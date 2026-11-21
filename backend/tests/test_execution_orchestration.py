from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.orchestrator import create_production_run


def test_production_run_persists_selected_execution_mode():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        run = create_production_run(db, "creative.preproduction", {"brief": "A short film"},
            "execution-orchestration-local-01", execution_mode="local", cloud_available=False)
        assert run["steps"]
        assert all(step["execution_mode"] == "local" for step in run["steps"])
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_production_run_can_be_routed_to_cloud_explicitly():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        run = create_production_run(db, "creative.preproduction", {"brief": "A short film"},
            "execution-orchestration-cloud-02", execution_mode="cloud", cloud_available=True)
        assert all(step["execution_mode"] == "cloud" for step in run["steps"])
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
