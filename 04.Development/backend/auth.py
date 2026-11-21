"""Database-backed opaque sessions and institution-scoped authorization."""

import hashlib
import hmac
import re
import secrets
from contextlib import contextmanager
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.access import Credentials
from backend.config import Settings, get_settings
from backend.database import DatabaseUnavailable
from backend.models import account, audit_event, institution, session
from backend.passwords import HashBusy, verify_password
from backend.store import transaction

router = APIRouter(prefix="/api", tags=["authentication"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
ADMIN_ROLES = ("ADMIN_MPALSG", "ADMIN_ITE")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def deny(code, status=403):
    raise HTTPException(status_code=status, detail=code)


def clock(conn):
    return conn.execute(text("SELECT clock_timestamp()")).scalar_one()


def cookie_name(settings):
    return (
        "l1_session"
        if settings.environment in ("development", "test")
        else "__Host-l1_session"
    )


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token):
    return hmac.new(token.encode(), b"layer1:csrf:v1", hashlib.sha256).hexdigest()


def require_origin(request, settings):
    if request.headers.get("origin") != settings.app_origin:
        deny("ORIGIN_INVALID")


@contextmanager
def runtime(settings, *, snapshot=False, readonly=True):
    try:
        with transaction(settings, snapshot=snapshot, readonly=readonly) as conn:
            yield conn
    except IntegrityError:
        deny("CONFLICT", 409)
    except (SQLAlchemyError, DatabaseUnavailable, ValueError):
        deny("SERVICE_UNAVAILABLE", 503)


def raw_cookie(request, settings):
    value = request.cookies.get(cookie_name(settings), "")
    if not TOKEN.fullmatch(value):
        deny("AUTH_REQUIRED", 401)
    return value


def usable(actor):
    return (
        actor["status"] == "approved"
        and actor["inactive_at"] is None
        and not actor["must_change_password"]
    )


def identify(conn, request, settings):
    token = raw_cookie(request, settings)
    row = (
        conn.execute(select(session).where(session.c.token_hash == digest(token)))
        .mappings()
        .one_or_none()
    )
    if not row:
        deny("AUTH_REQUIRED", 401)
    now = clock(conn)
    if (
        row["revoked_at"] is not None
        or now >= row["idle_expires_at"]
        or now >= row["absolute_expires_at"]
    ):
        deny("AUTH_REQUIRED", 401)
    actor = (
        conn.execute(select(account).where(account.c.id == row["account_id"]))
        .mappings()
        .one()
    )
    if not usable(actor):
        deny("AUTH_REQUIRED", 401)
    return token, row["id"], actor


def authenticate(
    conn, request, settings, *, admin=False, csrf=False, extra_account_ids=()
):
    token, sid, preliminary = identify(conn, request, settings)
    if admin and preliminary["role"] not in ADMIN_ROLES:
        deny("FORBIDDEN")
    if csrf:
        require_origin(request, settings)
        supplied = request.headers.get("x-csrf-token", "")
        if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(
            supplied, csrf_token(token)
        ):
            deny("CSRF_INVALID")
    # Institution -> sorted accounts -> session. Review locks target institution/policy first.
    if preliminary["institution_id"] is not None:
        active = conn.execute(
            select(institution.c.active)
            .where(institution.c.id == preliminary["institution_id"])
            .with_for_update(read=True)
        ).scalar_one()
        if not active:
            deny("AUTH_REQUIRED", 401)
    ids = sorted({preliminary["id"], *extra_account_ids}, key=str)
    locked = (
        conn.execute(
            select(account)
            .where(account.c.id.in_(ids))
            .order_by(account.c.id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    actor = next(row for row in locked if row["id"] == preliminary["id"])
    stored = (
        conn.execute(select(session).where(session.c.id == sid).with_for_update())
        .mappings()
        .one()
    )
    now = clock(conn)
    if (
        not usable(actor)
        or (admin and actor["role"] not in ADMIN_ROLES)
        or stored["revoked_at"] is not None
        or now >= stored["idle_expires_at"]
        or now >= stored["absolute_expires_at"]
    ):
        deny("AUTH_REQUIRED", 401)
    conn.execute(
        update(session)
        .where(session.c.id == sid)
        .values(
            last_seen_at=now,
            idle_expires_at=min(
                now + timedelta(seconds=settings.session_idle_seconds),
                stored["absolute_expires_at"],
            ),
        )
    )
    return {"actor": actor, "session_id": sid, "csrf_token": csrf_token(token)}


def profile(ctx):
    actor = ctx["actor"]
    return {
        "id": str(actor["id"]),
        "name": actor["name"],
        "role": actor["role"],
        "institution_id": str(actor["institution_id"])
        if actor["institution_id"]
        else None,
        "csrf_token": ctx["csrf_token"],
    }


@router.post("/auth/login")
def login(
    body: Credentials, request: Request, response: Response, settings: SettingsDep
):
    require_origin(request, settings)
    try:
        with runtime(settings) as conn:
            initial = (
                conn.execute(
                    select(account).where(account.c.normalized_email == body.email)
                )
                .mappings()
                .one_or_none()
            )
        correct = verify_password(
            body.password.get_secret_value(),
            initial["password_hash"] if initial else "!missing",
        )
    except HashBusy:
        deny("TRY_LATER", 429)
    if not correct:
        deny("LOGIN_FAILED", 401)
    token = secrets.token_urlsafe(32)
    with runtime(settings) as conn:
        if initial["institution_id"] is not None:
            active = conn.execute(
                select(institution.c.active)
                .where(institution.c.id == initial["institution_id"])
                .with_for_update(read=True)
            ).scalar_one()
            if not active:
                deny("LOGIN_FAILED", 401)
        actor = (
            conn.execute(
                select(account).where(account.c.id == initial["id"]).with_for_update()
            )
            .mappings()
            .one()
        )
        if actor["password_hash"] != initial["password_hash"] or not usable(actor):
            deny("LOGIN_FAILED", 401)
        old = request.cookies.get(cookie_name(settings), "")
        now = clock(conn)
        if TOKEN.fullmatch(old):
            conn.execute(
                update(session)
                .where(
                    session.c.token_hash == digest(old), session.c.revoked_at.is_(None)
                )
                .values(revoked_at=now)
            )
        sid = conn.execute(
            insert(session)
            .values(
                account_id=actor["id"],
                token_hash=digest(token),
                created_at=now,
                last_seen_at=now,
                idle_expires_at=now + timedelta(seconds=settings.session_idle_seconds),
                absolute_expires_at=now
                + timedelta(seconds=settings.session_absolute_seconds),
            )
            .returning(session.c.id)
        ).scalar_one()
        conn.execute(
            insert(audit_event).values(
                actor_id=actor["id"],
                action="auth.login",
                entity_type="session",
                entity_id=sid,
                request_id=request.state.request_id,
                changes={"version": 1},
            )
        )
        result = profile({"actor": actor, "csrf_token": csrf_token(token)})
    response.set_cookie(
        cookie_name(settings),
        token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.environment not in ("development", "test"),
        samesite="lax",
        path="/",
    )
    return result


@router.get("/auth/me")
def me(request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        return profile(authenticate(conn, request, settings))


@router.post("/auth/logout")
def logout(request: Request, response: Response, settings: SettingsDep):
    with runtime(settings) as conn:
        ctx = authenticate(conn, request, settings, csrf=True)
        conn.execute(
            update(session)
            .where(session.c.id == ctx["session_id"])
            .values(revoked_at=clock(conn))
        )
        conn.execute(
            insert(audit_event).values(
                actor_id=ctx["actor"]["id"],
                action="auth.logout",
                entity_type="session",
                entity_id=ctx["session_id"],
                request_id=request.state.request_id,
                changes={"version": 1},
            )
        )
    response.delete_cookie(
        cookie_name(settings),
        path="/",
        httponly=True,
        secure=settings.environment not in ("development", "test"),
        samesite="lax",
    )
    return {"status": "signed_out"}


def require_institution(ctx, iid):
    actor = ctx["actor"]
    if actor["role"] != "institution_user" or actor["institution_id"] != iid:
        deny("FORBIDDEN")


@router.get("/institutions/{institution_id}/access")
def institution_access(institution_id: UUID, request: Request, settings: SettingsDep):
    with runtime(settings) as conn:
        ctx = authenticate(conn, request, settings)
        require_institution(ctx, institution_id)
        name = conn.execute(
            select(institution.c.name).where(institution.c.id == institution_id)
        ).scalar_one()
        return {
            "institution_id": str(institution_id),
            "name": name,
            "permission": "institution_member",
        }
