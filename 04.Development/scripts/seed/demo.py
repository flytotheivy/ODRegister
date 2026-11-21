"""Deterministic demo-v1. No working passwords, mail, uploaded data or official claims."""

from datetime import UTC, datetime

from psycopg import sql

from backend.models import metadata
from scripts.db.common import DEV
from scripts.seed.core import (
    ImportRejected,
    identity,
    insert_immutable,
    load_json,
    nonproduction,
    verify_existing,
)
from scripts.seed.themes import catalog
from scripts.seed.themes import install as install_themes

VERSION = "demo-v1"
AT = datetime(2026, 11, 10, tzinfo=UTC)
START = datetime(2026, 11, 1, tzinfo=UTC)
END = datetime(2027, 3, 1, tzinfo=UTC)


def did(key):
    return identity(VERSION + ":" + key)


def rows():
    _, sha = load_json(DEV / "test-data/seed/demo-expectations.v1.json")
    result = {t.name: [] for t in metadata.tables.values()}
    result["institution_register_version"] = [
        {
            "id": did("register"),
            "source_reference": "SYNTHETIC demo-v1; not an official register",
            "source_sha256": sha,
            "received_at": AT,
            "imported_at": AT,
            "row_count": 7,
            "status": "applied",
        }
    ]
    result["cycle"] = [
        {
            "id": did("cycle"),
            "year": 2027,
            "opens_at": START,
            "closes_at": END,
            "timezone": "Europe/Belgrade",
            "licence_text": "SYNTHETIC DEMO ONLY; not an official licence",
            "licence_url": "https://example.invalid/demo-licence",
        }
    ]
    for i in range(1, 8):
        key = "i" + str(i)
        iid = did(key)
        attrs = {
            "name": "SYNTHETIC INSTITUTION " + str(i),
            "institution_type": "synthetic_ministry" if i % 2 else "synthetic_local",
            "institution_level": "national" if i % 2 else "local",
            "institution_region": "synthetic_region_" + str(i % 2),
        }
        result["institution"].append(
            dict(
                id=iid,
                register_version_id=did("register"),
                source_key=VERSION + ":" + key,
                **attrs,
            )
        )
        result["cycle_institution"].append(
            dict(
                cycle_id=did("cycle"),
                institution_id=iid,
                register_version_id=did("register"),
                **attrs,
            )
        )
        result["institution_email_domain"].append(
            {
                "id": did("domain:" + key),
                "institution_id": iid,
                "normalized_domain": key + ".agency.example.invalid",
                "active": True,
                "verified_by": did("admin_m"),
                "verified_at": AT,
                "evidence_reference": "SYNTHETIC source; not authorised for production",
            }
        )
    for key, role in [("admin_m", "ADMIN_MPALSG"), ("admin_i", "ADMIN_ITE")]:
        result["account"].append(
            {
                "id": did(key),
                "institution_id": None,
                "role": role,
                "name": "SYNTHETIC " + role,
                "email": key + "@example.invalid",
                "normalized_email": key + "@example.invalid",
                "password_hash": "!disabled:synthetic-fixture",
                "status": "approved",
                "approved_at": AT,
            }
        )
    for key, status in [
        ("i1", "approved"),
        ("i2", "approved"),
        ("i3", "pending"),
        ("i4", "rejected"),
        ("i7", "approved"),
    ]:
        reviewed = status != "pending"
        approved = status == "approved"
        result["account"].append(
            {
                "id": did("account:" + key),
                "institution_id": did(key),
                "role": "institution_user",
                "name": "SYNTHETIC " + key,
                "email": "user@" + key + ".agency.example.invalid",
                "normalized_email": "user@" + key + ".agency.example.invalid",
                "password_hash": "!disabled:synthetic-fixture",
                "status": status,
                "requested_at": START,
                "reviewed_by": did("admin_m") if reviewed else None,
                "reviewed_at": AT if reviewed else None,
                "approved_at": AT if approved else None,
                "domain_policy_id": did("domain:" + key) if approved else None,
                "approval_reference": "SYNTHETIC correspondence" if approved else None,
                "decision_reason": "SYNTHETIC rejection"
                if status == "rejected"
                else None,
            }
        )
    for key, status in [("i1", "submitted"), ("i2", "draft"), ("i7", "draft")]:
        result["plan"].append(
            {
                "id": did("plan:" + key),
                "institution_id": did(key),
                "cycle_id": did("cycle"),
                "status": status,
                "revision": 1,
                "first_submitted_at": AT if status == "submitted" else None,
                "created_at": START,
                "updated_at": AT,
            }
        )
    for key, pos, title, theme, confirmed in [
        ("i1", 1, "SYNTHETIC public transport stops", "TRAN", True),
        ("i1", 2, "SYNTHETIC budget programmes", "ECON", True),
        ("i2", 1, None, None, False),
    ]:
        result["planned_dataset"].append(
            {
                "id": did("item:" + key + ":" + str(pos)),
                "plan_id": did("plan:" + key),
                "position": pos,
                "title": title,
                "theme_id": identity("theme:" + theme) if theme else None,
                "personal_data_confirmation": confirmed,
                "confirmed_by": did("account:" + key) if confirmed else None,
                "confirmed_at": AT if confirmed else None,
            }
        )
    for key in ("i1", "i2", "i7"):
        items = [
            {
                "id": str(t["id"]),
                "title": t["title"],
                "position": t["position"],
                "theme_id": str(t["theme_id"]) if t["theme_id"] else None,
                "personal_data_confirmation": t["personal_data_confirmation"],
            }
            for t in result["planned_dataset"]
            if t["plan_id"] == did("plan:" + key)
        ]
        result["plan_revision"].append(
            {
                "plan_id": did("plan:" + key),
                "revision": 1,
                "saved_by": did("account:" + key),
                "saved_at": AT,
                "snapshot": {
                    "version": 1,
                    "synthetic": True,
                    "plan_id": str(did("plan:" + key)),
                    "revision": 1,
                    "items": items,
                },
            }
        )
    data, _ = catalog()
    for theme in data["themes"]:
        tid = identity("theme:" + theme["code"])
        result["theme"].append({"id": tid, "code": theme["code"], "uri": theme["uri"]})
        result["theme_translation"].extend(
            {"theme_id": tid, "locale": k, "label": v}
            for k, v in theme["labels"].items()
        )
        result["cycle_theme"].append(
            {"cycle_id": did("cycle"), "theme_id": tid, "active": True}
        )
    result["audit_event"] = [
        {
            "id": did("audit"),
            "actor_id": None,
            "action": "synthetic.seed",
            "entity_type": "cycle",
            "entity_id": did("cycle"),
            "request_id": did("request"),
            "changes": {"version": 1, "synthetic": True, "fixture": VERSION},
        }
    ]
    return result


