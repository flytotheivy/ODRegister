"""Manual institution-account recovery, one-use grants and isolated change-only sessions."""

import hmac
import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import insert, select, update

from backend.access_policy import normalize_email
from backend.auth import (
    ADMIN_ROLES,
    TOKEN,
    SettingsDep,
    authenticate,
    clock,
    cookie_name,
    csrf_token,
    deny,
    digest,
    identify,
    require_origin,
    runtime,
)
from backend.models import (
    account,
    audit_event,
    institution,
    session,
)
from backend.models import (
    account_recovery_grant as grant,
)
from backend.passwords import HashBusy, encode_password

router = APIRouter(prefix="/api", tags=["manual recovery"])


class IssueInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    identity_check_reference: str = Field(min_length=1, max_length=300)
    confirmed: bool = False


class ConsumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(max_length=254, repr=False)
    token: SecretStr = Field(min_length=43, max_length=43, repr=False)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        return normalize_email(v)


class ChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    new_password: SecretStr = Field(min_length=15, max_length=128, repr=False)


def recovery_cookie(settings):
    return (
        "l1_recovery"
        if settings.environment in ("development", "test")
        else "__Host-l1_recovery"
    )


def restricted_hash(raw):
    return digest("password-change:" + raw)


def secure(settings):
    return settings.environment not in ("development", "test")


def clear_cookies(response, settings):
    for name in (cookie_name(settings), recovery_cookie(settings)):
        response.delete_cookie(
            name, path="/", httponly=True, secure=secure(settings), samesite="lax"
        )


