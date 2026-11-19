"""Add stable story prop registry."""
from alembic import op
import sqlalchemy as sa

revision = "0017_story_prop_registry"
down_revision = "0016_timeline_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "story_props",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("origin", sa.Text(), nullable=True),
        sa.Column("initial_state", sa.Text(), nullable=True),
        sa.Column("current_holder_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_story_props_story_id", "story_props", ["story_id"])
    op.create_index("ix_story_props_current_holder_id", "story_props", ["current_holder_id"])


def downgrade():
    op.drop_index("ix_story_props_current_holder_id", table_name="story_props")
    op.drop_index("ix_story_props_story_id", table_name="story_props")
    op.drop_table("story_props")
