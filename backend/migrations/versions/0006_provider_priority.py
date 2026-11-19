"""Add provider priority for deterministic model routing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006_provider_priority"
down_revision = "0005_backfill_model_registry"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "ai_providers" in inspect(bind).get_table_names():
        columns = {column["name"] for column in inspect(bind).get_columns("ai_providers")}
        if "priority" not in columns:
            op.add_column("ai_providers", sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))

def downgrade():
    # Preserve provider routing configuration on downgrade.
    pass
