"""Required lookup and conditional uniqueness indexes. No seed."""

from pathlib import Path

from alembic import op

revision = "l1_0002"
down_revision = "l1_0001"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen SQL is migration-local; never imports mutable application metadata.
    sql = Path(__file__).with_suffix(".sql").read_text()
    op.get_bind().exec_driver_sql(sql)


def downgrade():
    raise RuntimeError(
        "Destructive downgrade disabled; use verified backup/forward repair."
    )
