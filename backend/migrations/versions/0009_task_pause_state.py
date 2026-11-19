"""Add task pause state restoration metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0009_task_pause_state"
down_revision = "0008_production_orchestrator"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("studio_tasks", sa.Column("paused_from_status", sa.String(length=24), nullable=True))


def downgrade():
    op.drop_column("studio_tasks", "paused_from_status")
