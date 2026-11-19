"""Add production run and step graph persistence."""
from alembic import op
import sqlalchemy as sa

revision = "0008_production_orchestrator"
down_revision = "0007_task_manager"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "production_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("workflow_key", sa.String(length=120), nullable=False),
        sa.Column("workflow_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("input_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("idempotency_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_production_runs_project_id", "production_runs", ["project_id"])
    op.create_index("ix_production_runs_status", "production_runs", ["status"])
    op.create_index("ix_production_runs_idempotency_hash", "production_runs", ["idempotency_hash"], unique=True)

    op.create_table(
        "production_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("production_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("step_key", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("studio_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "step_key", name="uq_production_run_step"),
        sa.UniqueConstraint("task_id", name="uq_production_step_task"),
    )
    op.create_index("ix_production_steps_run_id", "production_steps", ["run_id"])


def downgrade():
    op.drop_index("ix_production_steps_run_id", table_name="production_steps")
    op.drop_table("production_steps")
    op.drop_index("ix_production_runs_idempotency_hash", table_name="production_runs")
    op.drop_index("ix_production_runs_status", table_name="production_runs")
    op.drop_index("ix_production_runs_project_id", table_name="production_runs")
    op.drop_table("production_runs")
