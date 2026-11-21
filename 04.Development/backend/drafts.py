"""Institution-owned private drafts; all mutations commit with revision and audit."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
)
from sqlalchemy import delete, insert, select, update

from backend.auth import (
    SettingsDep,
    authenticate,
    clock,
    deny,
    identify,
    require_institution,
    runtime,
)
from backend.cycles import catalogue, cycle_summary, locked_cycle, window_state
from backend.models import (
    cycle,
    cycle_institution,
    cycle_theme,
    institution,
    plan,
    plan_revision,
    planned_dataset,
)
from backend.registry import record

router = APIRouter(prefix="/api/my-plans", tags=["private annual drafts"])
CONTENT = (
    "title",
    "description",
    "responsible_department",
    "planned_quarter",
    "theme_id",
)


class DraftItem(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: UUID | None = None
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    responsible_department: str | None = Field(default=None, max_length=300)
    planned_quarter: StrictInt | None = Field(default=None, ge=1, le=4)
    theme_id: UUID | None = None
    personal_data_confirmation: StrictBool | None = None

    @field_validator("title", "description", "responsible_department")
    @classmethod
    def text_value(cls, v):
        if v is not None:
            if any(ord(c) < 32 and c not in "\n\r\t" for c in v):
                raise ValueError("invalid_control")
            return v.strip() or None
        return None


class SaveDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_revision: StrictInt = Field(ge=0)
    items: list[DraftItem] = Field(max_length=200)


def member_lock(conn, request, settings):
    _, _, actor = identify(conn, request, settings)
    if actor["role"] != "institution_user":
        deny("FORBIDDEN")
    iid = actor["institution_id"]
    conn.execute(
        select(institution.c.id)
        .where(institution.c.id == iid)
        .with_for_update(read=True)
    ).one()
    return iid


def annual(conn, year, iid):
    cid = conn.execute(
        select(cycle.c.id).where(cycle.c.year == year)
    ).scalar_one_or_none()
    if cid is None:
        deny("PLAN_UNAVAILABLE", 404)
    row = locked_cycle(conn, cid, read=True)
    name = conn.execute(
        select(cycle_institution.c.name).where(
            cycle_institution.c.cycle_id == cid,
            cycle_institution.c.institution_id == iid,
        )
    ).scalar_one_or_none()
    if name is None:
        deny("PLAN_UNAVAILABLE", 404)
    return row, name


def existing(conn, cid, iid, lock=False):
    stmt = select(plan).where(plan.c.cycle_id == cid, plan.c.institution_id == iid)
    if lock:
        stmt = stmt.with_for_update()
    return conn.execute(stmt).mappings().one_or_none()


def items_for(conn, pid):
    return [
        dict(r)
        for r in conn.execute(
            select(planned_dataset)
            .where(planned_dataset.c.plan_id == pid)
            .order_by(planned_dataset.c.position, planned_dataset.c.id)
        ).mappings()
    ]


def document(conn, cy, name, iid, p, now):
    # Explicit whitelist: no account/email/confirmation actor or private revision snapshot.
    active = set(
        conn.execute(
            select(cycle_theme.c.theme_id).where(
                cycle_theme.c.cycle_id == cy["id"], cycle_theme.c.active.is_(True)
            )
        ).scalars()
    )
    return {
        "cycle": cycle_summary(cy, now),
        "institution": {"id": iid, "name": name},
        "themes": [t for t in catalogue(conn) if t["id"] in active],
        "plan": None
        if p is None
        else {
            **{
                k: p[k]
                for k in (
                    "id",
                    "status",
                    "revision",
                    "created_at",
                    "updated_at",
                    "first_submitted_at",
                )
            },
            "items": [
                {
                    k: r[k]
                    for k in ("id", "position", *CONTENT, "personal_data_confirmation")
                }
                for r in items_for(conn, p["id"])
            ],
        },
    }


@router.get("")
def listing(
    request: Request,
    settings: SettingsDep,
    before_year: int | None = None,
    limit: int = 50,
):
    if not 1 <= limit <= 50 or (
        before_year is not None and not 2000 <= before_year <= 9999
    ):
        deny("INVALID_REQUEST", 422)
    with runtime(settings) as conn:
        ctx = authenticate(conn, request, settings)
        iid = ctx["actor"]["institution_id"]
        require_institution(ctx, iid)
        stmt = (
            select(cycle, cycle_institution.c.name)
            .join(cycle_institution, cycle.c.id == cycle_institution.c.cycle_id)
            .where(cycle_institution.c.institution_id == iid)
        )
        if before_year is not None:
            stmt = stmt.where(cycle.c.year < before_year)
        years = (
            conn.execute(stmt.order_by(cycle.c.year.desc()).limit(limit + 1))
            .mappings()
            .all()
        )
        now = clock(conn)
        result = []
        for cy in years[:limit]:
            p = existing(conn, cy["id"], iid)
            result.append(
                {
                    "cycle": cycle_summary(cy, now),
                    "institution_name": cy["name"],
                    "plan": None
                    if p is None
                    else {
                        **{
                            k: p[k]
                            for k in (
                                "id",
                                "status",
                                "revision",
                                "updated_at",
                                "first_submitted_at",
                            )
                        },
                        "item_count": len(items_for(conn, p["id"])),
                    },
                }
            )
        return {
            "items": result,
            "next_cursor": years[limit - 1]["year"] if len(years) > limit else None,
        }


@router.get("/{year}")
def detail(year: int, request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        iid = member_lock(conn, request, settings)
        cy, name = annual(conn, year, iid)
        ctx = authenticate(conn, request, settings)
        require_institution(ctx, iid)
        p = existing(conn, cy["id"], iid, lock=True)
        return document(conn, cy, name, iid, p, clock(conn))


@router.post("/{year}/draft")
def save(year: int, body: SaveDraft, request: Request, settings: SettingsDep):
    return mutate(year, body, request, settings, submitting=False)


@router.post("/{year}/submit")
def submit(year: int, body: SaveDraft, request: Request, settings: SettingsDep):
    return mutate(year, body, request, settings, submitting=True)


@router.post("/{year}/amend")
def amend(year: int, body: SaveDraft, request: Request, settings: SettingsDep):
    return mutate(year, body, request, settings, submitting=True, amending=True)


def mutate(year, body, request, settings, *, submitting, amending=False):
    with runtime(settings) as conn:
        iid = member_lock(conn, request, settings)
        cy, name = annual(conn, year, iid)
        ctx = authenticate(conn, request, settings, csrf=True)
        require_institution(ctx, iid)
        p = existing(conn, cy["id"], iid, lock=True)
        now = clock(conn)
        if window_state(cy, now) != "open":
            deny("PLAN_WINDOW_CLOSED", 409)
        if amending:
            if p is None or p["status"] != "submitted":
                deny("PLAN_NOT_SUBMITTED", 409)
        elif p and p["status"] != "draft":
            deny("PLAN_SUBMITTED", 409)
        if body.expected_revision != (p["revision"] if p else 0):
            deny("PLAN_CONFLICT", 409)
        old_items = {r["id"]: r for r in items_for(conn, p["id"])} if p else {}
        supplied = [v.id for v in body.items if v.id is not None]
        if len(supplied) != len(set(supplied)) or not set(supplied) <= old_items.keys():
            deny("INVALID_DRAFT", 422)
        allowed = set(
            conn.execute(
                select(cycle_theme.c.theme_id).where(
                    cycle_theme.c.cycle_id == cy["id"], cycle_theme.c.active.is_(True)
                )
            ).scalars()
        )
        if any(
            v.theme_id is not None and v.theme_id not in allowed for v in body.items
        ):
            deny("INVALID_DRAFT", 422)
        if amending and not body.items:
            deny("LAST_DATASET_REQUIRED", 422)
        if submitting and (
            not body.items
            or any(
                not v.title
                or v.theme_id is None
                or v.personal_data_confirmation is not True
                for v in body.items
            )
        ):
            deny("SUBMISSION_INCOMPLETE", 422)
        if p:
            pid = p["id"]
            revision = p["revision"] + 1
            conn.execute(
                update(plan)
                .where(plan.c.id == pid)
                .values(
                    revision=revision,
                    updated_at=now,
                    **(
                        {"status": "submitted", "first_submitted_at": now}
                        if submitting and not amending
                        else {}
                    ),
                )
            )
        else:
            pid, revision = uuid4(), 1
            conn.execute(
                insert(plan).values(
                    id=pid,
                    institution_id=iid,
                    cycle_id=cy["id"],
                    status="submitted" if submitting else "draft",
                    first_submitted_at=now if submitting else None,
                    revision=revision,
                    created_at=now,
                    updated_at=now,
                )
            )
        keep = set(supplied)
        removed = set(old_items) - keep
        if removed:
            conn.execute(
                delete(planned_dataset).where(
                    planned_dataset.c.plan_id == pid, planned_dataset.c.id.in_(removed)
                )
            )
        for position, item in enumerate(body.items, 1):
            values = {k: getattr(item, k) for k in CONTENT}
            old = old_items.get(item.id)
            values.update(position=position, updated_at=now)
            changed = old is None or any(old[k] != getattr(item, k) for k in CONTENT)
            declared = item.personal_data_confirmation
            if declared is True:
                if changed or not old["personal_data_confirmation"]:
                    values.update(
                        personal_data_confirmation=True,
                        confirmed_at=now,
                        confirmed_by=ctx["actor"]["id"],
                    )
            elif declared is False or changed:
                values.update(
                    personal_data_confirmation=False,
                    confirmed_at=None,
                    confirmed_by=None,
                )
            if old:
                conn.execute(
                    update(planned_dataset)
                    .where(
                        planned_dataset.c.id == item.id,
                        planned_dataset.c.plan_id == pid,
                    )
                    .values(**values)
                )
            else:
                conn.execute(
                    insert(planned_dataset).values(
                        id=uuid4(), plan_id=pid, created_at=now, **values
                    )
                )
        fresh = existing(conn, cy["id"], iid)
        doc = document(conn, cy, name, iid, fresh, now)
        conn.execute(
            insert(plan_revision).values(
                plan_id=pid,
                revision=revision,
                saved_by=ctx["actor"]["id"],
                saved_at=now,
                snapshot=jsonable_encoder(
                    {
                        "version": 1,
                        "confirmation_statement_version": "no-personal-data-v1",
                        "institution_id": iid,
                        "cycle_id": cy["id"],
                        "plan": doc["plan"],
                    }
                ),
            )
        )
        record(
            conn,
            ctx,
            request,
            "plan.amended"
            if amending
            else "plan.submitted"
            if submitting
            else "plan.draft_saved",
            "plan",
            pid,
            {
                "from_revision": body.expected_revision,
                "to_revision": revision,
                "item_count": len(body.items),
            },
        )
        return doc
