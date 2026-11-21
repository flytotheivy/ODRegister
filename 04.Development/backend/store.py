"""Transaction boundary for runtime app role only; no local/admin fallback."""

from contextlib import contextmanager

from backend.connections import connection_engine
from backend.database import assert_runtime_principal


@contextmanager
def transaction(settings, *, snapshot=False, readonly=True):
    engine, owned = connection_engine(settings)
    try:
        with engine.begin() as conn:
            if snapshot:
                from sqlalchemy import text

                conn.execute(
                    text(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ "
                        + ("READ ONLY" if readonly else "READ WRITE")
                    )
                )
            assert_runtime_principal(conn)
            yield conn
    finally:
        if owned:
            engine.dispose()
