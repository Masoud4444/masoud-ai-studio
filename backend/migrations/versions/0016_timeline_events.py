"""Add explicit in-world timeline events and ordering constraints."""
from alembic import op
import sqlalchemy as sa

revision = "0016_timeline_events"
down_revision = "0015_continuity_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("scene_id", sa.String(36), sa.ForeignKey("story_scenes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("in_world_time", sa.String(180), nullable=True),
        sa.Column("chronology_note", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_timeline_events_story_id", "timeline_events", ["story_id"])
    op.create_index("ix_timeline_events_scene_id", "timeline_events", ["scene_id"])
    op.create_table(
        "timeline_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("before_event_id", sa.String(36), sa.ForeignKey("timeline_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("after_event_id", sa.String(36), sa.ForeignKey("timeline_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("story_id", "before_event_id", "after_event_id", name="uq_timeline_relation_edge"),
    )
    op.create_index("ix_timeline_relations_story_id", "timeline_relations", ["story_id"])
    op.create_index("ix_timeline_relations_before_event_id", "timeline_relations", ["before_event_id"])
    op.create_index("ix_timeline_relations_after_event_id", "timeline_relations", ["after_event_id"])


def downgrade():
    op.drop_index("ix_timeline_relations_after_event_id", table_name="timeline_relations")
    op.drop_index("ix_timeline_relations_before_event_id", table_name="timeline_relations")
    op.drop_index("ix_timeline_relations_story_id", table_name="timeline_relations")
    op.drop_table("timeline_relations")
    op.drop_index("ix_timeline_events_scene_id", table_name="timeline_events")
    op.drop_index("ix_timeline_events_story_id", table_name="timeline_events")
    op.drop_table("timeline_events")
