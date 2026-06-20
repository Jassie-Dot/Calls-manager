from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any

from config import settings


_store: dict[str, dict[str, Any]] = {}
_lock = Lock()


def _fresh_state() -> dict[str, Any]:
    return {
        "history": [],
        "booking": {
            "name": None,
            "date": None,
            "time": None,
            "guests": None,
            "service_type": None,
        },
        "language": {
            "code": settings.DEFAULT_LANGUAGE,
            "recognition_language": settings.DEFAULT_RECOGNITION_LANGUAGE,
            "tts_voice": settings.HINGLISH_TTS_VOICE,
        },
        "confirmed": False,
    }


def get_state(call_sid: str) -> dict[str, Any]:
    with _lock:
        if call_sid not in _store:
            _store[call_sid] = _fresh_state()
        return _store[call_sid]


def update_history(call_sid: str, role: str, content: str) -> None:
    with _lock:
        state = _store.setdefault(call_sid, _fresh_state())
        state["history"].append({"role": role, "content": content})
        state["history"] = state["history"][-24:]


def clear_state(call_sid: str) -> None:
    with _lock:
        _store.pop(call_sid, None)


def get_history(call_sid: str) -> list[dict[str, str]]:
    with _lock:
        return deepcopy(_store.setdefault(call_sid, _fresh_state())["history"])


def set_language(call_sid: str, language: dict[str, str]) -> None:
    with _lock:
        state = _store.setdefault(call_sid, _fresh_state())
        state["language"] = language


def get_language(call_sid: str) -> dict[str, str]:
    with _lock:
        return deepcopy(_store.setdefault(call_sid, _fresh_state())["language"])


def set_confirmed(call_sid: str, confirmed: bool) -> None:
    with _lock:
        state = _store.setdefault(call_sid, _fresh_state())
        state["confirmed"] = confirmed
