"""Explicit preview-only PostgreSQL installation; private files, no seed or reset."""

import argparse
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

import psycopg
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from backend.models import metadata

DEV = Path(__file__).resolve().parents[2]
PRIVATE = DEV / ".data/online-postgres"
HEAD = "l1_0002"
CA = "/etc/ssl/cert.pem"
KINDS = ("owner", "migrator", "app", "backup")
PRIVILEGES = {
    name: ("SELECT", "INSERT", "UPDATE")
    for name in (
        "institution_register_version",
        "institution",
        "cycle",
        "cycle_institution",
        "account",
        "institution_email_domain",
        "session",
        "account_recovery_grant",
        "theme",
        "theme_translation",
        "cycle_theme",
        "plan",
    )
}
PRIVILEGES.update(
    planned_dataset=("SELECT", "INSERT", "UPDATE", "DELETE"),
    plan_revision=("SELECT", "INSERT"),
    audit_event=("SELECT", "INSERT"),
)


def private_json(path):
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("Private regular file with mode 0600 required")
    return json.loads(path.read_text())


def save_private(path, value, *, exclusive=False):
    # Persist before publishing the name; an interrupted update preserves the old file.
    fd, temporary = tempfile.mkstemp(prefix=".private-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load():
    cfg = private_json(PRIVATE / "provider.json")
    if cfg.get("resource") != "odregister-preview" or cfg.get("provider") != "Neon":
        raise ValueError("Explicit preview resource required")
    urls = cfg["connections"]
    for key in ("DATABASE_URL", "DATABASE_URL_UNPOOLED"):
        u = make_url(urls[key])
        if (
            u.drivername != "postgresql"
            or not u.password
            or not u.host
            or not u.host.endswith(".neon.tech")
        ):
            raise ValueError("Expected private Neon PostgreSQL connection")
        if key.endswith("UNPOOLED") and "-pooler" in u.host:
            raise ValueError("Migration requires direct connection")
    return cfg


def role(kind):
    if kind not in KINDS:
        raise ValueError("Unknown preview role")
    return "layer1_preview_" + kind


def provider_connection():
    return psycopg.connect(
        load()["connections"]["DATABASE_URL_UNPOOLED"],
        connect_timeout=10,
        sslmode="verify-full",
        sslrootcert=CA,
        options="-c search_path=pg_catalog -c statement_timeout=15000 -c lock_timeout=5000",
    )


def state():
    cfg = load()
    identity = hashlib.sha256(
        cfg["connections"]["DATABASE_URL_UNPOOLED"].encode()
    ).hexdigest()
    p = PRIVATE / "roles.json"
    if p.exists():
        value = private_json(p)
        if value["identity"] != identity:
            raise ValueError(
                "Preview destination changed; explicit reconciliation required"
            )
        return value
    value = {
        "identity": identity,
        "marker": "ODRegister preview " + secrets.token_hex(16),
        "passwords": {k: secrets.token_urlsafe(36) for k in KINDS if k != "owner"},
    }
    save_private(p, value, exclusive=True)
    return value


def role_url(kind, *, pooled=False):
    cfg, st = load(), state()
    base = make_url(
        cfg["connections"]["DATABASE_URL" if pooled else "DATABASE_URL_UNPOOLED"]
    )
    query = dict(base.query)
    query.update(sslmode="verify-full", sslrootcert=CA)
    return base.set(
        drivername="postgresql+psycopg",
        username=role(kind),
        password=st["passwords"][kind],
        query=query,
    )


def role_engine(kind, *, pooled=False):
    return create_engine(
        role_url(kind, pooled=pooled),
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 10,
            "prepare_threshold": None,
            "options": "-c search_path=pg_catalog -c statement_timeout=15000",
        },
    )


