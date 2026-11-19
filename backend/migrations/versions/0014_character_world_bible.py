"""Character and World Bible schema."""
from alembic import op
import sqlalchemy as sa
revision="0014_character_world_bible"
down_revision="0013_story_engine"
branch_labels=None
depends_on=None
def upgrade():
    op.create_table("story_characters",sa.Column("id",sa.String(36),primary_key=True),sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),sa.Column("name",sa.String(180),nullable=False),sa.Column("role",sa.String(80),nullable=False),sa.Column("age",sa.String(80)),sa.Column("appearance_json",sa.Text(),nullable=False),sa.Column("psychology_json",sa.Text(),nullable=False),sa.Column("backstory",sa.Text()),sa.Column("goals",sa.Text()),sa.Column("conflict",sa.Text()),sa.Column("arc",sa.Text()),sa.Column("voice_notes",sa.Text()),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_story_characters_story_id","story_characters",["story_id"])
    op.create_table("character_relationships",sa.Column("id",sa.String(36),primary_key=True),sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),sa.Column("source_id",sa.String(36),sa.ForeignKey("story_characters.id",ondelete="RESTRICT"),nullable=False),sa.Column("target_id",sa.String(36),sa.ForeignKey("story_characters.id",ondelete="RESTRICT"),nullable=False),sa.Column("kind",sa.String(100),nullable=False),sa.Column("description",sa.Text()),sa.UniqueConstraint("story_id","source_id","target_id","kind",name="uq_character_relationship"))
    op.create_index("ix_character_relationships_story_id","character_relationships",["story_id"])
    op.create_table("story_world_locations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),sa.Column("name",sa.String(180),nullable=False),sa.Column("location_type",sa.String(80),nullable=False),sa.Column("description",sa.Text()),sa.Column("geography_json",sa.Text(),nullable=False),sa.Column("culture_json",sa.Text(),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_story_world_locations_story_id","story_world_locations",["story_id"])
    op.create_table("story_world_rules",sa.Column("id",sa.String(36),primary_key=True),sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),sa.Column("category",sa.String(80),nullable=False),sa.Column("statement",sa.Text(),nullable=False),sa.Column("rationale",sa.Text()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_story_world_rules_story_id","story_world_rules",["story_id"])
    op.create_table("scene_character_links",sa.Column("id",sa.String(36),primary_key=True),sa.Column("scene_id",sa.String(36),sa.ForeignKey("story_scenes.id",ondelete="RESTRICT"),nullable=False),sa.Column("character_id",sa.String(36),sa.ForeignKey("story_characters.id",ondelete="RESTRICT"),nullable=False),sa.Column("presence_type",sa.String(40),nullable=False),sa.Column("note",sa.Text()),sa.UniqueConstraint("scene_id","character_id",name="uq_scene_character_link"))
    op.create_index("ix_scene_character_links_scene_id","scene_character_links",["scene_id"]);op.create_index("ix_scene_character_links_character_id","scene_character_links",["character_id"])
    op.create_table("scene_location_links",sa.Column("id",sa.String(36),primary_key=True),sa.Column("scene_id",sa.String(36),sa.ForeignKey("story_scenes.id",ondelete="RESTRICT"),nullable=False),sa.Column("location_id",sa.String(36),sa.ForeignKey("story_world_locations.id",ondelete="RESTRICT"),nullable=False),sa.Column("note",sa.Text()),sa.UniqueConstraint("scene_id","location_id",name="uq_scene_location_link"))
    op.create_index("ix_scene_location_links_scene_id","scene_location_links",["scene_id"]);op.create_index("ix_scene_location_links_location_id","scene_location_links",["location_id"])
    op.create_table("story_bible_revisions",sa.Column("id",sa.String(36),primary_key=True),sa.Column("story_id",sa.String(36),sa.ForeignKey("stories.id",ondelete="RESTRICT"),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("snapshot_json",sa.Text(),nullable=False),sa.Column("change_note",sa.String(500)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("story_id","version",name="uq_story_bible_revision"))
    op.create_index("ix_story_bible_revisions_story_id","story_bible_revisions",["story_id"])
def downgrade():
    op.drop_index("ix_story_bible_revisions_story_id",table_name="story_bible_revisions");op.drop_table("story_bible_revisions")
    for table,cols in (("scene_location_links",("scene_id","location_id")),("scene_character_links",("scene_id","character_id"))):
        for col in cols: op.drop_index(f"ix_{table}_{col}",table_name=table)
        op.drop_table(table)
    for table in ("story_world_rules","story_world_locations","character_relationships","story_characters"):
        op.drop_index(f"ix_{table}_story_id",table_name=table);op.drop_table(table)
