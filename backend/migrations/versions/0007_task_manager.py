"""Create durable task manager tables."""
from alembic import op
import sqlalchemy as sa

revision = "0007_task_manager"
down_revision = "0006_provider_priority"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "studio_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_studio_tasks_project_id", "studio_tasks", ["project_id"])
    op.create_index("ix_studio_tasks_task_type", "studio_tasks", ["task_type"])
    op.create_index("ix_studio_tasks_status", "studio_tasks", ["status"])
    op.create_index("ix_studio_tasks_priority", "studio_tasks", ["priority"])
    op.create_index("ix_studio_tasks_available_at", "studio_tasks", ["available_at"])
    op.create_index("ix_studio_tasks_idempotency_hash", "studio_tasks", ["idempotency_hash"], unique=True)

    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("studio_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("depends_on_task_id", sa.String(length=36), sa.ForeignKey("studio_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
    )
    op.create_index("ix_task_dependencies_task_id", "task_dependencies", ["task_id"])
    op.create_index("ix_task_dependencies_depends_on_task_id", "task_dependencies", ["depends_on_task_id"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("studio_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("detail_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])


def downgrade():
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_task_dependencies_depends_on_task_id", table_name="task_dependencies")
    op.drop_index("ix_task_dependencies_task_id", table_name="task_dependencies")
    op.drop_table("task_dependencies")
    op.drop_index("ix_studio_tasks_idempotency_hash", table_name="studio_tasks")
    op.drop_index("ix_studio_tasks_available_at", table_name="studio_tasks")
    op.drop_index("ix_studio_tasks_priority", table_name="studio_tasks")
    op.drop_index("ix_studio_tasks_status", table_name="studio_tasks")
    op.drop_index("ix_studio_tasks_task_type", table_name="studio_tasks")
    op.drop_index("ix_studio_tasks_project_id", table_name="studio_tasks")
    op.drop_table("studio_tasks")