def provision():
    st = state()
    with provider_connection() as c:
        c.execute(
            "SELECT pg_advisory_xact_lock(hashtext('odregister-preview-install'))"
        )
        marker = c.execute(
            "SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='layer1_migration'"
        ).fetchone()
        existing = c.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
            ([role(k) for k in KINDS],),
        ).fetchall()
        if marker:
            if marker[0] != st["marker"] or len(existing) != 4:
                raise ValueError(
                    "Unrecognised existing installation; refusing adoption"
                )
            return
        if (
            existing
            or c.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') LIMIT 1"
            ).fetchone()
        ):
            raise ValueError(
                "Preview installation requires an empty dedicated database"
            )
        database, operator = c.execute(
            "SELECT current_database(),current_user"
        ).fetchone()
        for k in KINDS:
            c.execute(
                sql.SQL(
                    "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
                ).format(sql.Identifier(role(k)))
            )
            if k != "owner":
                c.execute(
                    sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role(k)), sql.Literal(st["passwords"][k])
                    )
                )
        for target in (operator, role("migrator")):
            c.execute(
                sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                    sql.Identifier(role("owner")), sql.Identifier(target)
                )
            )
        c.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(database)
            )
        )
        c.execute(
            sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(role("owner"))
            )
        )
        for k in ("migrator", "app", "backup"):
            c.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database), sql.Identifier(role(k))
                )
            )
        c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        c.execute(
            sql.SQL("CREATE SCHEMA layer1_migration AUTHORIZATION {}").format(
                sql.Identifier(role("owner"))
            )
        )
        c.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role("owner"))))
        c.execute(
            sql.SQL("COMMENT ON SCHEMA layer1_migration IS {}").format(
                sql.Literal(st["marker"])
            )
        )
        c.execute("REVOKE ALL ON SCHEMA layer1_migration FROM PUBLIC")
        c.execute("ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")


def runtime_configuration():
    # Existing app sends startup options which the provider pooler rejects.
    # NullPool + a direct, least-privilege login requires no application changes.
    return {
        "DATABASE_URL": role_url("app").render_as_string(hide_password=False),
        "L1_ENV": "preview",
        "L1_DB_POOL_MODE": "null",
        "L1_CONNECT_TIMEOUT": 5,
        "L1_APP_ORIGIN": None,
        "note": "Set actual HTTPS origin before deployment; provider owner credentials are not runtime credentials.",
    }


def migrate():
    st = state()
    eng = role_engine("migrator")
    try:
        with eng.begin() as c:
            c.execute(text("SET ROLE " + role("owner")))
            actual = c.execute(
                text(
                    "SELECT obj_description('layer1_migration'::regnamespace,'pg_namespace')"
                )
            ).scalar_one()
            if actual != st["marker"]:
                raise ValueError("Unrecognised schema marker")
            c.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtext('layer1-schema-migration'))"
                )
            )
            cfg = Config()
            cfg.set_main_option("script_location", str(DEV / "backend/migrations"))
            cfg.attributes["connection"] = c
            command.upgrade(cfg, HEAD)
            if set(PRIVILEGES) != {t.name for t in metadata.tables.values()}:
                raise ValueError("Privilege inventory requires review")
            for schema in ("layer1", "layer1_migration"):
                c.execute(text("REVOKE ALL ON SCHEMA " + schema + " FROM PUBLIC"))
            c.execute(
                text(
                    "GRANT USAGE ON SCHEMA layer1 TO "
                    + role("app")
                    + ","
                    + role("backup")
                )
            )
            c.execute(
                text("GRANT USAGE ON SCHEMA layer1_migration TO " + role("backup"))
            )
            c.execute(
                text(
                    "GRANT SELECT ON layer1_migration.alembic_version TO "
                    + role("backup")
                )
            )
            for name, grants in PRIVILEGES.items():
                target = "layer1." + name
                c.execute(
                    text(
                        "REVOKE ALL ON "
                        + target
                        + " FROM PUBLIC,"
                        + role("app")
                        + ","
                        + role("backup")
                    )
                )
                c.execute(text("GRANT SELECT ON " + target + " TO " + role("backup")))
                c.execute(
                    text(
                        "GRANT "
                        + ",".join(grants)
                        + " ON "
                        + target
                        + " TO "
                        + role("app")
                    )
                )
    finally:
        eng.dispose()
    save_private(PRIVATE / "runtime.json", runtime_configuration())


