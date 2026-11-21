"""Add Research Vault sources, evidence, claims and provenance events."""
from alembic import op
import sqlalchemy as sa

revision = "0012_research_vault"
down_revision = "0011_agent_budget_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("author", sa.String(300), nullable=True),
        sa.Column("publisher", sa.String(300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(24), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_sources_source_type", "research_sources", ["source_type"])
    op.create_index("ix_research_sources_created_at", "research_sources", ["created_at"])
    op.create_index("ix_research_sources_asset_id", "research_sources", ["asset_id"])

    op.create_table(
        "project_research_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("research_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "source_id", name="uq_project_research_source"),
    )
    op.create_index("ix_project_research_sources_project_id", "project_research_sources", ["project_id"])
    op.create_index("ix_project_research_sources_source_id", "project_research_sources", ["source_id"])

    op.create_table(
        "research_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("research_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("evidence_type", sa.String(20), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("locator", sa.String(500), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_research_evidence_hash"),
    )
    op.create_index("ix_research_evidence_source_id", "research_evidence", ["source_id"])
    op.create_index("ix_research_evidence_content_hash", "research_evidence", ["content_hash"])

    op.create_table(
        "research_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_claims_project_id", "research_claims", ["project_id"])
    op.create_index("ix_research_claims_status", "research_claims", ["status"])

    op.create_table(
        "research_claim_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("research_claims.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("research_evidence.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_research_claim_evidence"),
    )
    op.create_index("ix_research_claim_evidence_claim_id", "research_claim_evidence", ["claim_id"])
    op.create_index("ix_research_claim_evidence_evidence_id", "research_claim_evidence", ["evidence_id"])

    op.create_table(
        "research_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_events_entity_type", "research_events", ["entity_type"])
    op.create_index("ix_research_events_entity_id", "research_events", ["entity_id"])
    op.create_index("ix_research_events_created_at", "research_events", ["created_at"])


def downgrade():
    op.drop_index("ix_research_events_created_at", table_name="research_events")
    op.drop_index("ix_research_events_entity_id", table_name="research_events")
    op.drop_index("ix_research_events_entity_type", table_name="research_events")
    op.drop_table("research_events")
    op.drop_index("ix_research_claim_evidence_evidence_id", table_name="research_claim_evidence")
    op.drop_index("ix_research_claim_evidence_claim_id", table_name="research_claim_evidence")
    op.drop_table("research_claim_evidence")
    op.drop_index("ix_research_claims_status", table_name="research_claims")
    op.drop_index("ix_research_claims_project_id", table_name="research_claims")
    op.drop_table("research_claims")
    op.drop_index("ix_research_evidence_content_hash", table_name="research_evidence")
    op.drop_index("ix_research_evidence_source_id", table_name="research_evidence")
    op.drop_table("research_evidence")
    op.drop_index("ix_project_research_sources_source_id", table_name="project_research_sources")
    op.drop_index("ix_project_research_sources_project_id", table_name="project_research_sources")
    op.drop_table("project_research_sources")
    op.drop_index("ix_research_sources_asset_id", table_name="research_sources")
    op.drop_index("ix_research_sources_created_at", table_name="research_sources")
    op.drop_index("ix_research_sources_source_type", table_name="research_sources")
    op.drop_table("research_sources")
