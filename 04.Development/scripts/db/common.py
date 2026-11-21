"""Private local configuration. Never render credentials/URLs in tool output."""

import json
import os
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

DEV = Path(__file__).resolve().parents[2]
PROJECT = DEV.parent
PRIVATE = DEV / ".data"
SECRET = PRIVATE / "db-credentials.json"
CONFIG = PRIVATE / "local-postgres.json"
BIN = Path(os.environ.get("L1_PG_BIN", "/opt/homebrew/opt/postgresql@16/bin"))
ENVIRONMENTS = ("dev", "test", "restore")
HEAD = "l1_0002"


def config():
    result = json.loads(CONFIG.read_text())
    if result["project"] != str(PROJECT.resolve()) or result["port"] != 5433:
        raise RuntimeError("Unrecognised local cluster configuration")
    for p in (CONFIG, SECRET):
        if p.stat().st_mode & 0o077:
            raise RuntimeError("Private configuration permissions must be 0600")
    return result


def credentials():
    config()
    return json.loads(SECRET.read_text())


def role(environment, kind):
    if environment not in ENVIRONMENTS or kind not in (
        "owner",
        "migrator",
        "app",
        "backup",
    ):
        raise ValueError("Unknown local environment/role")
    return f"layer1_{environment}_{kind}"


def connection(environment, kind="app", *, autocommit=False):
    cfg = config()
    return psycopg.connect(
        host="127.0.0.1",
        port=cfg["port"],
        dbname="layer1_" + environment,
        user=role(environment, kind),
        password=credentials()[environment][kind],
        autocommit=autocommit,
        connect_timeout=5,
        options="-c search_path=pg_catalog",
    )


def admin(database="postgres"):
    cfg = config()
    return psycopg.connect(
        host=cfg["socket"],
        port=cfg["port"],
        dbname=database,
        user=cfg["admin"],
        autocommit=True,
        connect_timeout=5,
    )


def engine(environment):
    cfg = config()
    return create_engine(
        URL.create(
            "postgresql+psycopg",
            username=role(environment, "migrator"),
            password=credentials()[environment]["migrator"],
            host="127.0.0.1",
            port=cfg["port"],
            database="layer1_" + environment,
        ),
        echo=False,
        hide_parameters=True,
        poolclass=NullPool,
    )


def apply_grants(environment):
    # Explicit inventory: no broad grants on future tables, no schema ownership for API.
    from backend.models import metadata

    app = sql.Identifier(role(environment, "app"))
    backup = sql.Identifier(role(environment, "backup"))
    with connection(environment, "migrator") as conn:
        conn.execute(
            sql.SQL("SET ROLE {}").format(sql.Identifier(role(environment, "owner")))
        )
        conn.execute("REVOKE ALL ON SCHEMA layer1 FROM PUBLIC")
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA layer1 TO {}, {}").format(app, backup)
        )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA layer1_migration TO {}").format(backup)
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON layer1_migration.alembic_version TO {}").format(
                backup
            )
        )
        privileges = {
            "institution_register_version": ("SELECT", "INSERT", "UPDATE"),
            "institution": ("SELECT", "INSERT", "UPDATE"),
            "cycle": ("SELECT", "INSERT", "UPDATE"),
            "cycle_institution": ("SELECT", "INSERT", "UPDATE"),
            "account": ("SELECT", "INSERT", "UPDATE"),
            "institution_email_domain": ("SELECT", "INSERT", "UPDATE"),
            "session": ("SELECT", "INSERT", "UPDATE"),
            "account_recovery_grant": ("SELECT", "INSERT", "UPDATE"),
            "theme": ("SELECT", "INSERT", "UPDATE"),
            "theme_translation": ("SELECT", "INSERT", "UPDATE"),
            "cycle_theme": ("SELECT", "INSERT", "UPDATE"),
            "plan": ("SELECT", "INSERT", "UPDATE"),
            "planned_dataset": ("SELECT", "INSERT", "UPDATE", "DELETE"),
            "plan_revision": ("SELECT", "INSERT"),
            "audit_event": ("SELECT", "INSERT"),
        }
        if set(privileges) != {t.name for t in metadata.tables.values()}:
            raise RuntimeError(
                "New tables require explicit reviewed privilege inventory"
            )
        for name, grants in privileges.items():
            target = sql.Identifier("layer1", name)
            conn.execute(
                sql.SQL("REVOKE ALL ON {} FROM PUBLIC, {}, {}").format(
                    target, app, backup
                )
            )
            conn.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(target, backup))
            conn.execute(
                sql.SQL("GRANT {} ON {} TO {}").format(
                    sql.SQL(",").join(map(sql.SQL, grants)), target, app
                )
            )
