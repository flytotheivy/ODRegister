"""Protected annual snapshot statistics; accounts never multiply institutions."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request, Response
from pydantic import Field
from sqlalchemy import and_, func, select

from backend.auth import SettingsDep, authenticate, clock, deny, runtime
from backend.models import (
    account,
    cycle,
    plan,
    theme,
    theme_translation,
)
from backend.models import (
    cycle_institution as ci,
)
from backend.models import (
    institution_register_version as versions,
)
from backend.models import (
    planned_dataset as ds,
)
from backend.public import Projection
from backend.registry import administrator

router = APIRouter(prefix="/api/admin/monitoring", tags=["annual monitoring"])
Dimension = Annotated[str | None, Query(max_length=100)]


def totals(conn, source):
    row = (
        conn.execute(
            select(
                func.count().label("target"),
                func.count()
                .filter(source.c.plan_status == "submitted")
                .label("submitted"),
                func.count().filter(source.c.plan_status == "draft").label("draft"),
                func.count().filter(source.c.plan_status.is_(None)).label("no_plan"),
            ).select_from(source)
        )
        .mappings()
        .one()
    )
    return metrics(dict(row))


def metrics(row):
    row["not_submitted"] = row["target"] - row["submitted"]
    row["submission_rate"] = (
        row["submitted"] / row["target"] * 100 if row["target"] else None
    )
    assert row["target"] == row["submitted"] + row["draft"] + row["no_plan"]
    return row


class Counts(Projection):
    target: int = Field(ge=0)
    submitted: int = Field(ge=0)
    draft: int = Field(ge=0)
    no_plan: int = Field(ge=0)
    not_submitted: int = Field(ge=0)
    submission_rate: float | None = Field(ge=0, le=100)


class Breakdown(Counts):
    value: str | None


class AccountCounts(Projection):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    approved: int = Field(ge=0)
    rejected: int = Field(ge=0)
    deactivated: int = Field(ge=0)


class DatasetCounts(Projection):
    submitted: int = Field(ge=0)
    draft: int = Field(ge=0)


class ThemeCounts(Projection):
    id: str
    code: str
    datasets: int = Field(ge=0)
    plans: int = Field(ge=0)
    labels: dict[str, str]


class RegisterVersion(Projection):
    id: str
    source_reference: str
    institutions: int = Field(ge=0)


class ProgressItem(Projection):
    institution_id: str
    name: str
    institution_type: str | None
    institution_level: str | None
    institution_region: str | None
    register_version_id: str
    plan_id: str | None
    plan_status: Literal["submitted", "draft", "no_plan"]
    dataset_count: int = Field(ge=0)


class ProgressPage(Projection):
    items: list[ProgressItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: Literal[50]
    has_more: bool
    status: Literal["all", "not_submitted", "submitted", "draft", "no_plan"]
    q: str


class Monitoring(Projection):
    year: int
    generated_at: datetime
    summary: Counts
    accounts: AccountCounts
    datasets: DatasetCounts
    dimensions: dict[
        Literal["institution_type", "institution_level", "institution_region"],
        list[Breakdown],
    ]
    options: dict[
        Literal["institution_type", "institution_level", "institution_region"],
        list[str | None],
    ]
    themes: list[ThemeCounts]
    register_versions: list[RegisterVersion]
    progress: ProgressPage


@router.get("/{year}", response_model=Monitoring)
def monitoring(
    request: Request,
    response: Response,
    settings: SettingsDep,
    year: Annotated[int, Path(ge=2000, le=2100)],
    institution_type: Dimension = None,
    institution_level: Dimension = None,
    institution_region: Dimension = None,
    type_missing: bool = False,
    level_missing: bool = False,
    region_missing: bool = False,
    status: Literal[
        "all", "not_submitted", "submitted", "draft", "no_plan"
    ] = "not_submitted",
    q: Annotated[str, Query(max_length=300)] = "",
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
):
    for value, missing in [
        (institution_type, type_missing),
        (institution_level, level_missing),
        (institution_region, region_missing),
    ]:
        if missing and value is not None:
            deny("INVALID_REQUEST", 422)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Cookie"
    with runtime(settings, snapshot=True, readonly=False) as conn:
        administrator(conn, request, settings)
        authenticate(conn, request, settings, admin=True)
        cy = conn.execute(
            select(cycle.c.id).where(cycle.c.year == year)
        ).scalar_one_or_none()
        if cy is None:
            deny("NOT_FOUND", 404)
        annual = (
            select(
                ci.c.institution_id,
                ci.c.name,
                ci.c.institution_type,
                ci.c.institution_level,
                ci.c.institution_region,
                ci.c.register_version_id,
                plan.c.id.label("plan_id"),
                plan.c.status.label("plan_status"),
            )
            .select_from(
                ci.outerjoin(
                    plan,
                    and_(
                        plan.c.cycle_id == ci.c.cycle_id,
                        plan.c.institution_id == ci.c.institution_id,
                    ),
                )
            )
            .where(ci.c.cycle_id == cy)
            .subquery()
        )
        where = []
        for key, value, missing in [
            ("institution_type", institution_type, type_missing),
            ("institution_level", institution_level, level_missing),
            ("institution_region", institution_region, region_missing),
        ]:
            if missing:
                where.append(annual.c[key].is_(None))
            elif value is not None:
                where.append(annual.c[key] == value)
        scoped = select(annual).where(*where).subquery()
        summary = totals(conn, scoped)
        dimensions, options = {}, {}
        for key in ["institution_type", "institution_level", "institution_region"]:
            field = scoped.c[key]
            rows = conn.execute(
                select(
                    field.label("value"),
                    func.count().label("target"),
                    func.count()
                    .filter(scoped.c.plan_status == "submitted")
                    .label("submitted"),
                    func.count().filter(scoped.c.plan_status == "draft").label("draft"),
                    func.count()
                    .filter(scoped.c.plan_status.is_(None))
                    .label("no_plan"),
                )
                .group_by(field)
                .order_by(field.asc().nulls_last())
            ).mappings()
            dimensions[key] = [metrics(dict(row)) for row in rows]
            options[key] = list(
                conn.execute(
                    select(annual.c[key])
                    .distinct()
                    .order_by(annual.c[key].asc().nulls_last())
                ).scalars()
            )
        accounts = dict.fromkeys(["pending", "approved", "rejected", "deactivated"], 0)
        for state, count in conn.execute(
            select(account.c.status, func.count())
            .where(
                account.c.role == "institution_user",
                account.c.institution_id.in_(select(scoped.c.institution_id)),
            )
            .group_by(account.c.status)
        ):
            accounts["deactivated" if state == "inactive" else state] = count
        item_source = scoped.join(ds, ds.c.plan_id == scoped.c.plan_id)
        item_counts = {"submitted": 0, "draft": 0}
        for state, count in conn.execute(
            select(scoped.c.plan_status, func.count())
            .select_from(item_source)
            .group_by(scoped.c.plan_status)
        ):
            item_counts[state] = count
        labels = {}
        for tid, locale, label in conn.execute(
            select(
                theme_translation.c.theme_id,
                theme_translation.c.locale,
                theme_translation.c.label,
            )
        ):
            labels.setdefault(str(tid), {})[locale] = label
        themes = [
            dict(row)
            for row in conn.execute(
                select(
                    theme.c.id,
                    theme.c.code,
                    func.count().label("datasets"),
                    func.count(func.distinct(scoped.c.plan_id)).label("plans"),
                )
                .select_from(item_source.join(theme, theme.c.id == ds.c.theme_id))
                .where(scoped.c.plan_status == "submitted")
                .group_by(theme.c.id, theme.c.code)
                .order_by(theme.c.code)
            ).mappings()
        ]
        for row in themes:
            row["id"] = str(row["id"])
            row["labels"] = labels.get(row["id"], {})
        listing = select(scoped)
        if status == "not_submitted":
            listing = listing.where(scoped.c.plan_status.is_distinct_from("submitted"))
        elif status == "no_plan":
            listing = listing.where(scoped.c.plan_status.is_(None))
        elif status != "all":
            listing = listing.where(scoped.c.plan_status == status)
        if q.strip():
            listing = listing.where(
                func.strpos(func.lower(scoped.c.name), q.strip().lower()) > 0
            )
        total = conn.execute(
            select(func.count()).select_from(listing.subquery())
        ).scalar_one()
        counts = (
            select(ds.c.plan_id, func.count().label("dataset_count"))
            .group_by(ds.c.plan_id)
            .subquery()
        )
        visible = listing.subquery()
        items = []
        for row in conn.execute(
            select(
                visible, func.coalesce(counts.c.dataset_count, 0).label("dataset_count")
            )
            .select_from(
                visible.outerjoin(counts, counts.c.plan_id == visible.c.plan_id)
            )
            .order_by(visible.c.name, visible.c.institution_id)
            .offset((page - 1) * 50)
            .limit(50)
        ).mappings():
            obj = dict(row)
            for key in ["institution_id", "plan_id", "register_version_id"]:
                obj[key] = str(obj[key]) if obj[key] is not None else None
            obj["plan_status"] = obj["plan_status"] or "no_plan"
            items.append(obj)
        provenance = [
            dict(row)
            for row in conn.execute(
                select(
                    versions.c.id,
                    versions.c.source_reference,
                    func.count().label("institutions"),
                )
                .select_from(
                    annual.join(versions, versions.c.id == annual.c.register_version_id)
                )
                .group_by(versions.c.id, versions.c.source_reference)
                .order_by(versions.c.id)
            ).mappings()
        ]
        for row in provenance:
            row["id"] = str(row["id"])
        # Recheck wall-clock session validity after all preparation, retaining locks.
        authenticate(conn, request, settings, admin=True)
        return {
            "year": year,
            "generated_at": clock(conn),
            "summary": summary,
            "accounts": {"total": sum(accounts.values()), **accounts},
            "datasets": item_counts,
            "dimensions": dimensions,
            "options": options,
            "themes": themes,
            "register_versions": provenance,
            "progress": {
                "items": items,
                "total": total,
                "page": page,
                "page_size": 50,
                "has_more": page * 50 < total,
                "status": status,
                "q": q.strip(),
            },
        }
