"""Public request intake and credential-verified owner status; no login/session."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.access_policy import clean_name, normalize_email, private_domain
from backend.config import Settings, get_settings
from backend.database import DatabaseUnavailable
from backend.models import (
    account,
    audit_event,
    institution,
    institution_email_domain,
    institution_register_version,
)
from backend.passwords import HashBusy, encode_password, verify_password
from backend.store import transaction

router = APIRouter(prefix="/api/access", tags=["access"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Credentials(Input):
    email: str = Field(max_length=254, repr=False)
    password: SecretStr = Field(min_length=15, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        return normalize_email(value)


class AccessRequest(Credentials):
    institution_id: UUID
    name: str = Field(min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def name_shape(cls, value):
        return clean_name(value)


class Receipt(BaseModel):
    institution_name: str
    email: str
    status: Literal["pending"] = "pending"
    domain_review: Literal["matched", "unconfirmed"]
    requested_at: datetime
    request_id: UUID


class OwnerStatus(BaseModel):
    institution_name: str
    email: str
    status: Literal["pending", "approved", "rejected", "deactivated"]
    requested_at: datetime
    reviewed_at: datetime | None
    decision_reason: str | None
    request_id: UUID


def deny(code, status):
    raise HTTPException(status_code=status, detail=code)


class InstitutionChoice(BaseModel):
    id: UUID
    name: str
    synthetic: bool


class InstitutionChoices(BaseModel):
    items: list[InstitutionChoice]
    has_more: bool


@router.get("/institutions", response_model=InstitutionChoices)
def institutions(settings: SettingsDep, q: str = "", limit: int = 50):
    if len(q) > 100 or not 1 <= limit <= 50:
        deny("INVALID_REQUEST", 422)
    try:
        with transaction(settings) as conn:
            stmt = (
                select(
                    institution.c.id,
                    institution.c.name,
                    institution_register_version.c.source_reference,
                )
                .join(
                    institution_register_version,
                    institution.c.register_version_id
                    == institution_register_version.c.id,
                )
                .where(
                    institution.c.active.is_(True),
                    institution_register_version.c.status == "applied",
                )
            )
            if q.strip():
                stmt = stmt.where(
                    institution.c.name.ilike(
                        "%"
                        + q.strip()
                        .replace("!", "!!")
                        .replace("%", "!%")
                        .replace("_", "!_")
                        + "%",
                        escape="!",
                    )
                )
            rows = (
                conn.execute(
                    stmt.order_by(institution.c.name, institution.c.id).limit(limit + 1)
                )
                .mappings()
                .all()
            )
            # Source reference content is private; expose only the synthetic label.
            return {
                "items": [
                    {
                        "id": str(row["id"]),
                        "name": row["name"],
                        "synthetic": "SYNTHETIC" in row["source_reference"].upper(),
                    }
                    for row in rows[:limit]
                ],
                "has_more": len(rows) > limit,
            }
    except (SQLAlchemyError, DatabaseUnavailable, ValueError):
        deny("SERVICE_UNAVAILABLE", 503)


@router.post("/requests", response_model=Receipt, status_code=201)
def request_access(body: AccessRequest, request: Request, settings: SettingsDep):
    domain = body.email.split("@")[1]
    if private_domain(domain):
        deny("PRIVATE_EMAIL_BLOCKED", 422)
    try:
        # Validate institution before costly hashing; never infer affiliation from suffix.
        with transaction(settings) as conn:
            allowed = conn.execute(
                select(institution.c.id)
                .join(
                    institution_register_version,
                    institution.c.register_version_id
                    == institution_register_version.c.id,
                )
                .where(
                    institution.c.id == body.institution_id,
                    institution.c.active.is_(True),
                    institution_register_version.c.status == "applied",
                )
            ).first()
            if not allowed:
                deny("INVALID_INSTITUTION", 422)
        password_hash = encode_password(body.password.get_secret_value())
        with transaction(settings) as conn:
            active = conn.execute(
                select(institution.c.id, institution.c.name)
                .where(
                    institution.c.id == body.institution_id,
                    institution.c.active.is_(True),
                )
                .with_for_update()
            ).first()
            if not active:
                deny("INVALID_INSTITUTION", 422)
            policy = conn.execute(
                select(institution_email_domain.c.id).where(
                    institution_email_domain.c.institution_id == body.institution_id,
                    institution_email_domain.c.normalized_domain == domain,
                    institution_email_domain.c.active.is_(True),
                )
            ).scalar_one_or_none()
            row = conn.execute(
                insert(account)
                .values(
                    institution_id=body.institution_id,
                    role="institution_user",
                    name=body.name,
                    email=body.email,
                    normalized_email=body.email,
                    password_hash=password_hash,
                    status="pending",
                    domain_policy_id=policy,
                )
                .returning(account.c.id, account.c.requested_at)
            ).one()
            conn.execute(
                insert(audit_event).values(
                    actor_id=row.id,
                    action="access.requested",
                    entity_type="account",
                    entity_id=row.id,
                    request_id=request.state.request_id,
                    changes={
                        "version": 1,
                        "status": "pending",
                        "domain_review": "matched" if policy else "unconfirmed",
                    },
                )
            )
            return Receipt(
                institution_name=active.name,
                email=body.email,
                domain_review="matched" if policy else "unconfirmed",
                requested_at=row.requested_at,
                request_id=request.state.request_id,
            )
    except HashBusy:
        deny("TRY_LATER", 429)
    except IntegrityError:
        deny("REQUEST_NOT_ACCEPTED", 409)
    except (SQLAlchemyError, DatabaseUnavailable, ValueError):
        deny("SERVICE_UNAVAILABLE", 503)


@router.post("/status", response_model=OwnerStatus)
def owner_status(body: Credentials, request: Request, settings: SettingsDep):
    try:
        with transaction(settings) as conn:
            row = (
                conn.execute(
                    select(
                        institution.c.name.label("institution_name"),
                        account.c.email,
                        account.c.password_hash,
                        account.c.status,
                        account.c.requested_at,
                        account.c.reviewed_at,
                        account.c.decision_reason,
                        account.c.role,
                    )
                    .join(institution, account.c.institution_id == institution.c.id)
                    .where(account.c.normalized_email == body.email)
                )
                .mappings()
                .one_or_none()
            )
        authenticated = verify_password(
            body.password.get_secret_value(),
            row["password_hash"] if row else "!missing",
        )
        if not authenticated or row["role"] != "institution_user":
            deny("STATUS_UNAVAILABLE", 401)
        return OwnerStatus(
            institution_name=row["institution_name"],
            email=row["email"],
            status="deactivated" if row["status"] == "inactive" else row["status"],
            requested_at=row["requested_at"],
            reviewed_at=row["reviewed_at"],
            decision_reason=row["decision_reason"],
            request_id=request.state.request_id,
        )
    except HashBusy:
        deny("TRY_LATER", 429)
    except (SQLAlchemyError, DatabaseUnavailable, ValueError):
        deny("SERVICE_UNAVAILABLE", 503)
