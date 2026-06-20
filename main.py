from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import ensure_audio_dir, settings
from routes.audio_routes import router as audio_router
from routes.call_routes import router as call_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_audio_dir()
    yield


app = FastAPI(title="AI Phone Booking Agent", lifespan=lifespan)
app.include_router(call_router)
app.include_router(audio_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "business": settings.BUSINESS_NAME}
