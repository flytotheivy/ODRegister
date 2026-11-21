"""Protected contract2.0 projections with atomic prepared-export audit."""

from datetime import datetime
from itertools import groupby
from tempfile import SpooledTemporaryFile
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Request
from pydantic import Field, model_validator
from sqlalchemy import and_, func, select

from backend.auth import SettingsDep, authenticate, clock, deny, runtime
from backend.feeds import (
    FEED_SOURCE,
    RECORD_COLUMNS,
    SPOOL_LIMIT,
    Licence,
    PublicFeed,
    PublicRecord,
    StagedResponse,
    encode,
)
from backend.models import (
    account,
    cycle,
    cycle_institution,
    plan,
    planned_dataset,
    theme,
    theme_translation,
)
from backend.public import Projection
from backend.registry import record

router = APIRouter(
    prefix="/api/admin/feeds", tags=["protected internal annual JSON2.0"]
)
Profile = Literal["standard", "institutional-email"]


class InternalRecord(Projection):
    institution_id: UUID
    institution_name: str = Field(min_length=1)
    institution_type: str | None
    institution_level: str | None
    institution_region: str | None
    plan_id: UUID
    year: int
    dataset_id: UUID
    dataset_title: str | None = Field(min_length=1)
    description: str | None
    responsible_department: str | None
    planned_quarter: int | None = Field(ge=1, le=4)
    theme_code: str | None
    theme_uri: str | None
    theme_labels: dict[str, str] | None
    personal_data_confirmation: bool
    submitted_at: datetime | None
    updated_at: datetime
    plan_status: Literal["draft", "submitted"]

    @model_validator(mode="after")
    def submitted_fields(self):
        if self.plan_status == "submitted":
            PublicRecord.model_validate(self.model_dump(exclude={"plan_status"}))
        elif self.theme_labels is not None and (
            set(self.theme_labels) != {"en", "sr-Latn", "sr-Cyrl"}
            or not all(self.theme_labels.values())
        ):
            raise ValueError("Incomplete theme labels")
        return self


class InternalAccount(Projection):
    account_id: UUID
    approval_status: Literal["pending", "approved", "rejected", "deactivated"]


class EmailAccount(InternalAccount):
    email: str = Field(min_length=1)


class InternalInstitution(Projection):
    institution_id: UUID
    institution_name: str
    institution_type: str | None
    institution_level: str | None
    institution_region: str | None
    plan_id: UUID | None
    plan_status: Literal["no_plan", "draft", "submitted"]
    account_status: Literal["no_account", "pending", "approved", "not_approved"]
    accounts: list[InternalAccount | EmailAccount]


class InternalFeed(PublicFeed):
    feed_type: Literal["internal"] = "internal"
    records: list[InternalRecord]
    institutions: list[InternalInstitution]


def internal_records(conn, cid):
    return conn.execute(
        select(*RECORD_COLUMNS, plan.c.status.label("plan_status"))
        .select_from(
            FEED_SOURCE.outerjoin(theme, theme.c.id == planned_dataset.c.theme_id)
        )
        .where(plan.c.cycle_id == cid)
        .order_by(
            cycle_institution.c.name,
            plan.c.id,
            planned_dataset.c.position,
            planned_dataset.c.id,
        )
        .execution_options(stream_results=True, yield_per=500)
    ).mappings()


def institution_rows(conn, cid, include_email):
    source = cycle_institution.outerjoin(
        plan,
        and_(
            plan.c.cycle_id == cycle_institution.c.cycle_id,
            plan.c.institution_id == cycle_institution.c.institution_id,
        ),
    ).outerjoin(
        account,
        and_(
            account.c.institution_id == cycle_institution.c.institution_id,
            account.c.role == "institution_user",
        ),
    )
    fields = [
        cycle_institution.c.institution_id,
        cycle_institution.c.name.label("institution_name"),
        cycle_institution.c.institution_type,
        cycle_institution.c.institution_level,
        cycle_institution.c.institution_region,
        plan.c.id.label("plan_id"),
        plan.c.status.label("plan_status"),
        account.c.id.label("account_id"),
        account.c.status.label("approval_status"),
    ]
    if include_email:
        fields.append(account.c.email)
    return conn.execute(
        select(*fields)
        .select_from(source)
        .where(cycle_institution.c.cycle_id == cid)
        .order_by(
            cycle_institution.c.name, cycle_institution.c.institution_id, account.c.id
        )
        .execution_options(stream_results=True, yield_per=500)
    ).mappings()


