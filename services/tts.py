from __future__ import annotations

import logging
import uuid
from pathlib import Path

import edge_tts
from fastapi import HTTPException

from config import settings


logger = logging.getLogger(__name__)


async def synthesize(text: str, voice: str | None = None) -> str:
    """
    Convert text to speech audio.
    Returns the filename, not the full path, of the saved MP3.
    """
    filename = f"{uuid.uuid4()}.mp3"
    filepath = Path(settings.AUDIO_DIR) / filename
    selected_voice = voice or settings.TTS_VOICE

    try:
        communicate = edge_tts.Communicate(text, selected_voice)
        await communicate.save(str(filepath))
        return filename
    except Exception as exc:
        logger.exception("TTS generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="TTS generation failed") from exc


def get_audio_url(filename: str) -> str:
    return f"{settings.BASE_URL}/audio/{filename}"
