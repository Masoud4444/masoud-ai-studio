"""Add capability registry and recoverable request leases."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from backend.app.models import AIModelCapability

revision = "0002_gateway_capabilities"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ai_requests" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("ai_requests")}
        if "lease_expires_at" not in columns:
            op.add_column("ai_requests", sa.Column("lease_expires_at", sa.Integer(), nullable=True))
    AIModelCapability.__table__.create(bind=bind, checkfirst=True)

def downgrade():
    # Preserve idempotency records and declarations; downgrade is intentionally non-destructive.
    pass
