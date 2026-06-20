from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    GROQ_API_KEY: str = ""

    GOOGLE_CALENDAR_ID: str = "primary"
    GOOGLE_CREDENTIALS_FILE: str = "credentials.json"
    BASE_URL: str = "http://localhost:8000"

    BUSINESS_NAME: str = "Grand Spice Restaurant"
    BUSINESS_TYPE: str = "restaurant"
    OPEN_DAYS: str = "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday"
    OPEN_TIME: str = "12:00"
    CLOSE_TIME: str = "22:00"
    SLOT_DURATION_MINUTES: int = 60
    TIMEZONE: str = "Asia/Kolkata"

    AUDIO_DIR: str = "/tmp/audio_cache"
    LLM_MODEL: str = "llama-3.1-8b-instant"
    TTS_VOICE: str = "en-IN-NeerjaNeural"
    MAX_TOKENS: int = 120
    SPEECH_TIMEOUT: int = 3
    MIN_SPEECH_CONFIDENCE: float = 0.4

    DEFAULT_LANGUAGE: str = "hinglish"
    DEFAULT_RECOGNITION_LANGUAGE: str = "hi-IN"
    ENGLISH_RECOGNITION_LANGUAGE: str = "en-IN"
    HINDI_RECOGNITION_LANGUAGE: str = "hi-IN"
    HINGLISH_RECOGNITION_LANGUAGE: str = "hi-IN"
    TWILIO_SPEECH_MODEL: str = "phone_call"
    TWILIO_SPEECH_HINTS: str = (
        "booking,reservation,table,appointment,guests,people,namaste,haan,nahi,"
        "kal,aaj,parson,baje,log"
    )

    ENGLISH_TTS_VOICE: str = "en-IN-NeerjaNeural"
    HINDI_TTS_VOICE: str = "hi-IN-SwaraNeural"
    HINGLISH_TTS_VOICE: str = "hi-IN-SwaraNeural"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("BASE_URL")
    @classmethod
    def strip_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def open_days_list(self) -> list[str]:
        return [day.strip() for day in self.OPEN_DAYS.split(",") if day.strip()]


settings = Settings()


def ensure_audio_dir() -> None:
    Path(settings.AUDIO_DIR).mkdir(parents=True, exist_ok=True)


def project_path(filename: str) -> str:
    return os.path.join(os.getcwd(), filename)
