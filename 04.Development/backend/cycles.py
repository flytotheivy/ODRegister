"""Annual settings with DB clock boundaries, frozen identity and future theme eligibility."""

import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field, field_validator, model_validator
from sqlalchemy import func, insert, literal, select, text, update
from sqlalchemy.exc import IntegrityError

from backend.auth import SettingsDep, authenticate, clock, deny, runtime
from backend.models import (
    cycle,
    cycle_institution,
    cycle_theme,
    institution,
    institution_register_version,
    plan,
    theme,
    theme_translation,
)
from backend.registry import Evidence, administrator, clean_text, record

router = APIRouter(prefix="/api/admin", tags=["cycle and theme settings"])
BASE_CODES = (
    "AGRI",
    "ECON",
    "EDUC",
    "ENER",
    "ENVI",
    "GOVE",
    "HEAL",
    "INTR",
    "JUST",
    "SOCI",
    "REGI",
    "TECH",
    "TRAN",
)
LOCALES = {"en", "sr-Latn", "sr-Cyrl"}


def valid_uri(value):
    value = clean_text(value)
    try:
        u = urlsplit(value)
        if (
            u.scheme not in ("http", "https")
            or not u.hostname
            or u.username
            or u.password
        ):
            raise ValueError("invalid_uri")
        _ = u.port
    except ValueError:
        raise ValueError("invalid_uri") from None
    if any(c.isspace() for c in value):
        raise ValueError("invalid_uri")
    return value


class WindowInput(Evidence):
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    timezone: str = Field(min_length=1, max_length=80)

    @field_validator("opens_at", "closes_at", mode="before")
    @classmethod
    def explicit_instant(cls, v):
        if (
            not isinstance(v, str)
            or "T" not in v
            or not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", v)
        ):
            raise ValueError("explicit_iso_offset_required")
        return v

    @field_validator("timezone")
    @classmethod
    def zone(cls, v):
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("invalid_timezone") from None
        return v

    @model_validator(mode="after")
    def ordered(self):
        if self.opens_at >= self.closes_at:
            raise ValueError("invalid_window")
        return self


class CreateCycle(WindowInput):
    year: int = Field(ge=2000, le=9999)
    licence_text: str = Field(min_length=1, max_length=2000)
    licence_url: str = Field(min_length=1, max_length=2048)

    @field_validator("licence_text")
    @classmethod
    def label(cls, v):
        return clean_text(v)

    @field_validator("licence_url")
    @classmethod
    def uri(cls, v):
        return valid_uri(v)


class UpdateWindow(WindowInput):
    expected_revision: int = Field(ge=1)


class CreateTheme(Evidence):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    uri: str = Field(min_length=1, max_length=2048)
    labels: dict[Literal["en", "sr-Latn", "sr-Cyrl"], str]
    evidence_reference: str = Field(min_length=1, max_length=300)

    @field_validator("evidence_reference")
    @classmethod
    def proof(cls, v):
        return clean_text(v)

    @model_validator(mode="after")
    def complete(self):
        self.uri = valid_uri(self.uri)
        u = urlsplit(self.uri)
        if u.query or u.fragment or u.path.rsplit("/", 1)[-1] != self.code:
            raise ValueError("code_uri_mismatch")
        if set(self.labels) != LOCALES:
            raise ValueError("three_labels_required")
        self.labels = {k: clean_text(v) for k, v in self.labels.items()}
        if any(len(v) > 300 for v in self.labels.values()):
            raise ValueError("label_too_long")
        return self


class ThemeEligibility(Evidence):
    expected_revision: int = Field(ge=1)
    active: bool


def reference_lock(conn):
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('layer1-reference-import'))")
    )


def locked_cycle(conn, cid, *, read=False):
    row = (
        conn.execute(select(cycle).where(cycle.c.id == cid).with_for_update(read=read))
        .mappings()
        .one_or_none()
    )
    if not row:
        deny("INVALID_CYCLE", 404)
    return row


