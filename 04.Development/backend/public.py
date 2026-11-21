"""Anonymous submitted-plan projection. No account or draft data is selected."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, exists, func, select

from backend.auth import SettingsDep, clock, deny, runtime
from backend.cycles import catalogue, cycle_summary
from backend.models import cycle, cycle_institution, plan, planned_dataset

router = APIRouter(prefix="/api/public", tags=["public submitted plans"])


class Projection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicCycle(Projection):
    year: int
    opens_at: datetime
    closes_at: datetime
    timezone: str
    licence_text: str
    licence_url: str
    server_now: datetime
    window_state: str


class PublicTheme(Projection):
    id: UUID
    code: str
    labels: dict[str, str]


class Catalogue(Projection):
    cycles: list[PublicCycle]
    themes: list[PublicTheme]


class PublicInstitution(Projection):
    id: UUID
    name: str
    institution_type: str | None
    institution_level: str | None
    institution_region: str | None


class PlanSummary(Projection):
    id: UUID
    year: int
    institution: PublicInstitution
    first_submitted_at: datetime
    updated_at: datetime
    item_count: int
    themes: list[PublicTheme]


class PlanPage(Projection):
    cycle: PublicCycle
    items: list[PlanSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


class PublicItem(Projection):
    id: UUID
    title: str
    description: str | None
    responsible_department: str | None
    planned_quarter: int | None
    theme: PublicTheme
    personal_data_confirmation: bool


class PlanDetail(Projection):
    cycle: PublicCycle
    plan: PlanSummary
    items: list[PublicItem]


def cycle_public(row, now):
    return {
        k: v for k, v in cycle_summary(row, now).items() if k not in {"id", "revision"}
    }


def themes_public(conn):
    return {
        t["id"]: {k: t[k] for k in ("id", "code", "labels")} for t in catalogue(conn)
    }


SOURCE = plan.join(cycle, plan.c.cycle_id == cycle.c.id).join(
    cycle_institution,
    and_(
        cycle_institution.c.cycle_id == plan.c.cycle_id,
        cycle_institution.c.institution_id == plan.c.institution_id,
    ),
)
COLUMNS = [
    plan.c.id,
    plan.c.first_submitted_at,
    plan.c.updated_at,
    plan.c.institution_id,
    cycle.c.year,
    cycle_institution.c.name,
    cycle_institution.c.institution_type,
    cycle_institution.c.institution_level,
    cycle_institution.c.institution_region,
]
ITEM_COLUMNS = [
    planned_dataset.c.id,
    planned_dataset.c.plan_id,
    planned_dataset.c.title,
    planned_dataset.c.description,
    planned_dataset.c.responsible_department,
    planned_dataset.c.planned_quarter,
    planned_dataset.c.theme_id,
    planned_dataset.c.personal_data_confirmation,
]


def selected_items(conn, ids):
    if not ids:
        return []
    return list(
        conn.execute(
            select(*ITEM_COLUMNS)
            .where(planned_dataset.c.plan_id.in_(ids))
            .order_by(planned_dataset.c.position, planned_dataset.c.id)
        ).mappings()
    )


def summary(row, items, themes):
    return {
        "id": row["id"],
        "year": row["year"],
        "institution": {
            "id": row["institution_id"],
            **{
                k: row[k]
                for k in (
                    "name",
                    "institution_type",
                    "institution_level",
                    "institution_region",
                )
            },
        },
        "first_submitted_at": row["first_submitted_at"],
        "updated_at": row["updated_at"],
        "item_count": len(items),
        "themes": [
            themes[tid]
            for tid in sorted(
                {i["theme_id"] for i in items}, key=lambda t: themes[t]["code"]
            )
        ],
    }


@router.get("/cycles", response_model=Catalogue)
def cycles(settings: SettingsDep):
    with runtime(settings, snapshot=True) as conn:
        now = clock(conn)
        return jsonable_encoder(
            {
                "cycles": [
                    cycle_public(r, now)
                    for r in conn.execute(
                        select(cycle).order_by(cycle.c.year.desc())
                    ).mappings()
                ],
                "themes": list(themes_public(conn).values()),
            }
        )


@router.get("/plans", response_model=PlanPage)
def plans(
    settings: SettingsDep,
    year: int = Query(ge=2000, le=2100),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=100),
    q: str = Query(default="", max_length=200),
    theme_id: UUID | None = None,
):
    with runtime(settings, snapshot=True) as conn:
        cy = (
            conn.execute(select(cycle).where(cycle.c.year == year))
            .mappings()
            .one_or_none()
        )
        if cy is None:
            deny("NOT_FOUND", 404)
        conditions = [plan.c.status == "submitted", plan.c.cycle_id == cy["id"]]
        if q.strip():
            conditions.append(
                cycle_institution.c.name.icontains(q.strip(), autoescape=True)
            )
        if theme_id is not None:
            conditions.append(
                exists(
                    select(planned_dataset.c.id).where(
                        planned_dataset.c.plan_id == plan.c.id,
                        planned_dataset.c.theme_id == theme_id,
                    )
                )
            )
        total = conn.execute(
            select(func.count()).select_from(SOURCE).where(*conditions)
        ).scalar_one()
        rows = list(
            conn.execute(
                select(*COLUMNS)
                .select_from(SOURCE)
                .where(*conditions)
                .order_by(cycle_institution.c.name, plan.c.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            ).mappings()
        )
        items = selected_items(conn, [r["id"] for r in rows])
        by_plan = {}
        for i in items:
            by_plan.setdefault(i["plan_id"], []).append(i)
        themes = themes_public(conn)
        return jsonable_encoder(
            {
                "cycle": cycle_public(cy, clock(conn)),
                "items": [summary(r, by_plan.get(r["id"], []), themes) for r in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_next": page * page_size < total,
            }
        )


@router.get("/plans/{plan_id}", response_model=PlanDetail)
def detail(plan_id: UUID, settings: SettingsDep):
    with runtime(settings, snapshot=True) as conn:
        row = (
            conn.execute(
                select(*COLUMNS)
                .select_from(SOURCE)
                .where(plan.c.id == plan_id, plan.c.status == "submitted")
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            deny("NOT_FOUND", 404)
        cy = (
            conn.execute(select(cycle).where(cycle.c.year == row["year"]))
            .mappings()
            .one()
        )
        items, themes = selected_items(conn, [plan_id]), themes_public(conn)
        return jsonable_encoder(
            {
                "cycle": cycle_public(cy, clock(conn)),
                "plan": summary(row, items, themes),
                "items": [
                    {
                        **{
                            k: i[k]
                            for k in (
                                "id",
                                "title",
                                "description",
                                "responsible_department",
                                "planned_quarter",
                                "personal_data_confirmation",
                            )
                        },
                        "theme": themes[i["theme_id"]],
                    }
                    for i in items
                ],
            }
        )
