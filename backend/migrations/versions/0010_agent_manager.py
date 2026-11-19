"""Create Agent Manager registry and permission audit tables."""
from alembic import op
import sqlalchemy as sa

revision = "0010_agent_manager"
down_revision = "0009_task_pause_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "studio_agents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("provider_id", sa.String(length=36), sa.ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("model_id", sa.String(length=160), nullable=True),
        sa.Column("temperature", sa.Numeric(4, 3), nullable=False, server_default="0.2"),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="4096"),
        sa.Column("max_cost_per_run_usd", sa.Numeric(18, 8), nullable=False, server_default="0.25"),
        sa.Column("monthly_budget_usd", sa.Numeric(18, 8), nullable=False, server_default="10"),
        sa.Column("permissions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_studio_agent_slug"),
    )
    op.create_index("ix_studio_agents_slug", "studio_agents", ["slug"], unique=True)
    op.create_index("ix_studio_agents_status", "studio_agents", ["status"])
    op.create_table(
        "agent_tool_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("studio_agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "tool_name", name="uq_agent_tool_grant"),
    )
    op.create_index("ix_agent_tool_grants_agent_id", "agent_tool_grants", ["agent_id"])
    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("studio_agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_events_agent_id", "agent_events", ["agent_id"])


def downgrade():
    op.drop_index("ix_agent_events_agent_id", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_index("ix_agent_tool_grants_agent_id", table_name="agent_tool_grants")
    op.drop_table("agent_tool_grants")
    op.drop_index("ix_studio_agents_status", table_name="studio_agents")
    op.drop_index("ix_studio_agents_slug", table_name="studio_agents")
    op.drop_table("studio_agents")