def window_state(row, now):
    """Use only after acquiring the cycle lock; future plan writes must recheck DB time."""
    return (
        "scheduled"
        if now < row["opens_at"]
        else "open"
        if now < row["closes_at"]
        else "closed"
    )


def has_plans(conn, cid):
    return (
        conn.execute(select(plan.c.id).where(plan.c.cycle_id == cid).limit(1)).first()
        is not None
    )


def catalogue(conn):
    labels = {}
    for row in conn.execute(select(theme_translation)).mappings():
        labels.setdefault(row["theme_id"], {})[row["locale"]] = row["label"]
    return [
        {
            **dict(t),
            "labels": labels.get(t["id"], {}),
            "baseline": t["code"] in BASE_CODES,
        }
        for t in conn.execute(select(theme).order_by(theme.c.code)).mappings()
    ]


def cycle_summary(row, now):
    return {
        **{
            k: row[k]
            for k in (
                "id",
                "year",
                "opens_at",
                "closes_at",
                "timezone",
                "licence_text",
                "licence_url",
                "revision",
            )
        },
        "server_now": now,
        "window_state": window_state(row, now),
    }


@router.get("/cycles")
def list_cycles(
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
        authenticate(conn, request, settings, admin=True)
        stmt = select(cycle)
        if before_year is not None:
            stmt = stmt.where(cycle.c.year < before_year)
        rows = (
            conn.execute(stmt.order_by(cycle.c.year.desc()).limit(limit + 1))
            .mappings()
            .all()
        )
        now = clock(conn)
        return {
            "items": [cycle_summary(r, now) for r in rows[:limit]],
            "next_cursor": rows[limit - 1]["year"] if len(rows) > limit else None,
            "active_register_count": conn.execute(
                select(func.count())
                .select_from(institution)
                .join(
                    institution_register_version,
                    institution.c.register_version_id
                    == institution_register_version.c.id,
                )
                .where(
                    institution.c.active.is_(True),
                    institution_register_version.c.status == "applied",
                )
            ).scalar_one(),
        }


@router.get("/cycles/{cycle_id}")
def cycle_detail(cycle_id: UUID, request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        administrator(conn, request, settings)
        row = locked_cycle(conn, cycle_id, read=True)
        authenticate(conn, request, settings, admin=True)
        now = clock(conn)
        active = dict(
            conn.execute(
                select(cycle_theme.c.theme_id, cycle_theme.c.active).where(
                    cycle_theme.c.cycle_id == cycle_id
                )
            ).all()
        )
        return {
            **cycle_summary(row, now),
            "has_plans": has_plans(conn, cycle_id),
            "institution_count": conn.execute(
                select(func.count())
                .select_from(cycle_institution)
                .where(cycle_institution.c.cycle_id == cycle_id)
            ).scalar_one(),
            "themes": [
                {**t, "active": active.get(t["id"], False)} for t in catalogue(conn)
            ],
        }


@router.post("/cycles", status_code=201)
def create_cycle(body: CreateCycle, request: Request, settings: SettingsDep):
    if not body.confirmed:
        deny("INVALID_SETTINGS", 422)
    try:
        with runtime(settings) as conn:
            administrator(conn, request, settings)
            reference_lock(conn)
            ctx = authenticate(conn, request, settings, admin=True, csrf=True)
            cats = catalogue(conn)
            baseline = {t["code"]: t for t in cats if t["baseline"]}
            if set(baseline) != set(BASE_CODES) or any(
                set(t["labels"]) != LOCALES
                or t["uri"]
                != "http://publications.europa.eu/resource/authority/data-theme/"
                + t["code"]
                for t in baseline.values()
            ):
                deny("REFERENCE_UNAVAILABLE", 409)
            now = clock(conn)
            cid = uuid4()
            row = (
                conn.execute(
                    insert(cycle)
                    .values(
                        id=cid,
                        year=body.year,
                        opens_at=body.opens_at,
                        closes_at=body.closes_at,
                        timezone=body.timezone,
                        licence_text=body.licence_text,
                        licence_url=body.licence_url,
                        created_at=now,
                        updated_at=now,
                    )
                    .returning(cycle)
                )
                .mappings()
                .one()
            )
            n = conn.execute(
                insert(cycle_institution).from_select(
                    [
                        "cycle_id",
                        "institution_id",
                        "register_version_id",
                        "name",
                        "institution_type",
                        "institution_level",
                        "institution_region",
                    ],
                    select(
                        literal(cid),
                        institution.c.id,
                        institution.c.register_version_id,
                        institution.c.name,
                        institution.c.institution_type,
                        institution.c.institution_level,
                        institution.c.institution_region,
                    )
                    .join(
                        institution_register_version,
                        institution.c.register_version_id
                        == institution_register_version.c.id,
                    )
                    .where(
                        institution.c.active.is_(True),
                        institution_register_version.c.status == "applied",
                    ),
                )
            ).rowcount
            if not n:
                deny("REFERENCE_UNAVAILABLE", 409)
            for t in cats:
                conn.execute(
                    insert(cycle_theme).values(
                        cycle_id=cid, theme_id=t["id"], active=t["baseline"]
                    )
                )
            record(
                conn,
                ctx,
                request,
                "settings.cycle_created",
                "cycle",
                cid,
                {
                    "year": body.year,
                    "opens_at": body.opens_at.isoformat(),
                    "closes_at": body.closes_at.isoformat(),
                    "timezone": body.timezone,
                    "institution_count": n,
                    "active_themes": len(baseline),
                    "reason": body.reason,
                },
            )
            return cycle_summary(row, now)
    except IntegrityError:
        deny("SETTINGS_CONFLICT", 409)


@router.post("/cycles/{cycle_id}/window")
def update_window(
    cycle_id: UUID, body: UpdateWindow, request: Request, settings: SettingsDep
):
    if not body.confirmed:
        deny("INVALID_SETTINGS", 422)
    with runtime(settings) as conn:
        administrator(conn, request, settings)
        reference_lock(conn)
        old = locked_cycle(conn, cycle_id)
        ctx = authenticate(conn, request, settings, admin=True, csrf=True)
        now = clock(conn)
        if old["revision"] != body.expected_revision:
            deny("SETTINGS_CONFLICT", 409)
        if now >= old["opens_at"] or has_plans(conn, cycle_id):
            if (
                body.opens_at != old["opens_at"]
                or body.timezone != old["timezone"]
                or body.closes_at <= old["closes_at"]
            ):
                deny("SETTINGS_LOCKED", 409)
        elif body.opens_at <= now:
            deny("SETTINGS_LOCKED", 409)
        if all(
            old[k] == getattr(body, k) for k in ("opens_at", "closes_at", "timezone")
        ):
            deny("SETTINGS_CONFLICT", 409)
        row = (
            conn.execute(
                update(cycle)
                .where(cycle.c.id == cycle_id)
                .values(
                    opens_at=body.opens_at,
                    closes_at=body.closes_at,
                    timezone=body.timezone,
                    revision=cycle.c.revision + 1,
                    updated_at=now,
                )
                .returning(cycle)
            )
            .mappings()
            .one()
        )
        record(
            conn,
            ctx,
            request,
            "settings.window_changed",
            "cycle",
            cycle_id,
            {
                "from_revision": old["revision"],
                "to_revision": row["revision"],
                "before_window": {
                    k: old[k].isoformat() if k != "timezone" else old[k]
                    for k in ("opens_at", "closes_at", "timezone")
                },
                "after_window": {
                    k: row[k].isoformat() if k != "timezone" else row[k]
                    for k in ("opens_at", "closes_at", "timezone")
                },
                "reason": body.reason,
            },
        )
        return cycle_summary(row, now)


@router.get("/themes")
def list_themes(request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        authenticate(conn, request, settings, admin=True)
        return {"items": catalogue(conn)}


@router.post("/themes", status_code=201)
def create_theme(body: CreateTheme, request: Request, settings: SettingsDep):
    if not body.confirmed:
        deny("INVALID_SETTINGS", 422)
    try:
        with runtime(settings) as conn:
            administrator(conn, request, settings)
            reference_lock(conn)
            ctx = authenticate(conn, request, settings, admin=True, csrf=True)
            tid = uuid4()
            conn.execute(insert(theme).values(id=tid, code=body.code, uri=body.uri))
            for locale, label in body.labels.items():
                conn.execute(
                    insert(theme_translation).values(
                        theme_id=tid, locale=locale, label=label
                    )
                )
            record(
                conn,
                ctx,
                request,
                "settings.theme_created",
                "theme",
                tid,
                {
                    "code": body.code,
                    "uri": body.uri,
                    "labels": body.labels,
                    "evidence_reference": body.evidence_reference,
                    "reason": body.reason,
                },
            )
            return {
                "id": tid,
                "code": body.code,
                "uri": body.uri,
                "labels": body.labels,
                "baseline": False,
            }
    except IntegrityError:
        deny("SETTINGS_CONFLICT", 409)


@router.post("/cycles/{cycle_id}/themes/{theme_id}")
def theme_eligibility(
    cycle_id: UUID,
    theme_id: UUID,
    body: ThemeEligibility,
    request: Request,
    settings: SettingsDep,
):
    if not body.confirmed:
        deny("INVALID_SETTINGS", 422)
    with runtime(settings) as conn:
        administrator(conn, request, settings)
        reference_lock(conn)
        old = locked_cycle(conn, cycle_id)
        ctx = authenticate(conn, request, settings, admin=True, csrf=True)
        now = clock(conn)
        if old["revision"] != body.expected_revision:
            deny("SETTINGS_CONFLICT", 409)
        if now >= old["opens_at"] or has_plans(conn, cycle_id):
            deny("SETTINGS_LOCKED", 409)
        target = (
            conn.execute(select(theme).where(theme.c.id == theme_id))
            .mappings()
            .one_or_none()
        )
        if not target:
            deny("INVALID_THEME", 404)
        labels = (
            conn.execute(
                select(theme_translation.c.locale).where(
                    theme_translation.c.theme_id == theme_id
                )
            )
            .scalars()
            .all()
        )
        if set(labels) != LOCALES:
            deny("REFERENCE_UNAVAILABLE", 409)
        current = conn.execute(
            select(cycle_theme.c.active).where(
                cycle_theme.c.cycle_id == cycle_id, cycle_theme.c.theme_id == theme_id
            )
        ).scalar_one_or_none()
        if bool(current) == body.active:
            deny("SETTINGS_CONFLICT", 409)
        if (
            not body.active
            and conn.execute(
                select(func.count())
                .select_from(cycle_theme)
                .where(
                    cycle_theme.c.cycle_id == cycle_id, cycle_theme.c.active.is_(True)
                )
            ).scalar_one()
            <= 1
        ):
            deny("SETTINGS_LOCKED", 409)
        if current is None:
            conn.execute(
                insert(cycle_theme).values(
                    cycle_id=cycle_id, theme_id=theme_id, active=body.active
                )
            )
        else:
            conn.execute(
                update(cycle_theme)
                .where(
                    cycle_theme.c.cycle_id == cycle_id,
                    cycle_theme.c.theme_id == theme_id,
                )
                .values(active=body.active)
            )
        row = (
            conn.execute(
                update(cycle)
                .where(cycle.c.id == cycle_id)
                .values(revision=cycle.c.revision + 1, updated_at=now)
                .returning(cycle)
            )
            .mappings()
            .one()
        )
        record(
            conn,
            ctx,
            request,
            "settings.theme_eligibility",
            "cycle",
            cycle_id,
            {
                "theme_id": str(theme_id),
                "code": target["code"],
                "from_active": bool(current),
                "to_active": body.active,
                "from_revision": old["revision"],
                "to_revision": row["revision"],
                "reason": body.reason,
            },
        )
        return cycle_summary(row, now)
