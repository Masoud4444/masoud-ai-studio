"""Add scene-linked storyboard shots and reviewable media takes."""
from alembic import op
import sqlalchemy as sa

revision = "0020_storyboard_foundation"
down_revision = "0019_story_intent_structure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "storyboard_shots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_id", sa.String(36), sa.ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("scene_id", sa.String(36), sa.ForeignKey("story_scenes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("shot_size", sa.String(16), nullable=False, server_default="ms"),
        sa.Column("camera_angle", sa.String(24), nullable=False, server_default="eye_level"),
        sa.Column("camera_movement", sa.String(24), nullable=False, server_default="static"),
        sa.Column("lens", sa.String(120), nullable=True),
        sa.Column("composition", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("dialogue", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(8, 3), nullable=False, server_default="4"),
        sa.Column("transition", sa.String(120), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=True),
        sa.Column("source_end", sa.Integer(), nullable=True),
        sa.Column("continuity_notes", sa.Text(), nullable=True),
        sa.Column("entity_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("approved_take_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scene_id", "position", name="uq_storyboard_scene_position"),
    )
    op.create_index("ix_storyboard_shots_story_id", "storyboard_shots", ["story_id"])
    op.create_index("ix_storyboard_shots_scene_id", "storyboard_shots", ["scene_id"])
    op.create_table(
        "storyboard_takes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shot_id", sa.String(36), sa.ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("take_number", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="generated"),
        sa.Column("engine_key", sa.String(100), nullable=False, server_default="manual"),
        sa.Column("engine_job_id", sa.String(200), nullable=True),
        sa.Column("prompt_snapshot", sa.Text(), nullable=True),
        sa.Column("generation_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("shot_id", "take_number", name="uq_storyboard_take_number"),
    )
    op.create_index("ix_storyboard_takes_shot_id", "storyboard_takes", ["shot_id"])
    op.create_index("ix_storyboard_takes_asset_id", "storyboard_takes", ["asset_id"])
    with op.batch_alter_table("storyboard_shots") as batch:
        batch.create_foreign_key("fk_storyboard_approved_take", "storyboard_takes", ["approved_take_id"], ["id"], ondelete="RESTRICT")


def downgrade():
    with op.batch_alter_table("storyboard_shots") as batch:
        batch.drop_constraint("fk_storyboard_approved_take", type_="foreignkey")
    op.drop_index("ix_storyboard_takes_asset_id", table_name="storyboard_takes")
    op.drop_index("ix_storyboard_takes_shot_id", table_name="storyboard_takes")
    op.drop_table("storyboard_takes")
    op.drop_index("ix_storyboard_shots_scene_id", table_name="storyboard_shots")
    op.drop_index("ix_storyboard_shots_story_id", table_name="storyboard_shots")
    op.drop_table("storyboard_shots")
