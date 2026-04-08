from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CATEGORY_COLOR_IDS: dict[str, str] = {
    "Work": "7",        # Peacock (teal)
    "Deep Work": "3",   # Grape (purple)
    "Exercise": "2",    # Sage (green)
    "Meals": "5",       # Banana (yellow)
    "Social": "4",      # Flamingo (pink)
    "Rest": "9",        # Blueberry (dark blue)
    "Learning": "10",   # Basil (dark green)
    "Admin": "8",       # Graphite (gray)
    "Personal": "1",    # Lavender
    "Sleep": "9",       # Blueberry
}

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarClient:
    def __init__(self, credentials_path: str, token_path: str, calendar_id: str = "primary") -> None:
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.calendar_id = calendar_id
        self._service = None

    def is_configured(self) -> bool:
        return os.path.exists(self.credentials_path)

    def is_authenticated(self) -> bool:
        return os.path.exists(self.token_path)

    def _build_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                Path(self.token_path).write_text(creds.to_json())
            else:
                raise RuntimeError(
                    "Google Calendar token missing. Run `python setup_gcal.py` to authorize."
                )
        return build("calendar", "v3", credentials=creds)

    def _get_service(self):
        if self._service is None:
            self._service = self._build_service()
        return self._service

    async def create_event(self, entry: dict[str, Any]) -> str:
        service = await asyncio.to_thread(self._get_service)
        color_id = CATEGORY_COLOR_IDS.get(entry["category"], "8")
        body = {
            "summary": entry["title"],
            "description": _format_description(entry),
            "start": {"dateTime": entry["start"].isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": entry["end"].isoformat(), "timeZone": "UTC"},
            "colorId": color_id,
        }
        result = await asyncio.to_thread(
            lambda: service.events().insert(calendarId=self.calendar_id, body=body).execute()
        )
        return result["id"]

    async def update_event(self, event_id: str, entry: dict[str, Any]) -> None:
        service = await asyncio.to_thread(self._get_service)
        color_id = CATEGORY_COLOR_IDS.get(entry["category"], "8")
        body = {
            "summary": entry["title"],
            "description": _format_description(entry),
            "start": {"dateTime": entry["start"].isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": entry["end"].isoformat(), "timeZone": "UTC"},
            "colorId": color_id,
        }
        await asyncio.to_thread(
            lambda: service.events().update(calendarId=self.calendar_id, eventId=event_id, body=body).execute()
        )

    async def delete_event(self, event_id: str) -> None:
        service = await asyncio.to_thread(self._get_service)
        await asyncio.to_thread(
            lambda: service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
        )


def _format_description(entry: dict[str, Any]) -> str:
    lines = [
        f"Category: {entry['category']}",
        f"Duration: {entry['duration']} min",
    ]
    if entry.get("tags"):
        lines.append(f"Tags: {', '.join(entry['tags'])}")
    if entry.get("energy_level"):
        lines.append(f"Energy: {entry['energy_level']}")
    if entry.get("source"):
        lines.append(f"Source: {entry['source']}")
    if entry.get("notes"):
        lines.append(f"\n{entry['notes']}")
    return "\n".join(lines)
