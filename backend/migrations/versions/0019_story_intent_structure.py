"""Persist human-value and act-structure fields on story dossiers."""
from alembic import op
import sqlalchemy as sa

revision = "0019_story_intent_structure"
down_revision = "0018_task_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stories", sa.Column("central_question", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("human_value", sa.Text(), nullable=True))
    op.add_column(
        "stories",
        sa.Column("act_structure_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("stories", "act_structure_json")
    op.drop_column("stories", "human_value")
    op.drop_column("stories", "central_question")
