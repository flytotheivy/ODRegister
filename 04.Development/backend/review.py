"""Administrator-only approval/rejection with exact policy and atomic audit."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, or_, select, update

from backend.access_policy import private_domain
from backend.auth import (
    ADMIN_ROLES,
    SettingsDep,
    authenticate,
    clock,
    deny,
    identify,
    runtime,
    usable,
)
from backend.models import (
    account,
    audit_event,
    institution,
)
from backend.models import (
    institution_email_domain as domain,
)

router = APIRouter(prefix="/api/admin", tags=["administrator review"])


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    decision: Literal["approved", "rejected"]
    correspondence_checked: bool = False
    approval_reference: str = Field(default="", max_length=300)
    reason: str = Field(default="", max_length=500)


def current_policy(conn, target, *, lock=False):
    email_domain = target["normalized_email"].split("@")[1]
    if private_domain(email_domain):
        return None
    stmt = select(domain).where(
        domain.c.institution_id == target["institution_id"],
        domain.c.normalized_domain == email_domain,
        domain.c.active.is_(True),
    )
    if lock:
        stmt = stmt.with_for_update()
    return conn.execute(stmt).mappings().one_or_none()


def policy_usable(conn, policy):
    if not policy:
        return False
    verifier = (
        conn.execute(select(account).where(account.c.id == policy["verified_by"]))
        .mappings()
        .one_or_none()
    )
    return verifier is not None and usable(verifier) and verifier["role"] in ADMIN_ROLES


@router.get("/accounts")
def accounts(
    request: Request,
    settings: SettingsDep,
    status: Literal[
        "pending", "approved", "rejected", "deactivated", "all"
    ] = "pending",
    q: str = "",
    limit: int = 50,
    institution_id: UUID | None = None,
):
    if len(q) > 100 or not 1 <= limit <= 50:
        deny("INVALID_REQUEST", 422)
    with runtime(settings) as conn:
        authenticate(conn, request, settings, admin=True)
        reviewer = account.alias("reviewer")
        stmt = (
            select(
                account,
                reviewer.c.name.label("reviewer_name"),
                institution.c.name.label("institution_name"),
                institution.c.active.label("institution_active"),
            )
            .join(institution, account.c.institution_id == institution.c.id)
            .outerjoin(reviewer, account.c.reviewed_by == reviewer.c.id)
            .where(account.c.role == "institution_user")
        )
        if institution_id is not None:
            stmt = stmt.where(account.c.institution_id == institution_id)
        if status != "all":
            stmt = stmt.where(
                account.c.status == ("inactive" if status == "deactivated" else status)
            )
        if q.strip():
            pattern = (
                "%"
                + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
                + "%"
            )
            stmt = stmt.where(
                or_(
                    account.c.name.ilike(pattern, escape="!"),
                    account.c.normalized_email.ilike(pattern, escape="!"),
                    institution.c.name.ilike(pattern, escape="!"),
                )
            )
        rows = (
            conn.execute(
                stmt.order_by(account.c.requested_at, account.c.id).limit(limit + 1)
            )
            .mappings()
            .all()
        )
        counts = {
            key: conn.execute(
                select(func.count())
                .select_from(account)
                .where(account.c.role == "institution_user", account.c.status == key)
            ).scalar_one()
            for key in ("pending", "approved", "rejected", "inactive")
        }
        items = []
        for row in rows[:limit]:
            policy = current_policy(conn, row)
            good = policy_usable(conn, policy)
            items.append(
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "email": row["email"],
                    "institution_id": str(row["institution_id"]),
                    "institution_name": row["institution_name"],
                    "status": "deactivated"
                    if row["status"] == "inactive"
                    else row["status"],
                    "requested_at": row["requested_at"],
                    "reviewed_at": row["reviewed_at"],
                    "reviewed_by": str(row["reviewed_by"])
                    if row["reviewed_by"]
                    else None,
                    "reviewer_name": row["reviewer_name"],
                    "approval_reference": row["approval_reference"],
                    "decision_reason": row["decision_reason"],
                    "institution_active": row["institution_active"],
                    "domain_review": "matched" if good else "unconfirmed",
                    "domain_policy": {
                        "domain": policy["normalized_domain"],
                        "verified_at": policy["verified_at"],
                        "evidence_reference": policy["evidence_reference"],
                    }
                    if good
                    else None,
                }
            )
        return {
            "items": items,
            "has_more": len(rows) > limit,
            "counts": {
                "pending": counts["pending"],
                "approved": counts["approved"],
                "rejected": counts["rejected"],
                "deactivated": counts["inactive"],
            },
        }


@router.post("/accounts/{account_id}/review")
def review(
    account_id: UUID, body: ReviewInput, request: Request, settings: SettingsDep
):
    if body.decision == "approved" and (
        not body.correspondence_checked or not body.approval_reference.strip()
    ):
        deny("INVALID_REVIEW", 422)
    if body.decision == "rejected" and not body.reason.strip():
        deny("INVALID_REVIEW", 422)
    with runtime(settings) as conn:
        _, _, preactor = identify(conn, request, settings)
        if preactor["role"] not in ADMIN_ROLES or not usable(preactor):
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
        iid = target["institution_id"]
        active = conn.execute(
            select(institution.c.active)
            .where(institution.c.id == iid)
            .with_for_update()
        ).scalar_one()
        policy = current_policy(conn, target, lock=True)
        extras = [target["id"]] + ([policy["verified_by"]] if policy else [])
        ctx = authenticate(
            conn, request, settings, admin=True, csrf=True, extra_account_ids=extras
        )
        target = (
            conn.execute(select(account).where(account.c.id == account_id))
            .mappings()
            .one()
        )
        if target["id"] == ctx["actor"]["id"] or target["status"] != "pending":
            deny("ACCOUNT_UNAVAILABLE", 409)
        now = clock(conn)
        values = {
            "status": body.decision,
            "reviewed_by": ctx["actor"]["id"],
            "reviewed_at": now,
            "updated_at": now,
            "decision_reason": body.reason.strip() or None,
        }
        if body.decision == "approved":
            if not active or not policy_usable(conn, policy):
                deny("DOMAIN_UNCONFIRMED", 409)
            other = conn.execute(
                select(account.c.id).where(
                    account.c.institution_id == iid,
                    account.c.role == "institution_user",
                    account.c.status == "approved",
                    account.c.inactive_at.is_(None),
                )
            ).first()
            if other:
                deny("INSTITUTION_HAS_APPROVED_ACCOUNT", 409)
            values.update(
                approved_at=now,
                domain_policy_id=policy["id"],
                approval_reference=body.approval_reference.strip(),
            )
        conn.execute(update(account).where(account.c.id == account_id).values(**values))
        conn.execute(
            insert(audit_event).values(
                actor_id=ctx["actor"]["id"],
                action="account." + body.decision,
                entity_type="account",
                entity_id=account_id,
                request_id=request.state.request_id,
                changes={
                    "version": 1,
                    "from": "pending",
                    "to": body.decision,
                    "correspondence_checked": body.correspondence_checked,
                },
            )
        )
        return {
            "status": body.decision,
            "reviewed_at": now,
            "request_id": request.state.request_id,
        }
