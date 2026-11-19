from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from .api import router
from .database import Base, engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Masoud AI Studio API", version="0.1.0",
              description="Private, local-first creative production studio", lifespan=lifespan)
app.include_router(router)

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "masoud-ai-studio"}
