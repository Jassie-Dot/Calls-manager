from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from groq import Groq

from config import settings


logger = logging.getLogger(__name__)
client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


BOOKING_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_and_book_appointment",
        "description": (
            "Call this when you have all four pieces of info: customer name, "
            "date (YYYY-MM-DD), time (HH:MM, 24hr), and either number of guests "
            "for restaurants or service/project type for service businesses. "
            "This checks availability and creates the booking."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM in 24-hour format"},
                "guests": {"type": "integer", "minimum": 1},
                "service_type": {
                    "type": "string",
                    "description": "Service or project type for non-restaurant businesses, such as website redesign, ecommerce site, SEO, or consultation.",
                },
                "notes": {"type": "string", "description": "Any special requests"},
            },
            "required": ["customer_name", "date", "time"],
        },
    },
}


def _messages(system_prompt: str, history: list[dict[str, str]], user_message: str | None = None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    if user_message:
        last = messages[-1] if messages else {}
        if last.get("role") != "user" or last.get("content") != user_message:
            messages.append({"role": "user", "content": user_message})
    return messages


def _create_completion(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not configured")

    kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "max_tokens": settings.MAX_TOKENS,
        "temperature": 0.7,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def _fallback_response() -> str:
    return "I'm having a small issue. Could you please hold for a moment and try again?"


async def get_response(
    user_message: str,
    history: list[dict[str, str]],
    system_prompt: str,
) -> tuple[str | None, dict[str, Any] | None]:
    try:
        messages = _messages(system_prompt, history, user_message)
        response = await asyncio.to_thread(_create_completion, messages, [BOOKING_TOOL])
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)

        if tool_calls:
            tool_call = tool_calls[0]
            raw_arguments = tool_call.function.arguments or "{}"
            try:
                tool_args = json.loads(raw_arguments)
            except json.JSONDecodeError:
                logger.warning("Model returned invalid tool JSON: %s", raw_arguments)
                tool_args = {}

            tool_args["_tool_call_id"] = tool_call.id
            tool_args["_tool_call_name"] = tool_call.function.name
            tool_args["_raw_tool_arguments"] = raw_arguments
            return None, tool_args

        return (message.content or _fallback_response()).strip(), None
    except Exception as exc:
        logger.exception("Groq response failed: %s", exc)
        return _fallback_response(), None


async def get_response_after_tool(
    history: list[dict[str, str]],
    system_prompt: str,
    tool_call_args: dict[str, Any],
    tool_result: str,
) -> str:
    try:
        messages = _messages(system_prompt, history)
        tool_call_id = str(tool_call_args.get("_tool_call_id") or "booking_call")
        raw_arguments = str(tool_call_args.get("_raw_tool_arguments") or "{}")
        tool_name = str(tool_call_args.get("_tool_call_name") or "check_and_book_appointment")

        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": raw_arguments,
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_result,
            }
        )

        response = await asyncio.to_thread(_create_completion, messages, None)
        return (response.choices[0].message.content or _fallback_response()).strip()
    except Exception as exc:
        logger.exception("Groq follow-up response failed: %s", exc)
        return _fallback_response()
