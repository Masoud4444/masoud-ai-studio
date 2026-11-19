from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env", override=False)

from .api import router
from .character_world import router as character_world_router
from .continuity import router as continuity_router
from .database import Base, SessionLocal, engine
from .worker import TaskHandlerRegistry, WorkerSupervisor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is a development bootstrap only. Managed installs use Alembic.
    if os.getenv("MASOUD_STUDIO_SCHEMA_MODE", "migrate").lower() == "create":
        os.makedirs("data", exist_ok=True)
        Base.metadata.create_all(bind=engine)

    supervisor = None
    worker_task = None
    if os.getenv("MASOUD_STUDIO_WORKER_ENABLED", "false").lower() == "true":
        registry = TaskHandlerRegistry()
        # The only built-in handler is a safe smoke-test task. Production
        # workflow handlers are registered by their owning modules later.
        registry.register("system.healthcheck", lambda _payload: {"ok": True})
        supervisor = WorkerSupervisor(
            session_factory=SessionLocal,
            worker_id=os.getenv("MASOUD_STUDIO_WORKER_ID", "local-worker-1"),
            registry=registry,
        )
        worker_task = asyncio.create_task(supervisor.run_forever())

    try:
        yield
    finally:
        if supervisor is not None:
            supervisor.request_stop()
        if worker_task is not None:
            await worker_task


app = FastAPI(
    title="Masoud AI Studio API",
    version="0.3.0",
    description="Private, local-first creative production studio",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(character_world_router)
app.include_router(continuity_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "masoud-ai-studio"}


# In a production-style local install, serve the compiled React app from the
# same loopback-only FastAPI process. API routes are registered first so the
# static mount cannot shadow /api or /health.
_frontend_dist = ROOT_DIR / "frontend" / "dist"
if (_frontend_dist / "index.html").is_file():
    app.mount(
        "/",
        StaticFiles(directory=str(_frontend_dist), html=True),
        name="studio-ui",
    )