def institutions(conn, cid, include_email):
    rows = institution_rows(conn, cid, include_email)
    try:
        for _, group in groupby(rows, key=lambda r: r["institution_id"]):
            first = None
            accounts = []
            for row in group:
                if first is None:
                    first = row
                if row["account_id"] is not None:
                    value = {
                        "account_id": row["account_id"],
                        "approval_status": "deactivated"
                        if row["approval_status"] == "inactive"
                        else row["approval_status"],
                    }
                    if include_email:
                        value["email"] = row["email"]
                    accounts.append(
                        (EmailAccount if include_email else InternalAccount)
                        .model_validate(value)
                        .model_dump(mode="json")
                    )
            assert first is not None
            states = {a["approval_status"] for a in accounts}
            status = (
                "approved"
                if "approved" in states
                else "pending"
                if "pending" in states
                else "not_approved"
                if states
                else "no_account"
            )
            yield InternalInstitution.model_validate(
                {
                    **{
                        k: first[k]
                        for k in (
                            "institution_id",
                            "institution_name",
                            "institution_type",
                            "institution_level",
                            "institution_region",
                            "plan_id",
                        )
                    },
                    "plan_status": first["plan_status"] or "no_plan",
                    "account_status": status,
                    "accounts": accounts,
                }
            ).model_dump(mode="json")
    finally:
        rows.close()


def stage_internal(settings, request, year, profile):
    spool = SpooledTemporaryFile(max_size=SPOOL_LIMIT, mode="w+b")  # noqa: SIM115 - response owns cleanup
    try:
        with runtime(settings, snapshot=True, readonly=False) as conn:
            ctx = authenticate(conn, request, settings, admin=True)
            cy = (
                conn.execute(select(cycle).where(cycle.c.year == year))
                .mappings()
                .one_or_none()
            )
            if cy is None:
                deny("NOT_FOUND", 404)
            source = cycle_institution.outerjoin(
                plan,
                and_(
                    plan.c.cycle_id == cycle_institution.c.cycle_id,
                    plan.c.institution_id == cycle_institution.c.institution_id,
                ),
            )
            n, plans = conn.execute(
                select(func.count(), func.count(plan.c.id))
                .select_from(source)
                .where(cycle_institution.c.cycle_id == cy["id"])
            ).one()
            count = conn.execute(
                select(func.count())
                .select_from(FEED_SOURCE)
                .where(plan.c.cycle_id == cy["id"])
            ).scalar_one()
            header = InternalFeed(
                year=year,
                generated_at=clock(conn),
                licence=Licence(text=cy["licence_text"], url=cy["licence_url"]),
                record_count=count,
                plan_count=plans,
                institution_count=n,
                records=[],
                institutions=[],
            ).model_dump(mode="json", exclude={"records", "institutions"})
            spool.write(encode(header)[:-1] + b',"records":[')
            labels = {}
            for t in conn.execute(select(theme_translation)).mappings():
                labels.setdefault(t["theme_id"], {})[t["locale"]] = t["label"]
            actual = 0
            rows = internal_records(conn, cy["id"])
            try:
                for row in rows:
                    value = dict(row)
                    tid = value.pop("theme_id")
                    value["theme_labels"] = labels.get(tid) if tid else None
                    value = InternalRecord.model_validate(value).model_dump(mode="json")
                    if actual:
                        spool.write(b",")
                    spool.write(encode(value))
                    actual += 1
            finally:
                rows.close()
            if actual != count:
                raise ValueError("Internal row count mismatch")
            spool.write(b'],"institutions":[')
            actual_n = actual_plans = 0
            for value in institutions(conn, cy["id"], profile == "institutional-email"):
                if actual_n:
                    spool.write(b",")
                spool.write(encode(value))
                actual_n += 1
                actual_plans += value["plan_id"] is not None
            if (actual_n, actual_plans) != (n, plans):
                raise ValueError("Internal denominator mismatch")
            spool.write(b"]}\n")
            size = spool.tell()
            # Lock ownership is retained; recheck real session deadlines before committing audit.
            ctx = authenticate(conn, request, settings, admin=True)
            record(
                conn,
                ctx,
                request,
                "feed.internal_prepared",
                "cycle",
                cy["id"],
                {
                    "year": year,
                    "profile": profile,
                    "schema_version": "2.0",
                    "record_count": count,
                    "plan_count": plans,
                    "institution_count": n,
                },
            )
        spool.seek(0)
        return spool, size, (count, plans, n)
    except BaseException:
        spool.close()
        raise


@router.get(
    "/{year}.json",
    response_model=InternalFeed,
    description="Active MPALSG/IT&E administrator only; standard omits emails, institutional-email includes all institutional account emails; successful preparation is audited.",
)
def internal_feed(
    year: Annotated[int, Path(ge=2000, le=2100)],
    request: Request,
    settings: SettingsDep,
    profile: Profile = "standard",
):
    try:
        spool, size, counts = stage_internal(settings, request, year, profile)
    except OSError:
        deny("SERVICE_UNAVAILABLE", 503)
    response = StagedResponse(spool, size, year)
    suffix = "-institutional-email" if profile == "institutional-email" else ""
    response.headers["Content-Disposition"] = (
        f'attachment; filename="annual-plans-{year}-internal{suffix}.json"'
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Cookie"
    for label, value in zip(["Record", "Plan", "Institution"], counts, strict=True):
        response.headers["X-Feed-" + label + "-Count"] = str(value)
    return response
