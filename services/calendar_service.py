from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import settings


logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarServiceError(Exception):
    """Raised when Google Calendar cannot complete a booking operation."""


def get_calendar_service():
    try:
        creds = None
        credentials_path = Path(settings.GOOGLE_CREDENTIALS_FILE)
        token_path = Path("token.json")

        if credentials_path.exists() and _is_service_account_file(credentials_path):
            creds = service_account.Credentials.from_service_account_file(
                str(credentials_path),
                scopes=SCOPES,
            )
            return build("calendar", "v3", credentials=creds)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not credentials_path.exists():
                    raise CalendarServiceError(f"{settings.GOOGLE_CREDENTIALS_FILE} was not found")
                flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)

            token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("calendar", "v3", credentials=creds)
    except CalendarServiceError:
        raise
    except Exception as exc:
        logger.exception("Failed to build Google Calendar service: %s", exc)
        raise CalendarServiceError("Google Calendar authentication failed") from exc


def check_availability(date_str: str, time_str: str) -> tuple[bool, str | None]:
    try:
        start = _parse_local_datetime(date_str, time_str)
        service = get_calendar_service()

        if not _is_business_slot(start):
            return False, _find_next_available_slot(service, start)

        end = start + dt.timedelta(minutes=settings.SLOT_DURATION_MINUTES)
        if not _has_conflict(service, start, end):
            return True, None

        next_slot = _find_next_available_slot(service, start + dt.timedelta(minutes=30))
        return False, next_slot
    except CalendarServiceError:
        raise
    except Exception as exc:
        logger.exception("Calendar availability check failed: %s", exc)
        raise CalendarServiceError("Calendar availability check failed") from exc


def create_booking(
    customer_name: str,
    date_str: str,
    time_str: str,
    guests: int | None = None,
    notes: str = "",
    service_type: str | None = None,
) -> str:
    try:
        service = get_calendar_service()
        start = _parse_local_datetime(date_str, time_str)
        end = start + dt.timedelta(minutes=settings.SLOT_DURATION_MINUTES)

        summary_detail = f"{guests} guests" if guests else service_type or "consultation"
        description_parts = []
        if service_type:
            description_parts.append(f"Service type: {service_type}")
        if guests:
            description_parts.append(f"Guests/attendees: {guests}")
        if notes:
            description_parts.append(notes)

        event = {
            "summary": f"Booking - {customer_name} ({summary_detail})",
            "description": "\n".join(description_parts),
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": settings.TIMEZONE,
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": settings.TIMEZONE,
            },
        }

        created = (
            service.events()
            .insert(calendarId=settings.GOOGLE_CALENDAR_ID, body=event)
            .execute()
        )
        return str(created["id"])
    except Exception as exc:
        logger.exception("Calendar booking creation failed: %s", exc)
        raise CalendarServiceError("Calendar booking creation failed") from exc


def _parse_local_datetime(date_str: str, time_str: str) -> dt.datetime:
    parsed_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    parsed_time = dt.datetime.strptime(time_str, "%H:%M").time()
    return dt.datetime.combine(parsed_date, parsed_time, tzinfo=ZoneInfo(settings.TIMEZONE))


def _open_day_names() -> set[str]:
    return {day.strip().lower() for day in settings.open_days_list}


def _is_open_day(moment: dt.datetime) -> bool:
    return moment.strftime("%A").lower() in _open_day_names()


def _business_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    tz = ZoneInfo(settings.TIMEZONE)
    open_dt = _business_datetime(day, settings.OPEN_TIME, tz, is_close=False)
    close_dt = _business_datetime(day, settings.CLOSE_TIME, tz, is_close=True)
    if close_dt <= open_dt:
        close_dt += dt.timedelta(days=1)
    return open_dt, close_dt


def _business_datetime(day: dt.date, value: str, tz: ZoneInfo, is_close: bool) -> dt.datetime:
    if value == "24:00" and is_close:
        return dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min, tzinfo=tz)
    parsed_time = dt.datetime.strptime(value, "%H:%M").time()
    return dt.datetime.combine(day, parsed_time, tzinfo=tz)


def _is_business_slot(start: dt.datetime) -> bool:
    if not _is_open_day(start):
        return False
    open_dt, close_dt = _business_bounds(start.date())
    end = start + dt.timedelta(minutes=settings.SLOT_DURATION_MINUTES)
    return open_dt <= start and end <= close_dt


def _has_conflict(service, start: dt.datetime, end: dt.datetime) -> bool:
    body = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "timeZone": settings.TIMEZONE,
        "items": [{"id": settings.GOOGLE_CALENDAR_ID}],
    }
    result = service.freebusy().query(body=body).execute()
    busy = result.get("calendars", {}).get(settings.GOOGLE_CALENDAR_ID, {}).get("busy", [])
    return bool(busy)


def _round_up_to_next_half_hour(moment: dt.datetime) -> dt.datetime:
    minute = moment.minute
    if minute == 0 or minute == 30:
        rounded = moment.replace(second=0, microsecond=0)
    elif minute < 30:
        rounded = moment.replace(minute=30, second=0, microsecond=0)
    else:
        rounded = (moment + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return rounded


def _find_next_available_slot(service, start_search: dt.datetime) -> str | None:
    current_day = start_search.date()
    for day_offset in range(14):
        day = current_day + dt.timedelta(days=day_offset)
        probe = dt.datetime.combine(day, dt.time.min, tzinfo=ZoneInfo(settings.TIMEZONE))
        if not _is_open_day(probe):
            continue

        open_dt, close_dt = _business_bounds(day)
        candidate = max(open_dt, start_search if day == start_search.date() else open_dt)
        candidate = _round_up_to_next_half_hour(candidate)

        while candidate + dt.timedelta(minutes=settings.SLOT_DURATION_MINUTES) <= close_dt:
            end = candidate + dt.timedelta(minutes=settings.SLOT_DURATION_MINUTES)
            if not _has_conflict(service, candidate, end):
                return _format_slot(candidate)
            candidate += dt.timedelta(minutes=30)

    return None


def _format_slot(moment: dt.datetime) -> str:
    hour = moment.strftime("%I").lstrip("0") or "12"
    return f"{moment.strftime('%A, %B %d')} at {hour}:{moment.strftime('%M %p')}"


def credentials_files_exist() -> bool:
    return os.path.exists(settings.GOOGLE_CREDENTIALS_FILE) or os.path.exists("token.json")


def _is_service_account_file(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data.get("type") == "service_account"
    except Exception:
        return False
