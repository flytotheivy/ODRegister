"""Online-only migration environment; caller supplies a non-secret Connection."""

from alembic import context

from backend.models import metadata

connection = context.config.attributes.get("connection")
if connection is None or context.is_offline_mode():
    raise RuntimeError(
        "Use the migration CLI with an authorised connection; offline SQL is exported from verified PostgreSQL."
    )
context.configure(
    connection=connection,
    target_metadata=metadata,
    version_table_schema="layer1_migration",
    include_schemas=True,
    compare_type=True,
    compare_server_default=True,
)
with context.begin_transaction():
    context.run_migrations()
