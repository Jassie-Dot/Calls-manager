from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from config import settings


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    display_name: str
    recognition_language: str
    tts_voice: str

    def to_state(self) -> dict[str, str]:
        return asdict(self)


HINDI_ROMAN_TOKENS = {
    "aaj",
    "abhi",
    "agle",
    "apna",
    "batao",
    "baje",
    "booking",
    "chahiye",
    "chaiye",
    "hai",
    "haan",
    "han",
    "ji",
    "kal",
    "kar",
    "karna",
    "karni",
    "ke",
    "liye",
    "log",
    "mera",
    "meri",
    "mujhe",
    "nahi",
    "nahin",
    "namaste",
    "parson",
    "reservation",
    "table",
    "theek",
}

ENGLISH_HINT_TOKENS = {
    "book",
    "booking",
    "reservation",
    "table",
    "appointment",
    "tomorrow",
    "today",
    "tonight",
    "people",
    "guests",
    "please",
    "name",
    "time",
}

SHORT_ACKS = {"ok", "okay", "yes", "yeah", "yep", "haan", "han", "ji", "theek", "sure"}


def get_profile(code: str | None = None) -> LanguageProfile:
    normalized = (code or settings.DEFAULT_LANGUAGE or "hinglish").lower()
    if normalized == "en":
        return LanguageProfile(
            code="en",
            display_name="English",
            recognition_language=settings.ENGLISH_RECOGNITION_LANGUAGE,
            tts_voice=settings.ENGLISH_TTS_VOICE,
        )
    if normalized == "hi":
        return LanguageProfile(
            code="hi",
            display_name="Hindi",
            recognition_language=settings.HINDI_RECOGNITION_LANGUAGE,
            tts_voice=settings.HINDI_TTS_VOICE,
        )
    return LanguageProfile(
        code="hinglish",
        display_name="Hinglish",
        recognition_language=settings.HINGLISH_RECOGNITION_LANGUAGE,
        tts_voice=settings.HINGLISH_TTS_VOICE,
    )


def detect_language(text: str, previous_code: str | None = None) -> LanguageProfile:
    stripped = text.strip()
    if not stripped:
        return get_profile(previous_code)

    words = re.findall(r"[A-Za-z]+", stripped.lower())
    if len(words) <= 2 and words and set(words).issubset(SHORT_ACKS) and previous_code:
        return get_profile(previous_code)

    devanagari_count = sum(1 for char in stripped if "\u0900" <= char <= "\u097f")
    hindi_score = sum(1 for word in words if word in HINDI_ROMAN_TOKENS)
    english_score = sum(1 for word in words if word in ENGLISH_HINT_TOKENS)
    alpha_words = len(words)

    if devanagari_count >= 2:
        if english_score >= 1 or alpha_words >= 2:
            return get_profile("hinglish")
        return get_profile("hi")

    if hindi_score >= 2 and english_score >= 1:
        return get_profile("hinglish")

    if hindi_score >= 2:
        if previous_code == "en" and english_score > 0:
            return get_profile("hinglish")
        return get_profile("hi")

    if hindi_score == 1 and previous_code in {"hi", "hinglish"}:
        return get_profile(previous_code)

    return get_profile("en")


def bilingual_greeting(business_name: str) -> str:
    return (
        f"Namaste, thank you for calling {business_name}. "
        "Main Alex hoon, your AI assistant. How can I help you today?"
    )


def repeat_prompt(profile: LanguageProfile) -> str:
    if profile.code == "hi":
        return "Maaf kijiye, mujhe saaf samajh nahi aaya. Kya aap dobara bata sakte hain?"
    if profile.code == "hinglish":
        return "Sorry, mujhe clearly samajh nahi aaya. Could you please repeat that?"
    return "I'm sorry, I didn't catch that. Could you repeat that?"


def goodbye_text(profile: LanguageProfile) -> str:
    if profile.code == "hi":
        return "Dhanyavaad, call karne ke liye. Alvida."
    if profile.code == "hinglish":
        return "Thank you for calling. Have a great day."
    return "Thank you for calling. Goodbye."


def speech_hints() -> str:
    return settings.TWILIO_SPEECH_HINTS
