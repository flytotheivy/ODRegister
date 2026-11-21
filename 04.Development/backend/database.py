"""Short read-only readiness probe with the runtime app principal, no migrations/seed."""

from sqlalchemy import text

from backend.config import Settings
from backend.connections import connection_engine


class DatabaseUnavailable(RuntimeError):
    """Sanitized service-level failure; no connection details."""


def check_database(settings: Settings):
    if settings.database_url is None:
        raise DatabaseUnavailable("database_unavailable")
    engine = None
    owned = False
    try:
        engine, owned = connection_engine(settings)
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            # Reject owner/migration/elevated credentials and read-only backup logins.
            assert_runtime_principal(conn)
            conn.execute(text("SELECT id FROM layer1.institution LIMIT 0"))
            conn.execute(
                text(
                    "SELECT theme_id,locale,label FROM layer1.theme_translation LIMIT 0"
                )
            )
            if conn.execute(text("SELECT 1")).scalar_one() != 1:
                raise DatabaseUnavailable("database_unavailable")
    except Exception:  # noqa: BLE001 - never propagate DSN, driver error or SQL parameters
        raise DatabaseUnavailable("database_unavailable") from None
    finally:
        if engine is not None and owned:
            engine.dispose()


def assert_runtime_principal(conn):
    flags = conn.execute(
        text("""SELECT r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls,
        pg_has_role(current_user,n.nspowner,'MEMBER'),
        has_table_privilege(current_user,'layer1.plan','INSERT'),
        has_table_privilege(current_user,'layer1.plan','UPDATE'),
        has_table_privilege(current_user,'layer1.audit_event','UPDATE')
        FROM pg_roles r JOIN pg_namespace n ON n.nspname='layer1' WHERE r.rolname=current_user""")
    ).one()
    if any(flags[:6]) or not all(flags[6:8]) or flags[8]:
        raise DatabaseUnavailable("database_unavailable")