def install(conn, *, deployment="development", apply=False, allow_synthetic=False):
    nonproduction(conn, deployment)
    if apply and not allow_synthetic:
        raise ImportRejected("explicit_synthetic_opt_in_required")
    data = rows()
    with conn.transaction():
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('layer1-reference-import'))"
        )
        if conn.execute(
            "SELECT version_num FROM layer1_migration.alembic_version"
        ).fetchone() != ("l1_0002",):
            raise ImportRejected("migration_head_required")
        for table in metadata.tables.values():
            keys = [c.name for c in table.primary_key.columns]
            allowed = {tuple(row[k] for k in keys) for row in data[table.name]}
            actual = conn.execute(
                sql.SQL("SELECT {} FROM layer1.{}").format(
                    sql.SQL(",").join(map(sql.Identifier, keys)),
                    sql.Identifier(table.name),
                )
            ).fetchall()
            if any(tuple(row) not in allowed for row in actual):
                raise ImportRejected("non_fixture_data_present:" + table.name)
        if not apply:
            for table in metadata.tables.values():
                keys = tuple(c.name for c in table.primary_key.columns)
                for row in data[table.name]:
                    verify_existing(conn, table.name, row, keys)
        if apply:
            install_themes(conn, deployment=deployment, apply=True)
            order = [
                "institution_register_version",
                "institution",
                "cycle",
                "cycle_institution",
            ]
            for table in order:
                keys = tuple(
                    c.name
                    for c in metadata.tables["layer1." + table].primary_key.columns
                )
                for row in data[table]:
                    insert_immutable(conn, table, row, keys)
            for row in data["account"][:2]:
                insert_immutable(conn, "account", row)
            for row in data["institution_email_domain"]:
                insert_immutable(conn, "institution_email_domain", row)
            for row in data["account"][2:]:
                insert_immutable(conn, "account", row)
            for table in [
                "cycle_theme",
                "plan",
                "planned_dataset",
                "plan_revision",
                "audit_event",
            ]:
                keys = tuple(
                    c.name
                    for c in metadata.tables["layer1." + table].primary_key.columns
                )
                for row in data[table]:
                    insert_immutable(conn, table, row, keys)
    return {
        "status": "applied" if apply else "validated",
        "fixture": VERSION,
        "synthetic": True,
        "institutions": 7,
        "themes": 13,
        "translations": 39,
        "plans": 3,
        "items": 3,
        "login_credentials": "disabled",
        "rows": sum(len(v) for v in data.values()),
    }
