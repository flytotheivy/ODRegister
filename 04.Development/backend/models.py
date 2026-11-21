"""Layer 1 SQLAlchemy tables and mapped entities. No document/runtime dependency.

Initial definition implements ADR-008/P1-03 physical design. Applied database
changes must use new Alembic revisions; do not rewrite migration snapshots.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import registry

metadata = sa.MetaData(schema="layer1")
mapper_registry = registry(metadata=metadata)

institution_register_version = sa.Table(
    "institution_register_version",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable import version identifier [internal]",
    ),
    sa.Column(
        "source_reference",
        sa.Text(),
        nullable=False,
        comment="Document reference or approved source URL; no uploaded document content [internal]",
    ),
    sa.Column(
        "source_sha256",
        sa.Text(),
        nullable=False,
        comment="Lowercase SHA-256 of source bytes [internal]",
    ),
    sa.Column(
        "received_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Source receipt instant [internal]",
    ),
    sa.Column(
        "imported_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Successful import completion instant [internal]",
    ),
    sa.Column(
        "row_count",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
        comment="Validated accepted source rows; importer reconciles actual rows [internal]",
    ),
    sa.Column(
        "status",
        sa.Text(),
        nullable=False,
        server_default=sa.text("'staged'"),
        comment="staged, applied or failed; applied versions immutable [internal]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_institution_register_version"),
    sa.CheckConstraint(
        "source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_institution_register_version_1"
    ),
    sa.CheckConstraint("row_count >= 0", name="ck_institution_register_version_2"),
    sa.CheckConstraint(
        "status IN ('staged','applied','failed')",
        name="ck_institution_register_version_3",
    ),
    sa.CheckConstraint(
        "(status = 'applied') = (imported_at IS NOT NULL)",
        name="ck_institution_register_version_4",
    ),
    sa.CheckConstraint(
        "length(btrim(source_reference)) > 0", name="ck_institution_register_version_5"
    ),
    comment="Provenance and immutable version of an institution register import",
)


@mapper_registry.mapped
class InstitutionRegisterVersion:
    __table__ = institution_register_version


institution = sa.Table(
    "institution",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable identity independent of name or user replacement [public_id]",
    ),
    sa.Column(
        "register_version_id",
        sa.Uuid(),
        nullable=False,
        comment="Source version for latest attributes [internal]",
    ),
    sa.Column(
        "source_key",
        sa.Text(),
        nullable=True,
        comment="Canonical cross-version source identity; importer must adjudicate missing keys [internal]",
    ),
    sa.Column(
        "name",
        sa.Text(),
        nullable=False,
        comment="Latest official name; exports use cycle snapshot name [internal]",
    ),
    sa.Column(
        "institution_type",
        sa.Text(),
        nullable=True,
        comment="Latest source type code [internal]",
    ),
    sa.Column(
        "institution_level",
        sa.Text(),
        nullable=True,
        comment="Latest source level code [internal]",
    ),
    sa.Column(
        "institution_region",
        sa.Text(),
        nullable=True,
        comment="Latest source region code [internal]",
    ),
    sa.Column(
        "active",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
        comment="Available for future cycle configuration, not historical denominator [internal]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Last service mutation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_institution"),
    sa.UniqueConstraint("source_key", name="uq_institution_1"),
    sa.CheckConstraint("length(btrim(name)) > 0", name="ck_institution_1"),
    sa.CheckConstraint(
        "source_key IS NULL OR length(btrim(source_key)) > 0", name="ck_institution_2"
    ),
    sa.ForeignKeyConstraint(
        ["register_version_id"],
        ["layer1.institution_register_version.id"],
        name="fk_institution_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Stable institution identity and latest register attributes",
)
sa.Index("ix_institution_register", institution.c.register_version_id, unique=False)


@mapper_registry.mapped
class Institution:
    __table__ = institution


cycle = sa.Table(
    "cycle",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable annual cycle identifier [internal]",
    ),
    sa.Column(
        "year",
        sa.Integer(),
        nullable=False,
        comment="Feed year; one cycle per year [public]",
    ),
    sa.Column(
        "opens_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Inclusive opening instant [internal]",
    ),
    sa.Column(
        "closes_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Exclusive closing instant; extensions audited [internal]",
    ),
    sa.Column(
        "timezone",
        sa.Text(),
        nullable=False,
        comment="IANA display zone validated by service; timestamps stored as instants [internal]",
    ),
    sa.Column(
        "licence_text",
        sa.Text(),
        nullable=False,
        comment="Export licence text; external confirmation required for production [public]",
    ),
    sa.Column(
        "licence_url",
        sa.Text(),
        nullable=False,
        comment="Absolute HTTP(S) licence URI; service performs URI validation [public]",
    ),
    sa.Column(
        "revision",
        sa.BigInteger(),
        nullable=False,
        server_default=sa.text("1"),
        comment="Optimistic version for settings and denominator mutations [internal]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Last settings mutation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_cycle"),
    sa.UniqueConstraint("year", name="uq_cycle_1"),
    sa.CheckConstraint("year BETWEEN 2000 AND 9999", name="ck_cycle_1"),
    sa.CheckConstraint("opens_at < closes_at", name="ck_cycle_2"),
    sa.CheckConstraint("revision >= 1", name="ck_cycle_3"),
    sa.CheckConstraint("length(btrim(timezone)) > 0", name="ck_cycle_4"),
    sa.CheckConstraint("length(btrim(licence_text)) > 0", name="ck_cycle_5"),
    sa.CheckConstraint("licence_url ~ '^https?://'", name="ck_cycle_6"),
    comment="Annual collection window and public export licence",
)


@mapper_registry.mapped
class Cycle:
    __table__ = cycle


cycle_institution = sa.Table(
    "cycle_institution",
    metadata,
    sa.Column(
        "cycle_id", sa.Uuid(), nullable=False, comment="Cycle membership key [internal]"
    ),
    sa.Column(
        "institution_id",
        sa.Uuid(),
        nullable=False,
        comment="Stable institution identifier [public]",
    ),
    sa.Column(
        "register_version_id",
        sa.Uuid(),
        nullable=False,
        comment="Source version of this annual snapshot [internal]",
    ),
    sa.Column(
        "name",
        sa.Text(),
        nullable=False,
        comment="Annual official name used by public/internal feeds [public]",
    ),
    sa.Column(
        "institution_type",
        sa.Text(),
        nullable=True,
        comment="Annual institution type code [public]",
    ),
    sa.Column(
        "institution_level",
        sa.Text(),
        nullable=True,
        comment="Annual institution level code [public]",
    ),
    sa.Column(
        "institution_region",
        sa.Text(),
        nullable=True,
        comment="Annual institution region code [public]",
    ),
    sa.Column(
        "snapshotted_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Snapshot capture instant [internal]",
    ),
    sa.PrimaryKeyConstraint("cycle_id", "institution_id", name="pk_cycle_institution"),
    sa.CheckConstraint("length(btrim(name)) > 0", name="ck_cycle_institution_1"),
    sa.ForeignKeyConstraint(
        ["cycle_id"],
        ["layer1.cycle.id"],
        name="fk_cycle_institution_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["institution_id"],
        ["layer1.institution.id"],
        name="fk_cycle_institution_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["register_version_id"],
        ["layer1.institution_register_version.id"],
        name="fk_cycle_institution_3",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Explicit annual denominator and institution attribute snapshot",
)
sa.Index("ix_ci_institution", cycle_institution.c.institution_id, unique=False)
sa.Index("ix_ci_register", cycle_institution.c.register_version_id, unique=False)
sa.Index(
    "ix_ci_group",
    cycle_institution.c.cycle_id,
    cycle_institution.c.institution_type,
    cycle_institution.c.institution_level,
    cycle_institution.c.institution_region,
    unique=False,
)


@mapper_registry.mapped
class CycleInstitution:
    __table__ = cycle_institution


account = sa.Table(
    "account",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable account identifier [internal]",
    ),
    sa.Column(
        "institution_id",
        sa.Uuid(),
        nullable=True,
        comment="Mandatory only for institution_user; administrative accounts have no owning institution [internal_feed]",
    ),
    sa.Column(
        "role",
        sa.Text(),
        nullable=False,
        comment="institution_user, ADMIN_MPALSG or ADMIN_ITE [internal_feed]",
    ),
    sa.Column(
        "name",
        sa.Text(),
        nullable=False,
        comment="Applicant display name; not public [restricted]",
    ),
    sa.Column(
        "email",
        sa.Text(),
        nullable=False,
        comment="Original institution email; protected optional email profile only [internal_feed]",
    ),
    sa.Column(
        "normalized_email",
        sa.Text(),
        nullable=False,
        comment="trimmed lowercase email for uniqueness; validated email syntax and IDNA domain by service [restricted]",
    ),
    sa.Column(
        "password_hash",
        sa.Text(),
        nullable=False,
        comment="Password hash including algorithm metadata; never exported [secret_hash]",
    ),
    sa.Column(
        "status",
        sa.Text(),
        nullable=False,
        server_default=sa.text("'pending'"),
        comment="pending, approved, rejected or inactive [internal_feed]",
    ),
    sa.Column(
        "requested_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Request receipt for registration indicator, including pending/rejected [internal]",
    ),
    sa.Column(
        "reviewed_by",
        sa.Uuid(),
        nullable=True,
        comment="Reviewing administrator; approved institution user cannot self-review [restricted]",
    ),
    sa.Column(
        "reviewed_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Most recent approval or rejection review instant [restricted]",
    ),
    sa.Column(
        "approved_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Approval instant retained after deactivation [restricted]",
    ),
    sa.Column(
        "inactive_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Deactivation instant [restricted]",
    ),
    sa.Column(
        "decision_reason",
        sa.Text(),
        nullable=True,
        comment="Review reason; required for rejection [restricted]",
    ),
    sa.Column(
        "approval_reference",
        sa.Text(),
        nullable=True,
        comment="Restricted official correspondence reference; no document upload [restricted]",
    ),
    sa.Column(
        "domain_policy_id",
        sa.Uuid(),
        nullable=True,
        comment="Exact institutional domain policy used at approval [restricted]",
    ),
    sa.Column(
        "must_change_password",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
        comment="Force password change after manual recovery [internal]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Last account mutation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_account"),
    sa.UniqueConstraint("normalized_email", name="uq_account_1"),
    sa.CheckConstraint(
        "role IN ('institution_user','ADMIN_MPALSG','ADMIN_ITE')", name="ck_account_1"
    ),
    sa.CheckConstraint(
        "(role = 'institution_user') = (institution_id IS NOT NULL)",
        name="ck_account_2",
    ),
    sa.CheckConstraint(
        "status IN ('pending','approved','rejected','inactive')", name="ck_account_3"
    ),
    sa.CheckConstraint(
        "normalized_email = lower(btrim(email)) AND length(normalized_email) > 3",
        name="ck_account_4",
    ),
    sa.CheckConstraint(
        "length(btrim(name)) > 0 AND length(password_hash) > 0", name="ck_account_5"
    ),
    sa.CheckConstraint(
        "(status = 'inactive') = (inactive_at IS NOT NULL)", name="ck_account_6"
    ),
    sa.CheckConstraint(
        "status <> 'approved' OR approved_at IS NOT NULL", name="ck_account_7"
    ),
    sa.CheckConstraint(
        "status NOT IN ('approved','rejected') OR role <> 'institution_user' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by <> id)",
        name="ck_account_8",
    ),
    sa.CheckConstraint(
        "status <> 'approved' OR role <> 'institution_user' OR (domain_policy_id IS NOT NULL AND approval_reference IS NOT NULL AND length(btrim(approval_reference)) > 0)",
        name="ck_account_9",
    ),
    sa.CheckConstraint(
        "status <> 'rejected' OR (decision_reason IS NOT NULL AND length(btrim(decision_reason)) > 0)",
        name="ck_account_10",
    ),
    sa.ForeignKeyConstraint(
        ["institution_id"],
        ["layer1.institution.id"],
        name="fk_account_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["reviewed_by"],
        ["layer1.account.id"],
        name="fk_account_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["institution_id", "domain_policy_id"],
        [
            "layer1.institution_email_domain.institution_id",
            "layer1.institution_email_domain.id",
        ],
        name="fk_account_3",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Institution request and administrator account; no mailbox verification",
)
sa.Index(
    "uq_account_active_approved",
    account.c.institution_id,
    unique=True,
    postgresql_where=sa.text(
        "role = 'institution_user' AND status = 'approved' AND inactive_at IS NULL"
    ),
)
sa.Index("ix_account_institution", account.c.institution_id, unique=False)
sa.Index("ix_account_reviewed_by", account.c.reviewed_by, unique=False)
sa.Index(
    "ix_account_policy",
    account.c.institution_id,
    account.c.domain_policy_id,
    unique=False,
)
sa.Index("ix_account_queue", account.c.status, account.c.requested_at, unique=False)


@mapper_registry.mapped
class Account:
    __table__ = account


institution_email_domain = sa.Table(
    "institution_email_domain",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable policy version id; approved account retains reference [internal]",
    ),
    sa.Column(
        "institution_id",
        sa.Uuid(),
        nullable=False,
        comment="Institution allowed to use exactly this domain [internal]",
    ),
    sa.Column(
        "normalized_domain",
        sa.Text(),
        nullable=False,
        comment="Lowercase IDNA ASCII domain, no wildcard, suffix matching or @ [restricted]",
    ),
    sa.Column(
        "active",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
        comment="Policy currently eligible for approval [internal]",
    ),
    sa.Column(
        "verified_by",
        sa.Uuid(),
        nullable=False,
        comment="Administrator who checked the official domain list [restricted]",
    ),
    sa.Column(
        "verified_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Manual policy validation instant; not mailbox verification [restricted]",
    ),
    sa.Column(
        "evidence_reference",
        sa.Text(),
        nullable=False,
        comment="Restricted official source/correspondence reference [restricted]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_institution_email_domain"),
    sa.UniqueConstraint("institution_id", "id", name="uq_institution_email_domain_1"),
    sa.CheckConstraint(
        "normalized_domain = lower(btrim(normalized_domain))",
        name="ck_institution_email_domain_1",
    ),
    sa.CheckConstraint(
        "normalized_domain ~ '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$' AND position('.' in normalized_domain) > 0",
        name="ck_institution_email_domain_2",
    ),
    sa.CheckConstraint(
        "length(btrim(evidence_reference)) > 0", name="ck_institution_email_domain_3"
    ),
    sa.ForeignKeyConstraint(
        ["institution_id"],
        ["layer1.institution.id"],
        name="fk_institution_email_domain_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["verified_by"],
        ["layer1.account.id"],
        name="fk_institution_email_domain_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Versioned exact-domain policy with official evidence and reviewer",
)
sa.Index(
    "uq_domain_active",
    institution_email_domain.c.institution_id,
    institution_email_domain.c.normalized_domain,
    unique=True,
    postgresql_where=sa.text("active"),
)
sa.Index("ix_domain_reviewer", institution_email_domain.c.verified_by, unique=False)


@mapper_registry.mapped
class InstitutionEmailDomain:
    __table__ = institution_email_domain


session = sa.Table(
    "session",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Session identity [internal]",
    ),
    sa.Column(
        "account_id",
        sa.Uuid(),
        nullable=False,
        comment="Owning account checked on every authenticated request [restricted]",
    ),
    sa.Column(
        "token_hash",
        sa.Text(),
        nullable=False,
        comment="SHA-256 digest of high entropy random session token [secret_hash]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Session creation instant [internal]",
    ),
    sa.Column(
        "last_seen_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Last accepted activity [internal]",
    ),
    sa.Column(
        "idle_expires_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Sliding expiry never beyond absolute expiry [internal]",
    ),
    sa.Column(
        "absolute_expires_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Non-sliding hard expiry [internal]",
    ),
    sa.Column(
        "revoked_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Explicit invalidation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_session"),
    sa.UniqueConstraint("token_hash", name="uq_session_1"),
    sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_session_1"),
    sa.CheckConstraint(
        "created_at <= last_seen_at AND last_seen_at < idle_expires_at AND idle_expires_at <= absolute_expires_at",
        name="ck_session_2",
    ),
    sa.CheckConstraint(
        "revoked_at IS NULL OR revoked_at >= created_at", name="ck_session_3"
    ),
    sa.ForeignKeyConstraint(
        ["account_id"],
        ["layer1.account.id"],
        name="fk_session_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Shared server sessions; token stored as digest only",
)
sa.Index("ix_session_account", session.c.account_id, unique=False)
sa.Index("ix_session_expiry", session.c.absolute_expires_at, unique=False)


@mapper_registry.mapped
class Session:
    __table__ = session


account_recovery_grant = sa.Table(
    "account_recovery_grant",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Recovery grant identifier [internal]",
    ),
    sa.Column(
        "account_id", sa.Uuid(), nullable=False, comment="Target account [restricted]"
    ),
    sa.Column(
        "issued_by",
        sa.Uuid(),
        nullable=False,
        comment="Authorised issuing administrator [restricted]",
    ),
    sa.Column(
        "token_hash",
        sa.Text(),
        nullable=False,
        comment="SHA-256 of high entropy recovery token; never logged [secret_hash]",
    ),
    sa.Column(
        "issued_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Grant creation instant [internal]",
    ),
    sa.Column(
        "expires_at",
        sa.DateTime(timezone=True),
        nullable=False,
        comment="Finite expiration, duration configured by approved policy [internal]",
    ),
    sa.Column(
        "used_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Atomic one-use redemption instant [internal]",
    ),
    sa.Column(
        "revoked_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Explicit revocation instant [internal]",
    ),
    sa.Column(
        "identity_check_reference",
        sa.Text(),
        nullable=False,
        comment="Evidence reference for manual identity check, no identity document body [restricted]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_account_recovery_grant"),
    sa.UniqueConstraint("token_hash", name="uq_account_recovery_grant_1"),
    sa.CheckConstraint(
        "token_hash ~ '^[0-9a-f]{64}$'", name="ck_account_recovery_grant_1"
    ),
    sa.CheckConstraint("issued_at < expires_at", name="ck_account_recovery_grant_2"),
    sa.CheckConstraint(
        "used_at IS NULL OR (used_at >= issued_at AND used_at < expires_at)",
        name="ck_account_recovery_grant_3",
    ),
    sa.CheckConstraint(
        "revoked_at IS NULL OR revoked_at >= issued_at",
        name="ck_account_recovery_grant_4",
    ),
    sa.CheckConstraint(
        "length(btrim(identity_check_reference)) > 0",
        name="ck_account_recovery_grant_5",
    ),
    sa.ForeignKeyConstraint(
        ["account_id"],
        ["layer1.account.id"],
        name="fk_account_recovery_grant_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["issued_by"],
        ["layer1.account.id"],
        name="fk_account_recovery_grant_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Manual one-use recovery; delivery channel remains externally agreed",
)
sa.Index("ix_recovery_account", account_recovery_grant.c.account_id, unique=False)
sa.Index("ix_recovery_issuer", account_recovery_grant.c.issued_by, unique=False)
sa.Index("ix_recovery_expiry", account_recovery_grant.c.expires_at, unique=False)


@mapper_registry.mapped
class AccountRecoveryGrant:
    __table__ = account_recovery_grant


theme = sa.Table(
    "theme",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Theme identity [internal]",
    ),
    sa.Column("code", sa.Text(), nullable=False, comment="Stable export code [public]"),
    sa.Column(
        "uri",
        sa.Text(),
        nullable=False,
        comment="Stable absolute HTTP(S) URI; custom theme URI needs approved source [public]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_theme"),
    sa.UniqueConstraint("code", name="uq_theme_1"),
    sa.UniqueConstraint("uri", name="uq_theme_2"),
    sa.CheckConstraint("length(btrim(code)) > 0", name="ck_theme_1"),
    sa.CheckConstraint("uri ~ '^https?://'", name="ck_theme_2"),
    comment="Stable EU/custom theme identity",
)


@mapper_registry.mapped
class Theme:
    __table__ = theme


theme_translation = sa.Table(
    "theme_translation",
    metadata,
    sa.Column("theme_id", sa.Uuid(), nullable=False, comment="Theme key [internal]"),
    sa.Column(
        "locale", sa.Text(), nullable=False, comment="en, sr-Latn or sr-Cyrl [public]"
    ),
    sa.Column(
        "label",
        sa.Text(),
        nullable=False,
        comment="Nonblank theme label for locale [public]",
    ),
    sa.PrimaryKeyConstraint("theme_id", "locale", name="pk_theme_translation"),
    sa.CheckConstraint(
        "locale IN ('en','sr-Latn','sr-Cyrl')", name="ck_theme_translation_1"
    ),
    sa.CheckConstraint("length(btrim(label)) > 0", name="ck_theme_translation_2"),
    sa.ForeignKeyConstraint(
        ["theme_id"],
        ["layer1.theme.id"],
        name="fk_theme_translation_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Three product-language labels; institution free text is not translated",
)


@mapper_registry.mapped
class ThemeTranslation:
    __table__ = theme_translation


cycle_theme = sa.Table(
    "cycle_theme",
    metadata,
    sa.Column(
        "cycle_id", sa.Uuid(), nullable=False, comment="Annual cycle key [internal]"
    ),
    sa.Column("theme_id", sa.Uuid(), nullable=False, comment="Theme key [internal]"),
    sa.Column(
        "active",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
        comment="Eligible for new/changed items; existing submitted reference is retained [internal]",
    ),
    sa.PrimaryKeyConstraint("cycle_id", "theme_id", name="pk_cycle_theme"),
    sa.ForeignKeyConstraint(
        ["cycle_id"],
        ["layer1.cycle.id"],
        name="fk_cycle_theme_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["theme_id"],
        ["layer1.theme.id"],
        name="fk_cycle_theme_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Theme eligibility in an annual cycle",
)
sa.Index("ix_cycle_theme_theme", cycle_theme.c.theme_id, unique=False)


@mapper_registry.mapped
class CycleTheme:
    __table__ = cycle_theme


plan = sa.Table(
    "plan",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable plan identifier [public]",
    ),
    sa.Column(
        "institution_id",
        sa.Uuid(),
        nullable=False,
        comment="Owning institution; never reassigned to a user [public]",
    ),
    sa.Column(
        "cycle_id",
        sa.Uuid(),
        nullable=False,
        comment="Annual cycle; owner pair must be in annual denominator [internal]",
    ),
    sa.Column(
        "status",
        sa.Text(),
        nullable=False,
        server_default=sa.text("'draft'"),
        comment="draft or submitted; no mandatory review stage [internal_feed]",
    ),
    sa.Column(
        "revision",
        sa.BigInteger(),
        nullable=False,
        server_default=sa.text("1"),
        comment="Monotonic version for optimistic compare-and-swap [internal]",
    ),
    sa.Column(
        "first_submitted_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Immutable first submit instant; no draft exposure [public]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Last committed plan mutation instant, never an incomplete intermediate save [public]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_plan"),
    sa.UniqueConstraint("institution_id", "cycle_id", name="uq_plan_1"),
    sa.CheckConstraint("status IN ('draft','submitted')", name="ck_plan_1"),
    sa.CheckConstraint("revision >= 1", name="ck_plan_2"),
    sa.CheckConstraint(
        "(status = 'submitted') = (first_submitted_at IS NOT NULL)", name="ck_plan_3"
    ),
    sa.CheckConstraint("updated_at >= created_at", name="ck_plan_4"),
    sa.CheckConstraint(
        "first_submitted_at IS NULL OR (first_submitted_at >= created_at AND updated_at >= first_submitted_at)",
        name="ck_plan_5",
    ),
    sa.ForeignKeyConstraint(
        ["cycle_id", "institution_id"],
        [
            "layer1.cycle_institution.cycle_id",
            "layer1.cycle_institution.institution_id",
        ],
        name="fk_plan_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Institution-owned annual plan, independent of account replacement",
)
sa.Index(
    "ix_plan_public",
    plan.c.cycle_id,
    plan.c.status,
    plan.c.institution_id,
    plan.c.id,
    unique=False,
)


@mapper_registry.mapped
class Plan:
    __table__ = plan


planned_dataset = sa.Table(
    "planned_dataset",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Stable item identifier across edits [public]",
    ),
    sa.Column(
        "plan_id",
        sa.Uuid(),
        nullable=False,
        comment="Parent institution-owned plan [internal]",
    ),
    sa.Column(
        "position",
        sa.Integer(),
        nullable=False,
        comment="Positive item order; deferred uniqueness supports reorder in one transaction [internal]",
    ),
    sa.Column(
        "title",
        sa.Text(),
        nullable=True,
        comment="Dataset title; NULL allowed only until submission [public]",
    ),
    sa.Column(
        "description",
        sa.Text(),
        nullable=True,
        comment="Optional original free-text description [public]",
    ),
    sa.Column(
        "responsible_department",
        sa.Text(),
        nullable=True,
        comment="Optional department; no personal contact fields [public]",
    ),
    sa.Column(
        "planned_quarter",
        sa.SmallInteger(),
        nullable=True,
        comment="Optional quarter 1 to 4 [public]",
    ),
    sa.Column(
        "theme_id",
        sa.Uuid(),
        nullable=True,
        comment="NULL permitted in draft; eligibility checked against parent cycle [internal]",
    ),
    sa.Column(
        "personal_data_confirmation",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
        comment="True only after confirmation of current item content [public]",
    ),
    sa.Column(
        "confirmed_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="Confirmation instant for current content; cleared by content mutation [internal]",
    ),
    sa.Column(
        "confirmed_by",
        sa.Uuid(),
        nullable=True,
        comment="Account confirming content; institution checked by service [restricted]",
    ),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Creation instant [internal]",
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Last item mutation instant [internal]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_planned_dataset"),
    sa.UniqueConstraint(
        "plan_id",
        "position",
        name="uq_planned_dataset_order",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint("position > 0", name="ck_planned_dataset_1"),
    sa.CheckConstraint(
        "planned_quarter IS NULL OR planned_quarter BETWEEN 1 AND 4",
        name="ck_planned_dataset_2",
    ),
    sa.CheckConstraint(
        "title IS NULL OR length(btrim(title)) > 0", name="ck_planned_dataset_3"
    ),
    sa.CheckConstraint(
        "(personal_data_confirmation AND confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL) OR (NOT personal_data_confirmation AND confirmed_at IS NULL AND confirmed_by IS NULL)",
        name="ck_planned_dataset_4",
    ),
    sa.ForeignKeyConstraint(
        ["plan_id"],
        ["layer1.plan.id"],
        name="fk_planned_dataset_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["theme_id"],
        ["layer1.theme.id"],
        name="fk_planned_dataset_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["confirmed_by"],
        ["layer1.account.id"],
        name="fk_planned_dataset_3",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Ordered proposed dataset item; incomplete draft is allowed",
)
sa.Index(
    "ix_dataset_theme",
    planned_dataset.c.theme_id,
    planned_dataset.c.plan_id,
    unique=False,
)
sa.Index("ix_dataset_confirmer", planned_dataset.c.confirmed_by, unique=False)


@mapper_registry.mapped
class PlannedDataset:
    __table__ = planned_dataset


plan_revision = sa.Table(
    "plan_revision",
    metadata,
    sa.Column("plan_id", sa.Uuid(), nullable=False, comment="Plan identity [internal]"),
    sa.Column(
        "revision",
        sa.BigInteger(),
        nullable=False,
        comment="Exact committed plan revision [internal]",
    ),
    sa.Column(
        "saved_by",
        sa.Uuid(),
        nullable=False,
        comment="Authenticated institution actor [restricted]",
    ),
    sa.Column(
        "saved_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Committed revision creation instant [internal]",
    ),
    sa.Column(
        "snapshot",
        JSONB(),
        nullable=False,
        comment="Versioned plan/item snapshot; no account/email/hash/token fields [restricted]",
    ),
    sa.PrimaryKeyConstraint("plan_id", "revision", name="pk_plan_revision"),
    sa.CheckConstraint("revision >= 1", name="ck_plan_revision_1"),
    sa.CheckConstraint("jsonb_typeof(snapshot) = 'object'", name="ck_plan_revision_2"),
    sa.ForeignKeyConstraint(
        ["plan_id"],
        ["layer1.plan.id"],
        name="fk_plan_revision_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    sa.ForeignKeyConstraint(
        ["saved_by"],
        ["layer1.account.id"],
        name="fk_plan_revision_2",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Immutable committed business snapshot; restricted and not an export",
)
sa.Index("ix_revision_saver", plan_revision.c.saved_by, unique=False)


@mapper_registry.mapped
class PlanRevision:
    __table__ = plan_revision


audit_event = sa.Table(
    "audit_event",
    metadata,
    sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        comment="Audit identity [internal]",
    ),
    sa.Column(
        "actor_id",
        sa.Uuid(),
        nullable=True,
        comment="Authenticated actor or NULL for explicitly named system operation [restricted]",
    ),
    sa.Column(
        "action",
        sa.Text(),
        nullable=False,
        comment="Allowlisted action code; never raw request path or credentials [restricted]",
    ),
    sa.Column(
        "entity_type",
        sa.Text(),
        nullable=False,
        comment="Allowlisted logical entity type [restricted]",
    ),
    sa.Column(
        "entity_id",
        sa.Uuid(),
        nullable=True,
        comment="Logical target id; polymorphic target is not a physical FK [restricted]",
    ),
    sa.Column(
        "occurred_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        comment="Audit creation instant [internal]",
    ),
    sa.Column(
        "request_id",
        sa.Uuid(),
        nullable=False,
        comment="Server generated correlation id, no client secret [internal]",
    ),
    sa.Column(
        "changes",
        JSONB(),
        nullable=False,
        server_default=sa.text("'{\"version\": 1}'::jsonb"),
        comment="Allowlisted change summary with redaction; no passwords, hashes, tokens or raw request bodies [restricted]",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_audit_event"),
    sa.CheckConstraint(
        "length(btrim(action)) > 0 AND length(btrim(entity_type)) > 0",
        name="ck_audit_event_1",
    ),
    sa.CheckConstraint("jsonb_typeof(changes) = 'object'", name="ck_audit_event_2"),
    sa.ForeignKeyConstraint(
        ["actor_id"],
        ["layer1.account.id"],
        name="fk_audit_event_1",
        ondelete="RESTRICT",
        use_alter=True,
    ),
    comment="Append-only allowlisted administrative and security audit",
)
sa.Index("ix_audit_time", audit_event.c.occurred_at, unique=False)
sa.Index(
    "ix_audit_entity",
    audit_event.c.entity_type,
    audit_event.c.entity_id,
    audit_event.c.occurred_at,
    unique=False,
)
sa.Index(
    "ix_audit_actor", audit_event.c.actor_id, audit_event.c.occurred_at, unique=False
)
sa.Index("ix_audit_request", audit_event.c.request_id, unique=False)


@mapper_registry.mapped
class AuditEvent:
    __table__ = audit_event
