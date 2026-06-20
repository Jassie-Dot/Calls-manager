from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from config import settings


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid audio filename")

    audio_dir = Path(settings.AUDIO_DIR).resolve()
    filepath = (audio_dir / filename).resolve()

    if filepath.parent != audio_dir:
        raise HTTPException(status_code=400, detail="Invalid audio filename")

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        str(filepath),
        media_type="audio/mpeg",
        background=BackgroundTask(_delete_later, filepath),
    )


async def _delete_later(filepath: Path) -> None:
    await asyncio.sleep(30)
    try:
        filepath.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not delete temporary audio file %s: %s", filepath, exc)
