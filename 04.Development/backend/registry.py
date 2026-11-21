"""Administrator register corrections, exact-domain versions and redacted audit browsing."""

import hashlib
import json
import unicodedata
from typing import Literal
from uuid import UUID, uuid4, uuid5

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, insert, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from backend.access_policy import normalize_domain, private_domain
from backend.auth import (
    ADMIN_ROLES,
    SettingsDep,
    authenticate,
    clock,
    deny,
    identify,
    runtime,
)
from backend.lifecycle import discard_access
from backend.models import (
    account,
    audit_event,
    institution,
    institution_register_version,
)
from backend.models import institution_email_domain as domain

router = APIRouter(prefix="/api/admin", tags=["register, domain and audit"])


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    reason: str = Field(min_length=1, max_length=500)
    confirmed: bool = False

    @field_validator("reason")
    @classmethod
    def clean(cls, v):
        return clean_text(v)


class Attributes(Evidence):
    name: str = Field(min_length=1, max_length=300)
    institution_type: str | None = Field(default=None, max_length=100)
    institution_level: str | None = Field(default=None, max_length=100)
    institution_region: str | None = Field(default=None, max_length=100)
    active: bool
    source_reference: str = Field(min_length=1, max_length=300)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator(
        "name",
        "source_reference",
        "institution_type",
        "institution_level",
        "institution_region",
    )
    @classmethod
    def clean_fields(cls, v):
        return clean_text(v) if v is not None else v


class CreateInstitution(Attributes):
    source_key: str = Field(
        min_length=1, max_length=150, pattern=r"^[A-Za-z0-9._-]+:.+$"
    )

    @field_validator("source_key")
    @classmethod
    def clean_key(cls, v):
        return clean_text(v)


class UpdateInstitution(Attributes):
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class AddDomain(Evidence):
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    domain: str = Field(min_length=1, max_length=253)
    evidence_reference: str = Field(min_length=1, max_length=300)

    @field_validator("domain")
    @classmethod
    def exact_domain(cls, v):
        result = normalize_domain(v)
        if private_domain(result):
            raise ValueError("private_domain")
        return result

    @field_validator("evidence_reference")
    @classmethod
    def clean_evidence(cls, v):
        return clean_text(v)


class DisableDomain(Evidence):
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def clean_text(value):
    value = value.strip()
    if not value or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("invalid_text")
    return value


ATTRS = (
    "name",
    "institution_type",
    "institution_level",
    "institution_region",
    "active",
)


def revision(row):
    # Importer also updates updated_at; domain mutations explicitly touch the parent.
    body = {k: row[k] for k in (*ATTRS, "source_key")}
    body.update(
        updated_at=row["updated_at"].isoformat(),
        register_version_id=str(row["register_version_id"]),
    )
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def administrator(conn, request, settings):
    if identify(conn, request, settings)[2]["role"] not in ADMIN_ROLES:
        deny("FORBIDDEN")


