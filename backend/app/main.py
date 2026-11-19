from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env", override=False)

from .api import router
from .character_world import router as character_world_router
from .continuity import router as continuity_router
from .timeline import router as timeline_router
from .props import router as props_router
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
    app.state.worker_enabled = os.getenv("MASOUD_STUDIO_WORKER_ENABLED", "false").lower() == "true"
    app.state.worker_id = os.getenv("MASOUD_STUDIO_WORKER_ID", "local-worker-1")
    app.state.worker_handlers = []
    app.state.worker_task = None
    if app.state.worker_enabled:
        registry = TaskHandlerRegistry()
        # The only built-in handler is a safe smoke-test task. Production
        # workflow handlers are registered by their owning modules later.
        registry.register("system.healthcheck", lambda _payload: {"ok": True})
        supervisor = WorkerSupervisor(
            session_factory=SessionLocal,
            worker_id=os.getenv("MASOUD_STUDIO_WORKER_ID", "local-worker-1"),
            registry=registry,
        )
        app.state.worker_handlers = registry.task_types
        worker_task = asyncio.create_task(supervisor.run_forever())
        app.state.worker_task = worker_task

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
# Packaged desktop mode rejects DNS-rebinding Host headers and cross-origin browser
# requests to the loopback API. CLI clients without an Origin header remain supported.
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import JSONResponse


@app.middleware("http")
async def protect_local_desktop_api(request: Request, call_next):
    if os.getenv("MASOUD_STUDIO_DESKTOP_MODE", "false").lower() != "true":
        return await call_next(request)

    expected_port = int(os.getenv("MASOUD_STUDIO_PORT", "8000"))
    host = request.url.hostname
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    if host not in {"127.0.0.1", "localhost"} or port != expected_port:
        return JSONResponse({"detail": "Invalid local Host header"}, status_code=421)

    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
                or origin_port != expected_port or parsed.username or parsed.password):
            return JSONResponse({"detail": "Cross-origin requests are not allowed"}, status_code=403)

    return await call_next(request)


app.include_router(router)
app.include_router(character_world_router)
app.include_router(continuity_router)
app.include_router(timeline_router)
app.include_router(props_router)


@app.get("/api/v1/settings/runtime", tags=["settings"])
def runtime_diagnostics():
    database = {"status": "ok"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database = {"status": "unavailable"}
    worker_task = getattr(app.state, "worker_task", None)
    worker_enabled = bool(getattr(app.state, "worker_enabled", False))
    worker_running = bool(worker_task is not None and not worker_task.done())
    return {
        "backend": {"status": "ok", "version": app.version},
        "database": database,
        "worker": {
            "enabled": worker_enabled,
            "status": "running" if worker_running else ("stopped" if worker_enabled else "disabled"),
            "worker_id": getattr(app.state, "worker_id", "local-worker-1"),
            "registered_handlers": list(getattr(app.state, "worker_handlers", [])),
        },
        "execution_note": "Only registered task handlers can be claimed; the built-in healthcheck is not a creative production handler.",
    }


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
