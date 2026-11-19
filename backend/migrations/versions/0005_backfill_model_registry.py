"""Backfill declared provider models into the model capability registry."""
import json
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "0005_backfill_model_registry"
down_revision = "0004_pricing_history"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "ai_providers" not in tables or "ai_model_capabilities" not in tables:
        return
    providers = bind.execute(sa.text("SELECT id, models_json FROM ai_providers")).all()
    existing = {
        (row[0], row[1]) for row in bind.execute(
            sa.text("SELECT provider_id, model_id FROM ai_model_capabilities")
        ).all()
    }
    for provider_id, models_json in providers:
        try:
            models = json.loads(models_json or "[]")
        except (TypeError, ValueError):
            continue
        for model_id in models:
            if isinstance(model_id, str) and model_id and (provider_id, model_id) not in existing:
                bind.execute(sa.text(
                    "INSERT INTO ai_model_capabilities "
                    "(id, provider_id, model_id, capabilities_json, verification_status, "
                    "supports_streaming, supports_tools, supports_vision) "
                    "VALUES (:id, :provider_id, :model_id, '[]', 'declared', 0, 0, 0)"
                ), {"id": str(uuid4()), "provider_id": provider_id, "model_id": model_id})

def downgrade():
    # Do not erase user-defined capability declarations.
    pass
