"""Continuity facts and reviewable issue ledger."""
from alembic import op
import sqlalchemy as sa
revision="0015_continuity_engine"
down_revision="0014_character_world_bible"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("continuity_facts",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("scene_id",sa.String(36),sa.ForeignKey("story_scenes.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("subject_type",sa.String(24),nullable=False),sa.Column("subject_ref",sa.String(36)),
        sa.Column("subject_label",sa.String(180),nullable=False),sa.Column("attribute",sa.String(100),nullable=False),
        sa.Column("value",sa.Text(),nullable=False),sa.Column("transition_note",sa.Text()),sa.Column("evidence_note",sa.Text()),
        sa.Column("active",sa.Boolean(),nullable=False),sa.Column("version",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_continuity_facts_story_id","continuity_facts",["story_id"])
    op.create_index("ix_continuity_facts_scene_id","continuity_facts",["scene_id"])
    op.create_table("continuity_issues",
        sa.Column("id",sa.String(36),primary_key=True),sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("fingerprint",sa.String(64),nullable=False),sa.Column("code",sa.String(48),nullable=False),
        sa.Column("severity",sa.String(16),nullable=False),sa.Column("status",sa.String(16),nullable=False),
        sa.Column("title",sa.String(240),nullable=False),sa.Column("description",sa.Text(),nullable=False),
        sa.Column("details_json",sa.Text(),nullable=False),sa.Column("occurrences",sa.Integer(),nullable=False),
        sa.Column("first_seen",sa.DateTime(timezone=True),nullable=False),sa.Column("last_seen",sa.DateTime(timezone=True),nullable=False),
        sa.Column("reviewer_note",sa.Text()),sa.Column("reviewed_at",sa.DateTime(timezone=True)),
        sa.UniqueConstraint("story_id","fingerprint",name="uq_continuity_issue_fingerprint"))
    op.create_index("ix_continuity_issues_story_id","continuity_issues",["story_id"])
def downgrade():
    op.drop_index("ix_continuity_issues_story_id",table_name="continuity_issues");op.drop_table("continuity_issues")
    op.drop_index("ix_continuity_facts_scene_id",table_name="continuity_facts");op.drop_index("ix_continuity_facts_story_id",table_name="continuity_facts");op.drop_table("continuity_facts")