def verify():
    report = {
        "status": "PASS",
        "task": "L1-P6-01",
        "scope": "Remote preview schema and roles; no seed, deployment or UAT",
    }
    eng = role_engine("migrator")
    try:
        with eng.connect() as c:
            c.execute(text("SET ROLE " + role("owner")))
            version = c.execute(
                text(
                    "SELECT current_setting('server_version'),current_setting('server_version_num')::int"
                )
            ).one()
            report.update(
                server_version=version[0],
                major=version[1] // 10000,
                local_baseline_major=16,
                major_differs_from_local=version[1] // 10000 != 16,
            )
            inspector = inspect(c)
            tables = inspector.get_table_names(schema="layer1")
            assert set(tables) == {t.name for t in metadata.tables.values()}
            report["tables"] = len(tables)
            report["columns"] = sum(
                len(inspector.get_columns(t, schema="layer1")) for t in tables
            )
            assert report["columns"] == 124
            context = MigrationContext.configure(
                c,
                opts={
                    "include_schemas": True,
                    "include_name": lambda name, type_, parent: (
                        name == "layer1" if type_ == "schema" else True
                    ),
                    "compare_type": True,
                    "compare_server_default": True,
                },
            )
            differences = compare_metadata(context, metadata)
            assert not differences, "Metadata mismatch (details suppressed)"
            report["metadata_differences"] = 0
            report["indexes"] = c.execute(
                text("SELECT count(*) FROM pg_indexes WHERE schemaname='layer1'")
            ).scalar_one()
            assert report["indexes"] == 50
            head = c.execute(
                text("SELECT version_num FROM layer1_migration.alembic_version")
            ).scalar_one()
            assert head == HEAD
            report["migration_head"] = head
            owners = (
                c.execute(
                    text(
                        "SELECT DISTINCT pg_get_userbyid(relowner) FROM pg_class WHERE relnamespace IN ('layer1'::regnamespace,'layer1_migration'::regnamespace) AND relkind IN ('r','i')"
                    )
                )
                .scalars()
                .all()
            )
            assert owners == [role("owner")]
            report["dedicated_owner_verified"] = True
            counts = {
                t: c.execute(text("SELECT count(*) FROM layer1." + t)).scalar_one()
                for t in tables
            }
            report["business_rows"] = sum(counts.values())
            report["tls_verified"] = bool(
                c.connection.driver_connection.pgconn.ssl_in_use
            )
            assert report["tls_verified"]
    finally:
        eng.dispose()
    # Verify every table's full effective privilege matrix, not only explicit grants.
    for k in ("app", "backup"):
        eng = role_engine(k)
        try:
            with eng.connect() as c:
                flags = c.execute(
                    text(
                        "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
                    )
                ).one()
                assert not any(flags)
                assert not c.execute(
                    text("SELECT pg_has_role(current_user,:owner,'MEMBER')"),
                    {"owner": role("owner")},
                ).scalar_one()
                assert not c.execute(
                    text("SELECT pg_has_role(current_user,'neon_superuser','MEMBER')")
                ).scalar_one()
                permissions = (
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "REFERENCES",
                    "TRIGGER",
                )
                matrix = c.execute(
                    text("""
                    SELECT a.table_name,b.permission,
                           has_table_privilege(current_user,'layer1.'||a.table_name,b.permission)
                    FROM unnest(CAST(:tables AS text[])) AS a(table_name)
                    CROSS JOIN unnest(CAST(:permissions AS text[])) AS b(permission)
                """),
                    {"tables": list(PRIVILEGES), "permissions": list(permissions)},
                ).all()
                assert len(matrix) == 105
                for table, permission, actual in matrix:
                    expected = permission in (
                        PRIVILEGES[table] if k == "app" else ("SELECT",)
                    )
                    assert actual == expected
                assert not c.execute(
                    text("SELECT has_schema_privilege(current_user,'layer1','CREATE')")
                ).scalar_one()
                assert (
                    c.execute(text("SELECT count(*) FROM layer1.account")).scalar_one()
                    >= 0
                )
                assert c.connection.driver_connection.pgconn.ssl_in_use
        finally:
            eng.dispose()
    report.update(
        role_privilege_checks=210,
        app_and_backup_not_platform_admin=True,
        runtime_connection_mode="direct + NullPool",
        pooled_runtime_connection_verified=False,
        pooler_incompatible_with_existing_startup_options=True,
    )
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("install", "verify"))
    args = p.parse_args()
    if args.command == "install":
        provision()
        migrate()
    report = verify()
    (PRIVATE / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - redact driver diagnostics and DSNs
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "sqlstate": getattr(exc, "sqlstate", None),
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
