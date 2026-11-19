"""Create Agent monthly budget reservation ledger."""
from alembic import op
import sqlalchemy as sa

revision = "0011_agent_budget_ledger"
down_revision = "0010_agent_manager"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_budget_reservations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("studio_agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(18, 8), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_budget_reservations_agent_id", "agent_budget_reservations", ["agent_id"])
    op.create_index("ix_agent_budget_reservations_idempotency_hash", "agent_budget_reservations", ["idempotency_hash"], unique=True)
    op.create_index("ix_agent_budget_reservations_period_start", "agent_budget_reservations", ["period_start"])
    op.create_index("ix_agent_budget_reservations_status", "agent_budget_reservations", ["status"])


def downgrade():
    op.drop_index("ix_agent_budget_reservations_status", table_name="agent_budget_reservations")
    op.drop_index("ix_agent_budget_reservations_period_start", table_name="agent_budget_reservations")
    op.drop_index("ix_agent_budget_reservations_idempotency_hash", table_name="agent_budget_reservations")
    op.drop_index("ix_agent_budget_reservations_agent_id", table_name="agent_budget_reservations")
    op.drop_table("agent_budget_reservations")
