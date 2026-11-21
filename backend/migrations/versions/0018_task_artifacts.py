"""Associate completed execution tasks with stored assets."""
from alembic import op
import sqlalchemy as sa

revision = "0018_task_artifacts"
down_revision = "0017_story_prop_registry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("studio_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "asset_id", name="uq_task_artifact"),
    )
    op.create_index("ix_task_artifacts_task_id", "task_artifacts", ["task_id"])
    op.create_index("ix_task_artifacts_asset_id", "task_artifacts", ["asset_id"])


def downgrade():
    op.drop_index("ix_task_artifacts_asset_id", table_name="task_artifacts")
    op.drop_index("ix_task_artifacts_task_id", table_name="task_artifacts")
    op.drop_table("task_artifacts")