def locked_institution(conn, iid, *, read=False):
    row = (
        conn.execute(
            select(institution)
            .where(institution.c.id == iid)
            .with_for_update(read=read)
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        deny("INVALID_INSTITUTION", 404)
    return row


def changing(conn, request, settings, iid, expected, *, account_ids=()):
    administrator(conn, request, settings)
    # Same lock used by the existing reviewed bulk importer, before any row locks.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('layer1-reference-import'))")
    )
    old = locked_institution(conn, iid)
    if revision(old) != expected:
        deny("STALE_REFERENCE", 409)
    ctx = authenticate(
        conn, request, settings, admin=True, csrf=True, extra_account_ids=account_ids
    )
    return old, ctx


def record(conn, ctx, request, action, entity_type, entity_id, changes):
    conn.execute(
        insert(audit_event).values(
            actor_id=ctx["actor"]["id"],
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request.state.request_id,
            changes={"version": 1, **changes},
        )
    )


def version(conn, body, now):
    vid = uuid4()
    conn.execute(
        insert(institution_register_version).values(
            id=vid,
            source_reference=body.source_reference,
            source_sha256=body.source_sha256,
            received_at=now,
            imported_at=now,
            row_count=1,
            status="applied",
        )
    )
    return vid


def summary(row):
    return {
        "id": row["id"],
        "source_key": row["source_key"],
        **{k: row[k] for k in ATTRS},
        "revision": revision(row),
    }


@router.get("/institutions")
def institutions(
    request: Request,
    settings: SettingsDep,
    q: str = "",
    after: UUID | None = None,
    limit: int = 50,
):
    if len(q) > 100 or not 1 <= limit <= 50:
        deny("INVALID_REQUEST", 422)
    with runtime(settings) as conn:
        authenticate(conn, request, settings, admin=True)
        stmt = select(institution)
        if q.strip():
            pattern = (
                "%"
                + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
                + "%"
            )
            stmt = stmt.where(
                or_(
                    institution.c.name.ilike(pattern, escape="!"),
                    institution.c.source_key.ilike(pattern, escape="!"),
                )
            )
        if after:
            stmt = stmt.where(institution.c.id > after)
        rows = (
            conn.execute(stmt.order_by(institution.c.id).limit(limit + 1))
            .mappings()
            .all()
        )
        return {
            "items": [summary(r) for r in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }


@router.get("/institutions/{institution_id}")
def detail(institution_id: UUID, request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        administrator(conn, request, settings)
        row = locked_institution(conn, institution_id, read=True)
        authenticate(conn, request, settings, admin=True)
        source = (
            conn.execute(
                select(institution_register_version).where(
                    institution_register_version.c.id == row["register_version_id"]
                )
            )
            .mappings()
            .one()
        )
        policies = (
            conn.execute(
                select(domain)
                .where(domain.c.institution_id == institution_id)
                .order_by(domain.c.created_at.desc(), domain.c.id)
                .limit(51)
            )
            .mappings()
            .all()
        )
        return {
            **summary(row),
            "register_source": {
                k: source[k]
                for k in (
                    "id",
                    "source_reference",
                    "source_sha256",
                    "received_at",
                    "row_count",
                )
            },
            "domains": [
                {
                    k: p[k]
                    for k in (
                        "id",
                        "normalized_domain",
                        "active",
                        "verified_by",
                        "verified_at",
                        "evidence_reference",
                    )
                }
                for p in policies[:50]
            ],
            "domain_history_truncated": len(policies) > 50,
        }


@router.post("/institutions", status_code=201)
def create(body: CreateInstitution, request: Request, settings: SettingsDep):
    if not body.confirmed:
        deny("INVALID_REFERENCE", 422)
    try:
        with runtime(settings) as conn:
            administrator(conn, request, settings)
            conn.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtext('layer1-reference-import'))"
                )
            )
            ctx = authenticate(conn, request, settings, admin=True, csrf=True)
            now = clock(conn)
            # Immutable identity contract also used by scripts.seed.register; no importer dependency at runtime.
            iid = uuid5(
                UUID("c7bfa2c4-9c03-4e50-afbe-ea53ae23869c"),
                "institution:" + body.source_key,
            )
            vid = version(conn, body, now)
            row = (
                conn.execute(
                    insert(institution)
                    .values(
                        id=iid,
                        source_key=body.source_key,
                        register_version_id=vid,
                        **{k: getattr(body, k) for k in ATTRS},
                        created_at=now,
                        updated_at=now,
                    )
                    .returning(institution)
                )
                .mappings()
                .one()
            )
            record(
                conn,
                ctx,
                request,
                "reference.institution_created",
                "institution",
                iid,
                {
                    "after": {k: row[k] for k in ATTRS},
                    "source_version": str(vid),
                    "source_reference": body.source_reference,
                    "reason": body.reason,
                },
            )
            return summary(row)
    except IntegrityError:
        deny("REFERENCE_CONFLICT", 409)


