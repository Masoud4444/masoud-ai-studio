"""Preserve immutable model pricing versions."""
from alembic import op
from backend.app.models import AIModelPricingHistory

revision = "0004_pricing_history"
down_revision = "0003_ai_pricing"
branch_labels = None
depends_on = None

def upgrade():
    AIModelPricingHistory.__table__.create(bind=op.get_bind(), checkfirst=True)

def downgrade():
    # Pricing provenance is retained; destructive downgrade is intentionally disabled.
    pass
