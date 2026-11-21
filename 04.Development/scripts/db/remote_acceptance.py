"""Operator-only remote preview acceptance: roles, constraints, resume and API. No seed."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.config import Settings, get_settings
from backend.main import create_app
from scripts.db.remote import (
    PRIVATE,
    migrate,
    provider_connection,
    provision,
    role_engine,
)


def main():
    p = PRIVATE
    stage = "constraints"
    try:
        with provider_connection() as c:
            constraints = dict(
                c.execute(
                    "SELECT contype,count(*) FROM pg_constraint WHERE connamespace='layer1'::regnamespace AND contype IN ('p','f','u','c') GROUP BY contype"
                ).fetchall()
            )
            assert constraints == {"p": 15, "f": 22, "u": 10, "c": 52}
            deferral = c.execute(
                "SELECT condeferrable,condeferred FROM pg_constraint WHERE conname='uq_planned_dataset_order' AND connamespace='layer1'::regnamespace"
            ).fetchone()
            assert deferral == (True, True)
            attrs = c.execute(
                "SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname LIKE 'layer1_preview_%'"
            ).fetchall()
            assert len(attrs) == 4 and all(not any(row[1:]) for row in attrs)
        stage = "denials"
        checks = []
        for kind, statement in [
            ("app", "CREATE TABLE layer1.__permission_probe (id integer)"),
            ("app", "UPDATE layer1.audit_event SET action=action WHERE false"),
            ("backup", "DELETE FROM layer1.account WHERE false"),
        ]:
            eng = role_engine(kind)
            try:
                with eng.connect() as c:
                    try:
                        c.execute(text(statement))
                        c.rollback()
                        raise AssertionError("Unexpected permission")
                    except DBAPIError as e:
                        code = getattr(getattr(e, "orig", None), "sqlstate", None)
                        c.rollback()
                        assert code == "42501"
                        checks.append({"role": kind, "sqlstate": code})
            finally:
                eng.dispose()
        stage = "resume"
        provision()
        migrate()
        with provider_connection() as c:
            assert c.execute("SELECT count(*) FROM layer1.account").fetchone()[0] == 0
            assert (
                c.execute("SELECT to_regclass('layer1.__permission_probe')").fetchone()[
                    0
                ]
                is None
            )
        install = {
            "status": "PASS",
            "constraints": constraints,
            "deferred_order_constraint_verified": True,
            "four_roles_non_elevated": True,
            "denial_tests": checks,
            "idempotent_install_reentry": True,
            "business_rows_preserved": 0,
            "credentials_rotated": False,
        }
        (p / "installation-checks.json").write_text(
            json.dumps(install, indent=2) + "\n"
        )
        print(json.dumps(install), flush=True)
        stage = "api"
        cfg = json.loads((p / "runtime.json").read_text())
        checks = []
        settings = Settings(
            DATABASE_URL=cfg["DATABASE_URL"],
            L1_ENV="preview",
            app_origin="https://odregister-preview.example.invalid",
            connect_timeout=5,
        )
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        with TestClient(app, base_url=settings.app_origin) as client:
            for route, expected in [
                ("/api/runtime", 200),
                ("/api/health", 200),
                ("/api/public/cycles", 200),
                ("/api/auth/me", 401),
                ("/api/admin/monitoring/2027", 401),
            ]:
                response = client.get(route)
                checks.append(
                    {
                        "route": route,
                        "expected": expected,
                        "actual": response.status_code,
                    }
                )
                assert response.status_code == expected
        report = {
            "status": "PASS",
            "scope": "Local ASGI using real remote app role; no HTTP deployment",
            "checks": checks,
            "seed_written": False,
            "business_mutations": False,
        }
        print(json.dumps(report))
        (p / "api-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    except Exception as e:  # noqa: BLE001 - redact driver diagnostics
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "stage": stage,
                    "error_type": type(e).__name__,
                    "sqlstate": getattr(e, "sqlstate", None),
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