def lock_access(conn, aid):
    sessions = (
        conn.execute(
            select(session)
            .where(session.c.account_id == aid)
            .order_by(session.c.id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    conn.execute(
        select(grant.c.id)
        .where(grant.c.account_id == aid)
        .order_by(grant.c.id)
        .with_for_update()
    ).all()
    return sessions


def revoke(conn, aid, now, except_grant=None):
    conn.execute(
        update(session)
        .where(session.c.account_id == aid, session.c.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    stmt = update(grant).where(
        grant.c.account_id == aid,
        grant.c.used_at.is_(None),
        grant.c.revoked_at.is_(None),
    )
    if except_grant:
        stmt = stmt.where(grant.c.id != except_grant)
    conn.execute(stmt.values(revoked_at=now))


def log(conn, actor, action, entity, rid):
    conn.execute(
        insert(audit_event).values(
            actor_id=actor,
            action=action,
            entity_type="account",
            entity_id=entity,
            request_id=rid,
            changes={"version": 1},
        )
    )


def target_active(conn, actor):
    if (
        actor["role"] != "institution_user"
        or actor["status"] != "approved"
        or actor["inactive_at"] is not None
    ):
        deny("RECOVERY_FAILED", 401)
    if not conn.execute(
        select(institution.c.active)
        .where(institution.c.id == actor["institution_id"])
        .with_for_update(read=True)
    ).scalar_one():
        deny("RECOVERY_FAILED", 401)


@router.post("/admin/accounts/{account_id}/recovery")
def issue(account_id: UUID, body: IssueInput, request: Request, settings: SettingsDep):
    if not body.confirmed or not body.identity_check_reference.strip():
        deny("INVALID_RECOVERY", 422)
    with runtime(settings) as conn:
        _, _, admin = identify(conn, request, settings)
        if admin["role"] not in ADMIN_ROLES:
            deny("FORBIDDEN")
        target = (
            conn.execute(
                select(account).where(
                    account.c.id == account_id, account.c.role == "institution_user"
                )
            )
            .mappings()
            .one_or_none()
        )
        if not target:
            deny("ACCOUNT_UNAVAILABLE", 404)
        target_active(conn, target)
        ctx = authenticate(
            conn,
            request,
            settings,
            admin=True,
            csrf=True,
            extra_account_ids=[account_id],
        )
        target = (
            conn.execute(select(account).where(account.c.id == account_id))
            .mappings()
            .one()
        )
        if target["status"] != "approved" or target["inactive_at"] is not None:
            deny("ACCOUNT_UNAVAILABLE", 409)
        conn.execute(
            select(grant.c.id)
            .where(grant.c.account_id == account_id)
            .order_by(grant.c.id)
            .with_for_update()
        ).all()
        now = clock(conn)
        expires = now + timedelta(seconds=settings.recovery_grant_seconds)
        conn.execute(
            update(grant)
            .where(
                grant.c.account_id == account_id,
                grant.c.used_at.is_(None),
                grant.c.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        raw = secrets.token_urlsafe(32)
        conn.execute(
            insert(grant).values(
                account_id=account_id,
                issued_by=ctx["actor"]["id"],
                token_hash=digest(raw),
                issued_at=now,
                expires_at=expires,
                identity_check_reference=body.identity_check_reference.strip(),
            )
        )
        log(
            conn,
            ctx["actor"]["id"],
            "recovery.issued",
            account_id,
            request.state.request_id,
        )
    return {
        "temporary_credential": raw,
        "expires_at": expires,
        "request_id": request.state.request_id,
    }


@router.post("/auth/recovery/consume")
def consume(
    body: ConsumeInput, request: Request, response: Response, settings: SettingsDep
):
    require_origin(request, settings)
    raw = body.token.get_secret_value()
    if not TOKEN.fullmatch(raw):
        deny("RECOVERY_FAILED", 401)
    try:
        with runtime(settings) as conn:
            actor = (
                conn.execute(
                    select(account).where(account.c.normalized_email == body.email)
                )
                .mappings()
                .one_or_none()
            )
            if not actor:
                deny("RECOVERY_FAILED", 401)
            target_active(conn, actor)
            actor = (
                conn.execute(
                    select(account).where(account.c.id == actor["id"]).with_for_update()
                )
                .mappings()
                .one()
            )
            if (
                actor["role"] != "institution_user"
                or actor["status"] != "approved"
                or actor["inactive_at"] is not None
            ):
                deny("RECOVERY_FAILED", 401)
            lock_access(conn, actor["id"])
            now = clock(conn)
            gid = conn.execute(
                update(grant)
                .where(
                    grant.c.account_id == actor["id"],
                    grant.c.token_hash == digest(raw),
                    grant.c.used_at.is_(None),
                    grant.c.revoked_at.is_(None),
                    grant.c.expires_at > now,
                )
                .values(used_at=now)
                .returning(grant.c.id)
            ).scalar_one_or_none()
            if gid is None:
                deny("RECOVERY_FAILED", 401)
            unknown_hash = encode_password(secrets.token_urlsafe(32))
            revoke(conn, actor["id"], now, except_grant=gid)
            conn.execute(
                update(account)
                .where(account.c.id == actor["id"])
                .values(
                    password_hash=unknown_hash,
                    must_change_password=True,
                    updated_at=now,
                )
            )
            limited = secrets.token_urlsafe(32)
            end = now + timedelta(seconds=settings.recovery_session_seconds)
            conn.execute(
                insert(session).values(
                    account_id=actor["id"],
                    token_hash=restricted_hash(limited),
                    created_at=now,
                    last_seen_at=now,
                    idle_expires_at=end,
                    absolute_expires_at=end,
                )
            )
            log(
                conn,
                actor["id"],
                "recovery.consumed",
                actor["id"],
                request.state.request_id,
            )
        clear_cookies(response, settings)
        response.set_cookie(
            recovery_cookie(settings),
            limited,
            max_age=settings.recovery_session_seconds,
            path="/",
            httponly=True,
            secure=secure(settings),
            samesite="lax",
        )
        return {
            "mode": "password_change_required",
            "csrf_token": csrf_token(limited),
            "expires_at": end,
        }
    except HashBusy:
        deny("TRY_LATER", 429)


def restricted(conn, request, settings, *, mutation=False):
    raw = request.cookies.get(recovery_cookie(settings), "")
    if not TOKEN.fullmatch(raw):
        deny("RECOVERY_REQUIRED", 401)
    row = (
        conn.execute(
            select(session).where(session.c.token_hash == restricted_hash(raw))
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        deny("RECOVERY_REQUIRED", 401)
    actor = (
        conn.execute(select(account).where(account.c.id == row["account_id"]))
        .mappings()
        .one()
    )
    target_active(conn, actor)
    actor = (
        conn.execute(
            select(account).where(account.c.id == actor["id"]).with_for_update()
        )
        .mappings()
        .one()
    )
    sessions = lock_access(conn, actor["id"])
    stored = next(s for s in sessions if s["id"] == row["id"])
    now = clock(conn)
    if (
        actor["role"] != "institution_user"
        or actor["status"] != "approved"
        or actor["inactive_at"] is not None
        or not actor["must_change_password"]
        or stored["revoked_at"] is not None
        or now >= stored["idle_expires_at"]
        or now >= stored["absolute_expires_at"]
    ):
        deny("RECOVERY_REQUIRED", 401)
    if mutation:
        require_origin(request, settings)
        supplied = request.headers.get("x-csrf-token", "")
        if (
            len(supplied) != 64
            or not supplied.isascii()
            or not hmac.compare_digest(supplied, csrf_token(raw))
        ):
            deny("CSRF_INVALID")
    return actor, stored, raw, now


@router.get("/auth/recovery/me")
def recovery_me(request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        _, stored, raw, _ = restricted(conn, request, settings)
        return {
            "mode": "password_change_required",
            "csrf_token": csrf_token(raw),
            "expires_at": stored["absolute_expires_at"],
        }


@router.post("/auth/recovery/password")
def change(
    body: ChangeInput, request: Request, response: Response, settings: SettingsDep
):
    try:
        with runtime(settings) as conn:
            actor, _, _, now = restricted(conn, request, settings, mutation=True)
            hashed = encode_password(body.new_password.get_secret_value())
            conn.execute(
                update(account)
                .where(account.c.id == actor["id"])
                .values(
                    password_hash=hashed, must_change_password=False, updated_at=now
                )
            )
            revoke(conn, actor["id"], now)
            log(
                conn,
                actor["id"],
                "recovery.password_changed",
                actor["id"],
                request.state.request_id,
            )
        clear_cookies(response, settings)
        return {"status": "password_changed_sign_in_required"}
    except HashBusy:
        deny("TRY_LATER", 429)


@router.post("/auth/recovery/logout")
def recovery_logout(request: Request, response: Response, settings: SettingsDep):
    with runtime(settings) as conn:
        actor, stored, _, now = restricted(conn, request, settings, mutation=True)
        conn.execute(
            update(session).where(session.c.id == stored["id"]).values(revoked_at=now)
        )
        log(
            conn,
            actor["id"],
            "recovery.signed_out",
            actor["id"],
            request.state.request_id,
        )
    clear_cookies(response, settings)
    return {"status": "signed_out"}
