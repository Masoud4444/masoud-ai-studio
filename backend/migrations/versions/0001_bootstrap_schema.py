"""Bootstrap the original core schema without pre-creating later feature tables.

This baseline adopts databases initialized by the original SQLAlchemy schema.
It deliberately creates only core tables that existed before feature revisions
0002 onward. Later tables must be created by their own explicit revisions.
"""
from alembic import op
from backend.app.database import Base
from backend.app import models  # noqa: F401

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None

_CORE_TABLES = (
    "projects",
    "assets",
    "project_assets",
    "ai_providers",
    "ai_requests",
    "ai_usage",
)


def upgrade():
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _CORE_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade():
    # Intentionally non-destructive: this baseline may adopt an existing DB.
    pass
