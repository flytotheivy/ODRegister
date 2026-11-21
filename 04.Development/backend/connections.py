"""Process-local bounded candidate or per-probe NullPool. No business/session state."""

import hashlib
import ssl
from pathlib import Path
from threading import RLock

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, QueuePool

_cached_engine = None
_cached_key = None
_lock = RLock()


def dispose_pool():
    global _cached_engine, _cached_key
    with _lock:
        if _cached_engine is not None:
            _cached_engine.dispose()
        _cached_engine = None
        _cached_key = None


def portable_certificate_url(url):
    """Resolve system CA bundles across macOS/Linux binary libpq distributions."""
    if url.query.get("sslrootcert") != "system":
        return url
    candidates = [
        ssl.get_default_verify_paths().cafile,
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return url.set(
                query={**url.query, "sslrootcert": candidate, "sslmode": "verify-full"}
            )
    # Preserve libpq's own system resolution; certificate verification stays enabled.
    return url


def connection_engine(settings):
    global _cached_engine, _cached_key
    if settings.database_url is None:
        raise ValueError("runtime database URL required")
    raw = settings.database_url.get_secret_value()
    url = make_url(raw)
    if url.drivername not in ("postgresql", "postgresql+psycopg"):
        raise ValueError("unsupported runtime driver")
    url = portable_certificate_url(url)
    options = {
        "echo": False,
        "hide_parameters": True,
        "connect_args": {
            "connect_timeout": settings.connect_timeout,
            "prepare_threshold": None,
            "options": "-c statement_timeout=2000 -c search_path=pg_catalog",
        },
    }
    if settings.db_pool_mode == "null":
        return create_engine(
            url.set(drivername="postgresql+psycopg"), poolclass=NullPool, **options
        ), True
    key = (
        hashlib.sha256(raw.encode()).hexdigest(),
        settings.connect_timeout,
        settings.db_pool_size,
        settings.db_pool_timeout,
    )
    with _lock:
        if _cached_engine is None or _cached_key != key:
            dispose_pool()
            _cached_engine = create_engine(
                url.set(drivername="postgresql+psycopg"),
                poolclass=QueuePool,
                pool_size=settings.db_pool_size,
                max_overflow=0,
                pool_timeout=settings.db_pool_timeout,
                pool_pre_ping=True,
                pool_recycle=300,
                **options,
            )
            _cached_key = key
        return _cached_engine, False