@router.post("/institutions/{institution_id}/update")
def change(
    institution_id: UUID,
    body: UpdateInstitution,
    request: Request,
    settings: SettingsDep,
):
    if not body.confirmed:
        deny("INVALID_REFERENCE", 422)
    with runtime(settings) as conn:
        # Gather IDs after institution lock; exclusive lock blocks concurrent account creation.
        old, ctx = changing(
            conn, request, settings, institution_id, body.expected_revision
        )
        # Actor already locked; institution accounts cannot be administrators, so no reverse admin lock edge.
        members = (
            conn.execute(
                select(account.c.id)
                .where(account.c.institution_id == institution_id)
                .order_by(account.c.id)
                .with_for_update()
            )
            .scalars()
            .all()
            if old["active"] and not body.active
            else []
        )
        now = clock(conn)
        vid = version(conn, body, now)
        row = (
            conn.execute(
                update(institution)
                .where(institution.c.id == institution_id)
                .values(
                    register_version_id=vid,
                    **{k: getattr(body, k) for k in ATTRS},
                    updated_at=now,
                )
                .returning(institution)
            )
            .mappings()
            .one()
        )
        sessions = grants = 0
        for aid in members:
            s, g = discard_access(conn, aid, now)
            sessions += s
            grants += g
        record(
            conn,
            ctx,
            request,
            "reference.institution_updated",
            "institution",
            institution_id,
            {
                "before": {k: old[k] for k in ATTRS},
                "after": {k: row[k] for k in ATTRS},
                "source_version": str(vid),
                "source_reference": body.source_reference,
                "reason": body.reason,
                "sessions_revoked": sessions,
                "grants_revoked": grants,
            },
        )
        return summary(row)


@router.post("/institutions/{institution_id}/domains", status_code=201)
def add_domain(
    institution_id: UUID, body: AddDomain, request: Request, settings: SettingsDep
):
    if not body.confirmed:
        deny("INVALID_REFERENCE", 422)
    try:
        with runtime(settings) as conn:
            old, ctx = changing(
                conn, request, settings, institution_id, body.expected_revision
            )
            if not old["active"]:
                deny("INVALID_INSTITUTION", 409)
            now, did = clock(conn), uuid4()
            conn.execute(
                insert(domain).values(
                    id=did,
                    institution_id=institution_id,
                    normalized_domain=body.domain,
                    active=True,
                    verified_by=ctx["actor"]["id"],
                    verified_at=now,
                    evidence_reference=body.evidence_reference,
                    created_at=now,
                )
            )
            row = (
                conn.execute(
                    update(institution)
                    .where(institution.c.id == institution_id)
                    .values(updated_at=now)
                    .returning(institution)
                )
                .mappings()
                .one()
            )
            record(
                conn,
                ctx,
                request,
                "reference.domain_added",
                "institution_email_domain",
                did,
                {
                    "institution_id": str(institution_id),
                    "after": {"normalized_domain": body.domain, "active": True},
                    "evidence_reference": body.evidence_reference,
                    "reason": body.reason,
                },
            )
            return {"id": did, "revision": revision(row)}
    except IntegrityError:
        deny("REFERENCE_CONFLICT", 409)


