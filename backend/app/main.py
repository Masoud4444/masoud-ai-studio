from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from .api import router
from .database import Base, engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is a development bootstrap only. Managed installs use Alembic.
    if os.getenv("MASOUD_STUDIO_SCHEMA_MODE", "migrate").lower() == "create":
        os.makedirs("data", exist_ok=True)
        Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Masoud AI Studio API", version="0.2.0",
              description="Private, local-first creative production studio", lifespan=lifespan)
app.include_router(router)

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "masoud-ai-studio"}
