from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import Gather, VoiceResponse

from config import settings
from prompts.system_prompt import get_system_prompt
from services import calendar_service, language, llm, tts
from services.calendar_service import CalendarServiceError
from services.language import LanguageProfile
from utils import state


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/incoming-call")
async def incoming_call(request: Request) -> Response:
    form = await request.form()
    call_sid = str(form.get("CallSid") or f"local-{uuid.uuid4()}")
    state.get_state(call_sid)

    profile = language.get_profile(settings.DEFAULT_LANGUAGE)
    state.set_language(call_sid, profile.to_state())

    greeting = language.bilingual_greeting(settings.BUSINESS_NAME)
    state.update_history(call_sid, "assistant", greeting)
    return await _voice_response(greeting, profile, gather=True)


@router.post("/handle-speech")
async def handle_speech(request: Request) -> Response:
    form = await request.form()
    call_sid = str(form.get("CallSid") or f"local-{uuid.uuid4()}")
    speech_result = str(form.get("SpeechResult") or "").strip()
    confidence = _parse_confidence(form.get("Confidence"))

    previous_language = state.get_language(call_sid)
    previous_profile = language.get_profile(previous_language.get("code"))

    if not speech_result or confidence < settings.MIN_SPEECH_CONFIDENCE:
        reply = language.repeat_prompt(previous_profile)
        return await _voice_response(reply, previous_profile, gather=True)

    profile = language.detect_language(speech_result, previous_profile.code)
    state.set_language(call_sid, profile.to_state())
    state.update_history(call_sid, "user", speech_result)

    system_prompt = get_system_prompt(
        business_name=settings.BUSINESS_NAME,
        business_type=settings.BUSINESS_TYPE,
        open_days=settings.open_days_list,
        open_time=settings.OPEN_TIME,
        close_time=settings.CLOSE_TIME,
        timezone_name=settings.TIMEZONE,
        caller_language=profile.display_name,
    )
    history = state.get_history(call_sid)
    response_text, tool_call_args = await llm.get_response(speech_result, history, system_prompt)
    booking_confirmed = False

    if tool_call_args is not None:
        tool_result, booking_confirmed = await _process_booking_tool(tool_call_args)
        response_text = await llm.get_response_after_tool(history, system_prompt, tool_call_args, tool_result)

    response_text = response_text or language.repeat_prompt(profile)
    state.update_history(call_sid, "assistant", response_text)

    if booking_confirmed:
        state.set_confirmed(call_sid, True)
        return await _voice_response(response_text, profile, gather=False, hangup=True)

    return await _voice_response(response_text, profile, gather=True)


@router.post("/call-status")
async def call_status(request: Request) -> Response:
    form = await request.form()
    call_sid = str(form.get("CallSid") or "")
    call_status_value = str(form.get("CallStatus") or "").lower()

    if call_sid and call_status_value in {"completed", "failed", "busy", "no-answer", "canceled"}:
        state.clear_state(call_sid)

    return Response(content="", media_type="text/plain")


async def _process_booking_tool(tool_call_args: dict[str, Any]) -> tuple[str, bool]:
    validation_error = _validate_tool_args(tool_call_args)
    if validation_error:
        result = {
            "status": "needs_clarification",
            "message": validation_error,
            "instruction": "Ask the caller for the missing or corrected booking detail.",
        }
        return json.dumps(result), False

    customer_name = str(tool_call_args["customer_name"]).strip()
    date_str = str(tool_call_args["date"]).strip()
    time_str = str(tool_call_args["time"]).strip()
    guests = int(tool_call_args["guests"]) if tool_call_args.get("guests") else None
    service_type = str(tool_call_args.get("service_type") or "").strip()
    notes = str(tool_call_args.get("notes") or "").strip()

    try:
        available, next_slot = await asyncio.to_thread(calendar_service.check_availability, date_str, time_str)
        if available:
            event_id = await asyncio.to_thread(
                calendar_service.create_booking,
                customer_name,
                date_str,
                time_str,
                guests,
                notes,
                service_type,
            )
            result = {
                "status": "confirmed",
                "event_id": event_id,
                "customer_name": customer_name,
                "date": date_str,
                "time": time_str,
                "guests": guests,
                "service_type": service_type,
                "instruction": "Tell the caller the booking is confirmed, then end the call.",
            }
            return json.dumps(result), True

        result = {
            "status": "unavailable",
            "requested_date": date_str,
            "requested_time": time_str,
            "next_available": next_slot,
            "instruction": "Apologize briefly, suggest the next slot, and ask if it works.",
        }
        return json.dumps(result), False
    except CalendarServiceError as exc:
        logger.exception("Calendar service error during booking: %s", exc)
        result = {
            "status": "calendar_error",
            "instruction": "Tell the caller a human team member will call back to confirm the booking.",
        }
        return json.dumps(result), False


def _validate_tool_args(tool_call_args: dict[str, Any]) -> str | None:
    required = ["customer_name", "date", "time"]
    missing = [field for field in required if tool_call_args.get(field) in {None, ""}]
    if missing:
        return f"Missing required booking fields: {', '.join(missing)}."

    try:
        datetime.strptime(str(tool_call_args["date"]), "%Y-%m-%d")
    except ValueError:
        return "The date must be in YYYY-MM-DD format."

    try:
        datetime.strptime(str(tool_call_args["time"]), "%H:%M")
    except ValueError:
        return "The time must be in HH:MM 24-hour format."

    business_type = settings.BUSINESS_TYPE.lower()
    is_restaurant = any(word in business_type for word in ["restaurant", "cafe", "bar", "dining"])

    if is_restaurant:
        if tool_call_args.get("guests") in {None, ""}:
            return "The number of guests is required for restaurant bookings."
        try:
            guests = int(tool_call_args["guests"])
        except (TypeError, ValueError):
            return "The number of guests must be a whole number."
        if guests < 1:
            return "The number of guests must be at least 1."
    elif not str(tool_call_args.get("service_type") or "").strip():
        return "The service or project type is required for this business."

    return None


async def _voice_response(
    text: str,
    profile: LanguageProfile,
    gather: bool,
    hangup: bool = False,
) -> Response:
    twiml = VoiceResponse()

    try:
        filename = await tts.synthesize(text, profile.tts_voice)
        twiml.play(tts.get_audio_url(filename))
    except Exception as exc:
        logger.warning("Falling back to Twilio Say because TTS failed: %s", exc)
        twiml.say(text)

    if gather:
        gather_node = Gather(
            input="speech",
            action=_action_url("/handle-speech"),
            method="POST",
            speech_timeout=settings.SPEECH_TIMEOUT,
            speech_model=settings.TWILIO_SPEECH_MODEL,
            language=profile.recognition_language,
            hints=language.speech_hints(),
        )
        twiml.append(gather_node)
        twiml.say(language.goodbye_text(profile))

    if hangup:
        twiml.hangup()

    return Response(content=str(twiml), media_type="text/xml")


def _action_url(path: str) -> str:
    if settings.BASE_URL:
        return f"{settings.BASE_URL}{path}"
    return path


def _parse_confidence(value: Any) -> float:
    if value in {None, ""}:
        return 1.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0
