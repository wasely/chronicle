from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @asynccontextmanager
    async def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def init(self) -> None:
        async with self.connect() as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_state (
                    chat_id INTEGER PRIMARY KEY,
                    timezone TEXT NOT NULL,
                    wake_time TEXT NOT NULL DEFAULT '07:00',
                    sleep_time TEXT NOT NULL DEFAULT '23:00',
                    checkin_frequency_minutes INTEGER NOT NULL DEFAULT 15,
                    paused_until_utc TEXT,
                    is_sleeping INTEGER NOT NULL DEFAULT 0,
                    sleep_started_utc TEXT,
                    last_checkin_utc TEXT,
                    last_logged_end_utc TEXT,
                    last_activity_title TEXT,
                    streak_count INTEGER NOT NULL DEFAULT 0,
                    onboarding_step TEXT,
                    onboarding_data_json TEXT,
                    pending_prompt TEXT,
                    pending_prompt_payload TEXT,
                    last_morning_prompt_date TEXT,
                    last_eod_prompt_date TEXT,
                    checkin_style_index INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS activity_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    notion_page_id TEXT,
                    title TEXT NOT NULL,
                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    energy_level TEXT,
                    notes TEXT,
                    source TEXT NOT NULL,
                    day_rating INTEGER,
                    synced INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS outbound_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS pending_preview (
                    chat_id INTEGER PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await db.commit()

    async def get_user(self, chat_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cur = await db.execute("SELECT * FROM user_state WHERE chat_id = ?", (chat_id,))
            row = await cur.fetchone()
        return dict(row) if row else None

    async def ensure_user(self, chat_id: int, timezone: str) -> dict[str, Any]:
        user = await self.get_user(chat_id)
        if user:
            return user
        user = {
            "chat_id": chat_id,
            "timezone": timezone,
            "wake_time": "07:00",
            "sleep_time": "23:00",
            "checkin_frequency_minutes": 15,
            "paused_until_utc": None,
            "is_sleeping": 0,
            "sleep_started_utc": None,
            "last_checkin_utc": None,
            "last_logged_end_utc": None,
            "last_activity_title": None,
            "streak_count": 0,
            "onboarding_step": None,
            "onboarding_data_json": None,
            "pending_prompt": None,
            "pending_prompt_payload": None,
            "last_morning_prompt_date": None,
            "last_eod_prompt_date": None,
            "checkin_style_index": 0,
        }
        await self.upsert_user(user)
        return user

    async def list_users(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cur = await db.execute("SELECT * FROM user_state ORDER BY chat_id ASC")
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def upsert_user(self, user: dict[str, Any]) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO user_state (
                    chat_id, timezone, wake_time, sleep_time, checkin_frequency_minutes,
                    paused_until_utc, is_sleeping, sleep_started_utc, last_checkin_utc,
                    last_logged_end_utc, last_activity_title, streak_count, onboarding_step,
                    onboarding_data_json, pending_prompt, pending_prompt_payload,
                    last_morning_prompt_date, last_eod_prompt_date, checkin_style_index
                ) VALUES (
                    :chat_id, :timezone, :wake_time, :sleep_time, :checkin_frequency_minutes,
                    :paused_until_utc, :is_sleeping, :sleep_started_utc, :last_checkin_utc,
                    :last_logged_end_utc, :last_activity_title, :streak_count, :onboarding_step,
                    :onboarding_data_json, :pending_prompt, :pending_prompt_payload,
                    :last_morning_prompt_date, :last_eod_prompt_date, :checkin_style_index
                )
                ON CONFLICT(chat_id) DO UPDATE SET
                    timezone = excluded.timezone,
                    wake_time = excluded.wake_time,
                    sleep_time = excluded.sleep_time,
                    checkin_frequency_minutes = excluded.checkin_frequency_minutes,
                    paused_until_utc = excluded.paused_until_utc,
                    is_sleeping = excluded.is_sleeping,
                    sleep_started_utc = excluded.sleep_started_utc,
                    last_checkin_utc = excluded.last_checkin_utc,
                    last_logged_end_utc = excluded.last_logged_end_utc,
                    last_activity_title = excluded.last_activity_title,
                    streak_count = excluded.streak_count,
                    onboarding_step = excluded.onboarding_step,
                    onboarding_data_json = excluded.onboarding_data_json,
                    pending_prompt = excluded.pending_prompt,
                    pending_prompt_payload = excluded.pending_prompt_payload,
                    last_morning_prompt_date = excluded.last_morning_prompt_date,
                    last_eod_prompt_date = excluded.last_eod_prompt_date,
                    checkin_style_index = excluded.checkin_style_index
                """,
                user,
            )
            await db.commit()

    async def save_pending_preview(self, chat_id: int, draft: dict[str, Any]) -> None:
        payload = dict(draft)
        payload["start"] = draft["start"].isoformat()
        payload["end"] = draft["end"].isoformat()
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO pending_preview (chat_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET payload_json = excluded.payload_json, created_at_utc = CURRENT_TIMESTAMP
                """,
                (chat_id, json.dumps(payload)),
            )
            await db.commit()

    async def get_pending_preview(self, chat_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cur = await db.execute("SELECT payload_json FROM pending_preview WHERE chat_id = ?", (chat_id,))
            row = await cur.fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        payload["start"] = datetime.fromisoformat(payload["start"])
        payload["end"] = datetime.fromisoformat(payload["end"])
        return payload

    async def clear_pending_preview(self, chat_id: int) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM pending_preview WHERE chat_id = ?", (chat_id,))
            await db.commit()

    async def add_activity(self, chat_id: int, entry: dict[str, Any], synced: bool) -> int:
        async with self.connect() as db:
            cur = await db.execute(
                """
                INSERT INTO activity_cache (
                    chat_id, notion_page_id, title, start_utc, end_utc, duration_minutes,
                    category, tags_json, energy_level, notes, source, day_rating, synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    entry.get("notion_page_id"),
                    entry["title"],
                    entry["start"].isoformat(),
                    entry["end"].isoformat(),
                    entry["duration"],
                    entry["category"],
                    json.dumps(entry.get("tags", [])),
                    entry.get("energy_level"),
                    entry.get("notes"),
                    entry.get("source", "Manual"),
                    entry.get("day_rating"),
                    1 if synced else 0,
                ),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def update_activity(self, activity_id: int, entry: dict[str, Any], synced: bool) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE activity_cache SET
                    notion_page_id = ?, title = ?, start_utc = ?, end_utc = ?, duration_minutes = ?,
                    category = ?, tags_json = ?, energy_level = ?, notes = ?, source = ?, day_rating = ?, synced = ?
                WHERE id = ?
                """,
                (
                    entry.get("notion_page_id"),
                    entry["title"],
                    entry["start"].isoformat(),
                    entry["end"].isoformat(),
                    entry["duration"],
                    entry["category"],
                    json.dumps(entry.get("tags", [])),
                    entry.get("energy_level"),
                    entry.get("notes"),
                    entry.get("source", "Manual"),
                    entry.get("day_rating"),
                    1 if synced else 0,
                    activity_id,
                ),
            )
            await db.commit()

    async def mark_activity_synced(self, activity_id: int, notion_page_id: str) -> None:
        async with self.connect() as db:
            await db.execute("UPDATE activity_cache SET synced = 1, notion_page_id = ? WHERE id = ?", (notion_page_id, activity_id))
            await db.commit()

    async def get_activity(self, activity_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            cur = await db.execute("SELECT * FROM activity_cache WHERE id = ?", (activity_id,))
            row = await cur.fetchone()
        return dict(row) if row else None

    async def archive_activity(self, activity_id: int) -> None:
        async with self.connect() as db:
            await db.execute("UPDATE activity_cache SET archived = 1 WHERE id = ?", (activity_id,))
            await db.commit()

    async def recent_activities(self, chat_id: int, limit: int = 5) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT * FROM activity_cache WHERE chat_id = ? AND archived = 0 ORDER BY start_utc DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def activities_between(self, chat_id: int, start_utc: datetime, end_utc: datetime) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cur = await db.execute(
                """
                SELECT * FROM activity_cache
                WHERE chat_id = ? AND archived = 0 AND start_utc < ? AND end_utc > ?
                ORDER BY start_utc ASC
                """,
                (chat_id, end_utc.isoformat(), start_utc.isoformat()),
            )
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def queue_action(self, chat_id: int, action: str, payload: dict[str, Any], last_error: str | None = None) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO outbound_queue (chat_id, action, payload_json, last_error) VALUES (?, ?, ?, ?)",
                (chat_id, action, json.dumps(payload), last_error),
            )
            await db.commit()

    async def queue_items(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.connect() as db:
            cur = await db.execute("SELECT * FROM outbound_queue ORDER BY created_at_utc ASC LIMIT ?", (limit,))
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def queue_done(self, queue_id: int) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM outbound_queue WHERE id = ?", (queue_id,))
            await db.commit()

    async def queue_retry(self, queue_id: int, last_error: str) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE outbound_queue SET retry_count = retry_count + 1, last_error = ?, updated_at_utc = CURRENT_TIMESTAMP WHERE id = ?",
                (last_error, queue_id),
            )
            await db.commit()
