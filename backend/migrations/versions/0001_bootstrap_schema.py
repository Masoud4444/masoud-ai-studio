"""Bootstrap missing tables without dropping existing local data.

This baseline supports installs that were previously initialized through
SQLAlchemy create_all. Future schema changes must use explicit Alembic
operations in new revisions.
"""
from alembic import op
from backend.app.database import Base
from backend.app import models  # noqa: F401

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

def downgrade():
    # Intentionally non-destructive: this baseline may adopt an existing DB.
    # A downgrade must never erase a user's projects or assets.
    pass
