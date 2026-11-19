"""Add manually sourced model pricing and usage cost fields."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from backend.app.models import AIModelPricing

revision = "0003_ai_pricing"
down_revision = "0002_gateway_capabilities"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ai_usage" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("ai_usage")}
        if "estimated_cost_usd" not in columns:
            op.add_column("ai_usage", sa.Column("estimated_cost_usd", sa.Numeric(18, 8), nullable=True))
        if "pricing_version" not in columns:
            op.add_column("ai_usage", sa.Column("pricing_version", sa.Integer(), nullable=True))
    AIModelPricing.__table__.create(bind=bind, checkfirst=True)

def downgrade():
    # Keep cost history and pricing provenance; downgrade is intentionally non-destructive.
    pass
