from __future__ import annotations

import asyncio
from typing import Any

from notion_client import Client


class NotionService:
    def __init__(self, api_key: str, database_id: str | None) -> None:
        self.client = Client(auth=api_key)
        self.database_id = database_id

    def is_configured(self) -> bool:
        return bool(self.database_id)

    async def create_database(self, parent_page_id: str, title: str = "Telegram Calendar Activity Log") -> dict[str, Any]:
        return await asyncio.to_thread(
            self.client.databases.create,
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": title}}],
            properties={
                "Title": {"title": {}},
                "Date": {"date": {}},
                "Duration": {"number": {"format": "number"}},
                "Category": {"select": {"options": [{"name": name} for name in [
                    "Work", "Deep Work", "Exercise", "Meals", "Social", "Rest", "Learning", "Admin", "Personal", "Sleep"
                ]]}},
                "Tags": {"multi_select": {"options": []}},
                "Energy Level": {"select": {"options": [{"name": item} for item in ["Low", "Medium", "High"]]}},
                "Notes": {"rich_text": {}},
                "Source": {"select": {"options": [{"name": item} for item in ["Manual", "Auto-logged", "Inferred"]]}},
                "Day Rating": {"number": {"format": "number"}},
            },
        )

    async def create_entry(self, entry: dict[str, Any]) -> str:
        if not self.database_id:
            raise RuntimeError("NOTION_DATABASE_ID is not configured.")
        response = await asyncio.to_thread(
            self.client.pages.create,
            parent={"database_id": self.database_id},
            properties=self._props(entry),
        )
        return response["id"]

    async def update_entry(self, page_id: str, entry: dict[str, Any]) -> None:
        await asyncio.to_thread(self.client.pages.update, page_id=page_id, properties=self._props(entry))

    async def archive_entry(self, page_id: str) -> None:
        await asyncio.to_thread(self.client.pages.update, page_id=page_id, archived=True)

    def _props(self, entry: dict[str, Any]) -> dict[str, Any]:
        props: dict[str, Any] = {
            "Title": {"title": [{"text": {"content": entry["title"][:2000]}}]},
            "Date": {"date": {"start": entry["start"].isoformat(), "end": entry["end"].isoformat()}},
            "Duration": {"number": entry["duration"]},
            "Category": {"select": {"name": entry["category"]}},
            "Tags": {"multi_select": [{"name": tag[:100]} for tag in entry.get("tags", [])]},
            "Notes": {"rich_text": [{"text": {"content": (entry.get("notes") or "")[:2000]}}]},
            "Source": {"select": {"name": entry.get("source", "Manual")}},
            "Day Rating": {"number": entry.get("day_rating")},
        }
        if entry.get("energy_level"):
            props["Energy Level"] = {"select": {"name": entry["energy_level"]}}
        return props
