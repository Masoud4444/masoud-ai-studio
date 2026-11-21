"""Add versioned Story Engine dossiers and scenes."""
from alembic import op
import sqlalchemy as sa
revision = "0013_story_engine"
down_revision = "0012_research_vault"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("stories",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("project_id",sa.String(36),sa.ForeignKey("projects.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("title",sa.String(240),nullable=False),sa.Column("format",sa.String(40),nullable=False),
        sa.Column("genre",sa.String(120)),sa.Column("target_audience",sa.String(500)),sa.Column("premise",sa.Text()),
        sa.Column("logline",sa.String(1000)),sa.Column("synopsis",sa.Text()),sa.Column("creative_intent",sa.Text()),
        sa.Column("status",sa.String(24),nullable=False),sa.Column("version",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_stories_project_id","stories",["project_id"]);op.create_index("ix_stories_status","stories",["status"])
    op.create_table("story_revisions",sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("version",sa.Integer(),nullable=False),sa.Column("snapshot_json",sa.Text(),nullable=False),
        sa.Column("change_note",sa.String(500)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("story_id","version",name="uq_story_revision_version"))
    op.create_index("ix_story_revisions_story_id","story_revisions",["story_id"])
    op.create_table("story_scenes",sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("position",sa.Integer(),nullable=False),sa.Column("title",sa.String(240),nullable=False),
        sa.Column("slugline",sa.String(300)),sa.Column("summary",sa.Text()),sa.Column("dramatic_purpose",sa.String(1000)),
        sa.Column("location",sa.String(240)),sa.Column("time_of_day",sa.String(80)),sa.Column("beats_json",sa.Text(),nullable=False),
        sa.Column("body",sa.Text()),sa.Column("version",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("story_id","position",name="uq_story_scene_position"))
    op.create_index("ix_story_scenes_story_id","story_scenes",["story_id"])

def downgrade():
    op.drop_index("ix_story_scenes_story_id",table_name="story_scenes");op.drop_table("story_scenes")
    op.drop_index("ix_story_revisions_story_id",table_name="story_revisions");op.drop_table("story_revisions")
    op.drop_index("ix_stories_status",table_name="stories");op.drop_index("ix_stories_project_id",table_name="stories");op.drop_table("stories")
