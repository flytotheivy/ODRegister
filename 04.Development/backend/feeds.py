"""Contract 2.0 whole-year public download, completed before response headers."""

import json
from datetime import datetime
from tempfile import SpooledTemporaryFile
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path
from pydantic import Field, field_validator
from sqlalchemy import distinct, func, select
from starlette.responses import StreamingResponse

from backend.auth import SettingsDep, clock, deny, runtime
from backend.models import (
    cycle,
    cycle_institution,
    plan,
    planned_dataset,
    theme,
    theme_translation,
)
from backend.public import SOURCE, Projection

router = APIRouter(prefix="/api/public/feeds", tags=["public annual JSON contract 2.0"])
SPOOL_LIMIT = 1024 * 1024


class Licence(Projection):
    text: str = Field(min_length=1)
    url: str


class PublicRecord(Projection):
    institution_id: UUID
    institution_name: str = Field(min_length=1)
    institution_type: str | None
    institution_level: str | None
    institution_region: str | None
    plan_id: UUID
    year: int
    dataset_id: UUID
    dataset_title: str = Field(min_length=1)
    description: str | None
    responsible_department: str | None
    planned_quarter: int | None = Field(ge=1, le=4)
    theme_code: str = Field(min_length=1)
    theme_uri: str
    theme_labels: dict[str, str]
    personal_data_confirmation: Literal[True]
    submitted_at: datetime
    updated_at: datetime

    @field_validator("theme_labels")
    @classmethod
    def three_labels(cls, value):
        if set(value) != {"en", "sr-Latn", "sr-Cyrl"} or not all(value.values()):
            raise ValueError("Incomplete public labels")
        return value


class PublicFeed(Projection):
    schema_version: Literal["2.0"] = "2.0"
    feed_type: Literal["public"] = "public"
    year: int
    generated_at: datetime
    licence: Licence
    record_count: int = Field(ge=0)
    plan_count: int = Field(ge=0)
    institution_count: int = Field(ge=0)
    records: list[PublicRecord]


FEED_SOURCE = SOURCE.join(planned_dataset, planned_dataset.c.plan_id == plan.c.id)
RECORD_COLUMNS = [
    plan.c.institution_id,
    cycle_institution.c.name.label("institution_name"),
    cycle_institution.c.institution_type,
    cycle_institution.c.institution_level,
    cycle_institution.c.institution_region,
    plan.c.id.label("plan_id"),
    cycle.c.year,
    planned_dataset.c.id.label("dataset_id"),
    planned_dataset.c.title.label("dataset_title"),
    planned_dataset.c.description,
    planned_dataset.c.responsible_department,
    planned_dataset.c.planned_quarter,
    theme.c.code.label("theme_code"),
    theme.c.uri.label("theme_uri"),
    planned_dataset.c.theme_id,
    planned_dataset.c.personal_data_confirmation,
    plan.c.first_submitted_at.label("submitted_at"),
    plan.c.updated_at,
]


def record_rows(conn, cid):
    return conn.execute(
        select(*RECORD_COLUMNS)
        .select_from(FEED_SOURCE.join(theme, theme.c.id == planned_dataset.c.theme_id))
        .where(plan.c.status == "submitted", plan.c.cycle_id == cid)
        .order_by(
            cycle_institution.c.name,
            plan.c.id,
            planned_dataset.c.position,
            planned_dataset.c.id,
        )
        .execution_options(stream_results=True, yield_per=500)
    ).mappings()


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def stage_feed(settings, year):
    spool = SpooledTemporaryFile(max_size=SPOOL_LIMIT, mode="w+b")  # noqa: SIM115 - transferred to streaming response cleanup
    try:
        with runtime(settings, snapshot=True) as conn:
            cy = (
                conn.execute(select(cycle).where(cycle.c.year == year))
                .mappings()
                .one_or_none()
            )
            if cy is None:
                deny("NOT_FOUND", 404)
            generated = clock(conn)
            conditions = [plan.c.status == "submitted", plan.c.cycle_id == cy["id"]]
            counts = conn.execute(
                select(
                    func.count(planned_dataset.c.id),
                    func.count(distinct(plan.c.id)),
                    func.count(distinct(plan.c.institution_id)),
                )
                .select_from(FEED_SOURCE)
                .where(*conditions)
            ).one()
            envelope = PublicFeed(
                year=year,
                generated_at=generated,
                licence=Licence(text=cy["licence_text"], url=cy["licence_url"]),
                record_count=counts[0],
                plan_count=counts[1],
                institution_count=counts[2],
                records=[],
            )
            header = envelope.model_dump(mode="json", exclude={"records"})
            spool.write(encode(header)[:-1] + b',"records":[')
            labels = {}
            for t in conn.execute(select(theme_translation)).mappings():
                labels.setdefault(t["theme_id"], {})[t["locale"]] = t["label"]
            actual = 0
            rows = record_rows(conn, cy["id"])
            try:
                for row in rows:
                    record = dict(row)
                    record["theme_labels"] = labels.get(record.pop("theme_id"), {})
                    encoded = PublicRecord.model_validate(record).model_dump(
                        mode="json"
                    )
                    if actual:
                        spool.write(b",")
                    spool.write(encode(encoded))
                    actual += 1
            finally:
                rows.close()
            if actual != counts[0]:
                raise ValueError("Public feed count mismatch")
            spool.write(b"]}\n")
            size = spool.tell()
        # Release the database transaction before a slow browser starts consuming bytes.
        spool.seek(0)
        return spool, size
    except BaseException:
        spool.close()
        raise


def chunks(spool):
    try:
        while data := spool.read(65536):
            yield data
    finally:
        spool.close()


class StagedResponse(StreamingResponse):
    """Close the spool even if ASGI send fails before the iterator starts."""

    def __init__(self, spool, size, year):
        self.spool = spool
        super().__init__(
            chunks(spool),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="annual-plans-{year}-public.json"',
                "Content-Length": str(size),
                "Cache-Control": "no-store",
            },
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.spool.close()


@router.get(
    "/{year}.json",
    response_model=PublicFeed,
    description="Whole selected year; independent of list search, theme filters and pagination.",
)
def public_feed(year: Annotated[int, Path(ge=2000, le=2100)], settings: SettingsDep):
    try:
        spool, size = stage_feed(settings, year)
    except OSError:
        deny("SERVICE_UNAVAILABLE", 503)
    return StagedResponse(spool, size, year)
