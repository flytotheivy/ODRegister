"""Seed helpers: identifiers are composed, values are bound, no raw payload logging."""

import hashlib
import json
import os
from datetime import datetime
from uuid import UUID, uuid5

from psycopg import sql
from psycopg.types.json import Jsonb

NAMESPACE = UUID("c7bfa2c4-9c03-4e50-afbe-ea53ae23869c")


class ImportRejected(ValueError):
    """Safe machine-readable reason, never the input row or credential."""


def identity(key):
    return uuid5(NAMESPACE, key)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require_nonproduction(deployment):
    if deployment not in ("development", "test") or os.environ.get(
        "L1_ENV", "development"
    ) not in ("development", "test"):
        raise ImportRejected("synthetic_or_unreviewed_reference_forbidden")


def nonproduction(conn, deployment):
    require_nonproduction(deployment)
    db, host, port = conn.execute(
        "SELECT current_database(),host(inet_server_addr()),inet_server_port()"
    ).fetchone()
    if db not in ("layer1_dev", "layer1_test") or host != "127.0.0.1" or port != 5433:
        raise ImportRejected("target_not_local_nonproduction_allowlist")


def compare_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def insert_immutable(conn, table, values, keys=("id",)):
    """Insert or verify exact managed values; never overwrite user edits."""
    ordered = list(values)
    conn.execute(
        sql.SQL(
            "INSERT INTO layer1.{} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING"
        ).format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, ordered)),
            sql.SQL(",").join(sql.Placeholder() for _ in ordered),
            sql.SQL(",").join(map(sql.Identifier, keys)),
        ),
        [Jsonb(v) if isinstance(v, dict) else v for v in values.values()],
    )
    if not verify_existing(conn, table, values, keys):
        raise ImportRejected("managed_row_missing:" + table)


def verify_existing(conn, table, values, keys=("id",)):
    ordered = list(values)
    result = conn.execute(
        sql.SQL("SELECT {} FROM layer1.{} WHERE {}").format(
            sql.SQL(",").join(map(sql.Identifier, ordered)),
            sql.Identifier(table),
            sql.SQL(" AND ").join(
                sql.SQL("{}=%s").format(sql.Identifier(k)) for k in keys
            ),
        ),
        [values[k] for k in keys],
    ).fetchone()
    if result is not None and any(
        compare_value(a) != compare_value(b) for a, b in zip(result, values.values())
    ):
        raise ImportRejected("managed_row_conflict:" + table)
    return result is not None


def load_json(path):
    raw = path.read_bytes()
    try:
        return json.loads(raw), digest(raw)
    except (ValueError, UnicodeError) as exc:
        raise ImportRejected("invalid_json") from exc