@router.post("/institutions/{institution_id}/domains/{domain_id}/disable")
def disable_domain(
    institution_id: UUID,
    domain_id: UUID,
    body: DisableDomain,
    request: Request,
    settings: SettingsDep,
):
    if not body.confirmed:
        deny("INVALID_REFERENCE", 422)
    with runtime(settings) as conn:
        _, ctx = changing(
            conn, request, settings, institution_id, body.expected_revision
        )
        policy = (
            conn.execute(
                select(domain)
                .where(
                    domain.c.id == domain_id, domain.c.institution_id == institution_id
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if not policy or not policy["active"]:
            deny("REFERENCE_CONFLICT", 409)
        now = clock(conn)
        conn.execute(
            update(domain).where(domain.c.id == domain_id).values(active=False)
        )
        row = (
            conn.execute(
                update(institution)
                .where(institution.c.id == institution_id)
                .values(updated_at=now)
                .returning(institution)
            )
            .mappings()
            .one()
        )
        record(
            conn,
            ctx,
            request,
            "reference.domain_disabled",
            "institution_email_domain",
            domain_id,
            {
                "institution_id": str(institution_id),
                "before": {
                    "normalized_domain": policy["normalized_domain"],
                    "active": True,
                },
                "after": {
                    "normalized_domain": policy["normalized_domain"],
                    "active": False,
                },
                "reason": body.reason,
            },
        )
        return {"id": domain_id, "revision": revision(row)}


AUDIT_ACTIONS = {
    "feed.internal_prepared",
    "plan.draft_saved",
    "plan.submitted",
    "plan.amended",
    "settings.cycle_created",
    "settings.window_changed",
    "settings.theme_created",
    "settings.theme_eligibility",
    "access.requested",
    "auth.login",
    "auth.logout",
    "account.approved",
    "account.rejected",
    "account.replaced",
    "account.deactivated",
    "recovery.issued",
    "recovery.consumed",
    "recovery.password_changed",
    "recovery.signed_out",
    "reference.institution_created",
    "reference.institution_updated",
    "reference.domain_added",
    "reference.domain_disabled",
    "reference.register_import",
    "reference.cycle_snapshot_import",
    "reference.themes_seed",
    "synthetic.seed",
    "admin.bootstrap",
}
AUDIT_FIELDS = {
    "profile",
    "schema_version",
    "record_count",
    "plan_count",
    "item_count",
    "year",
    "opens_at",
    "closes_at",
    "timezone",
    "institution_count",
    "active_themes",
    "from_revision",
    "to_revision",
    "code",
    "uri",
    "theme_id",
    "from_active",
    "to_active",
    "from",
    "to",
    "correspondence_checked",
    "revoked_sessions",
    "revoked_unused_grants",
    "replaced_account_id",
    "domain_review",
    "version",
    "reason",
    "source_version",
    "source_reference",
    "evidence_reference",
    "institution_id",
    "sessions_revoked",
    "grants_revoked",
    "status",
    "domain_policy_id",
    "replacement_account_id",
    "approval_reference",
    "rows",
    "inserted",
    "updated",
    "added",
}


def safe_changes(changes):
    # Never recursively echo arbitrary JSON from old/future producers.
    safe = {
        k: v
        for k, v in changes.items()
        if k in AUDIT_FIELDS and (v is None or type(v) in (str, int, bool))
    }
    for key, fields in (
        ("before_window", {"opens_at", "closes_at", "timezone"}),
        ("after_window", {"opens_at", "closes_at", "timezone"}),
        ("labels", {"en", "sr-Latn", "sr-Cyrl"}),
    ):
        if isinstance(changes.get(key), dict):
            safe[key] = {
                k: v
                for k, v in changes[key].items()
                if k in fields and isinstance(v, str)
            }
    for key in ("before", "after"):
        if isinstance(changes.get(key), dict):
            safe[key] = {
                k: v
                for k, v in changes[key].items()
                if k in {*ATTRS, "normalized_domain"}
                and (v is None or type(v) in (str, int, bool))
            }
    return safe


@router.get("/audit")
def audit(
    request: Request,
    settings: SettingsDep,
    entity_type: Literal[
        "account",
        "session",
        "institution",
        "institution_email_domain",
        "institution_register_version",
        "cycle",
        "theme",
        "plan",
    ]
    | None = None,
    entity_id: UUID | None = None,
    action: str | None = None,
    before: UUID | None = None,
    limit: int = 50,
):
    if not 1 <= limit <= 50 or (action is not None and action not in AUDIT_ACTIONS):
        deny("INVALID_REQUEST", 422)
    with runtime(settings) as conn:
        authenticate(conn, request, settings, admin=True)
        stmt = select(audit_event).where(audit_event.c.action.in_(AUDIT_ACTIONS))
        for column, value in (
            (audit_event.c.entity_type, entity_type),
            (audit_event.c.entity_id, entity_id),
            (audit_event.c.action, action),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        if before:
            cursor = (
                conn.execute(
                    select(audit_event.c.occurred_at, audit_event.c.id).where(
                        audit_event.c.id == before,
                        audit_event.c.action.in_(AUDIT_ACTIONS),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if not cursor:
                deny("INVALID_REQUEST", 422)
            stmt = stmt.where(
                or_(
                    audit_event.c.occurred_at < cursor["occurred_at"],
                    and_(
                        audit_event.c.occurred_at == cursor["occurred_at"],
                        audit_event.c.id < cursor["id"],
                    ),
                )
            )
        rows = (
            conn.execute(
                stmt.order_by(
                    audit_event.c.occurred_at.desc(), audit_event.c.id.desc()
                ).limit(limit + 1)
            )
            .mappings()
            .all()
        )
        return {
            "items": [
                {
                    **{
                        k: r[k]
                        for k in (
                            "id",
                            "actor_id",
                            "action",
                            "entity_type",
                            "entity_id",
                            "occurred_at",
                            "request_id",
                        )
                    },
                    "changes": safe_changes(r["changes"]),
                }
                for r in rows[:limit]
            ],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }
