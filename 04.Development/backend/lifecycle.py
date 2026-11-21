"""Atomic institutional account deactivation/replacement. Never transfer plan ownership."""

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert, select, update

from backend.auth import (
    ADMIN_ROLES,
    SettingsDep,
    authenticate,
    clock,
    deny,
    identify,
    runtime,
)
from backend.models import (
    account,
    audit_event,
    cycle,
    institution,
    plan,
    planned_dataset,
    session,
)
from backend.models import (
    account_recovery_grant as grant,
)
from backend.review import current_policy, policy_usable

router = APIRouter(prefix="/api/admin/accounts", tags=["account lifecycle"])


class DeactivateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    reason: str = Field(min_length=1, max_length=500)
    confirmed: bool = False


class ReplaceInput(DeactivateInput):
    replacement_account_id: UUID
    correspondence_checked: bool = False
    approval_reference: str = Field(min_length=1, max_length=300)


def discard_access(conn, aid, now):
    # Explicitly lock in stable order, including sessions from other browsers/workers.
    conn.execute(
        select(session.c.id)
        .where(session.c.account_id == aid)
        .order_by(session.c.id)
        .with_for_update()
    ).all()
    conn.execute(
        select(grant.c.id)
        .where(grant.c.account_id == aid)
        .order_by(grant.c.id)
        .with_for_update()
    ).all()
    sessions = conn.execute(
        update(session)
        .where(session.c.account_id == aid, session.c.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount
    grants = conn.execute(
        update(grant)
        .where(
            grant.c.account_id == aid,
            grant.c.used_at.is_(None),
            grant.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    ).rowcount
    return sessions, grants


def transition(old_id, body, request, settings, replacing):
    if not body.confirmed or not body.reason.strip():
        deny("INVALID_LIFECYCLE", 422)
    if replacing and (
        not body.correspondence_checked
        or not body.approval_reference.strip()
        or body.replacement_account_id == old_id
    ):
        deny("INVALID_LIFECYCLE", 422)
    with runtime(settings) as conn:
        _, _, preactor = identify(conn, request, settings)
        if preactor["role"] not in ADMIN_ROLES:
            deny("FORBIDDEN")
        old = (
            conn.execute(
                select(account).where(
                    account.c.id == old_id, account.c.role == "institution_user"
                )
            )
            .mappings()
            .one_or_none()
        )
        if not old:
            deny("ACCOUNT_UNAVAILABLE", 404)
        iid = old["institution_id"]
        active = conn.execute(
            select(institution.c.active)
            .where(institution.c.id == iid)
            .with_for_update()
        ).scalar_one()
        new = None
        policy = None
        if replacing:
            new = (
                conn.execute(
                    select(account).where(
                        account.c.id == body.replacement_account_id,
                        account.c.role == "institution_user",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if not new or new["institution_id"] != iid:
                deny("INVALID_REPLACEMENT", 409)
            policy = current_policy(conn, new, lock=True)
        extras = (
            [old_id]
            + ([new["id"]] if new else [])
            + ([policy["verified_by"]] if policy else [])
        )
        ctx = authenticate(
            conn, request, settings, admin=True, csrf=True, extra_account_ids=extras
        )
        old = (
            conn.execute(select(account).where(account.c.id == old_id)).mappings().one()
        )
        if old["status"] != "approved" or old["inactive_at"] is not None:
            deny("ACCOUNT_UNAVAILABLE", 409)
        if new:
            new = (
                conn.execute(select(account).where(account.c.id == new["id"]))
                .mappings()
                .one()
            )
            if (
                new["institution_id"] != iid
                or new["status"] != "pending"
                or new["inactive_at"] is not None
            ):
                deny("INVALID_REPLACEMENT", 409)
            if (
                not active
                or not policy_usable(conn, policy)
                or policy["normalized_domain"] != new["normalized_email"].split("@")[1]
            ):
                deny("DOMAIN_UNCONFIRMED", 409)
        now = clock(conn)
        conn.execute(
            update(account)
            .where(account.c.id == old_id)
            .values(status="inactive", inactive_at=now, updated_at=now)
        )
        sessions, grants = discard_access(conn, old_id, now)
        if new:
            # Never revive an earlier pending-account session/recovery artifact.
            discard_access(conn, new["id"], now)
            conn.execute(
                update(account)
                .where(account.c.id == new["id"])
                .values(
                    status="approved",
                    reviewed_by=ctx["actor"]["id"],
                    reviewed_at=now,
                    approved_at=now,
                    updated_at=now,
                    domain_policy_id=policy["id"],
                    approval_reference=body.approval_reference.strip(),
                    decision_reason=None,
                )
            )
        conn.execute(
            insert(audit_event).values(
                actor_id=ctx["actor"]["id"],
                action="account.replaced" if new else "account.deactivated",
                entity_type="account",
                entity_id=old_id,
                request_id=request.state.request_id,
                changes={
                    "version": 1,
                    "from": "approved",
                    "to": "inactive",
                    "reason": body.reason.strip(),
                    "replacement_account_id": str(new["id"]) if new else None,
                    "revoked_sessions": sessions,
                    "revoked_unused_grants": grants,
                },
            )
        )
        if new:
            conn.execute(
                insert(audit_event).values(
                    actor_id=ctx["actor"]["id"],
                    action="account.approved",
                    entity_type="account",
                    entity_id=new["id"],
                    request_id=request.state.request_id,
                    changes={
                        "version": 1,
                        "from": "pending",
                        "to": "approved",
                        "replaced_account_id": str(old_id),
                        "correspondence_checked": True,
                    },
                )
            )
        return {
            "status": "replaced" if new else "deactivated",
            "request_id": request.state.request_id,
            "revoked_sessions": sessions,
            "revoked_unused_grants": grants,
        }


@router.post("/{account_id}/deactivate")
def deactivate(
    account_id: UUID, body: DeactivateInput, request: Request, settings: SettingsDep
):
    return transition(account_id, body, request, settings, False)


@router.post("/{account_id}/replace")
def replace(
    account_id: UUID, body: ReplaceInput, request: Request, settings: SettingsDep
):
    return transition(account_id, body, request, settings, True)


# Protected read surface for proving unchanged institution-owned plans, not a plan editor.
plans_router = APIRouter(prefix="/api/institutions", tags=["institution plan access"])


@plans_router.get("/{institution_id}/plans")
def plans(institution_id: UUID, request: Request, settings: SettingsDep):
    from backend.auth import require_institution

    with runtime(settings) as conn:
        ctx = authenticate(conn, request, settings)
        require_institution(ctx, institution_id)
        rows = (
            conn.execute(
                select(plan, cycle.c.year)
                .join(cycle, plan.c.cycle_id == cycle.c.id)
                .where(plan.c.institution_id == institution_id)
                .order_by(cycle.c.year, plan.c.id)
            )
            .mappings()
            .all()
        )
        return {
            "items": [
                {
                    "id": str(p["id"]),
                    "year": p["year"],
                    "status": p["status"],
                    "revision": p["revision"],
                    "first_submitted_at": p["first_submitted_at"],
                    "datasets": [
                        {
                            "id": str(item["id"]),
                            "title": item["title"],
                            "position": item["position"],
                        }
                        for item in conn.execute(
                            select(planned_dataset)
                            .where(planned_dataset.c.plan_id == p["id"])
                            .order_by(planned_dataset.c.position, planned_dataset.c.id)
                        ).mappings()
                    ],
                }
                for p in rows
            ]
        }
