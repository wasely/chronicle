from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .config import CHECKIN_MESSAGES


class TelegramCalendarScheduler:
    def __init__(self, handlers) -> None:
        self.handlers = handlers
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self, app) -> None:
        self.scheduler.add_job(self.tick, "interval", minutes=1, args=[app], id="telegram_calendar_tick", replace_existing=True)
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def tick(self, app) -> None:
        await self.handlers.sync_queue()
        for user in await self.handlers.db.list_users():
            await self._handle_user(app, user)

    async def _handle_user(self, app, user: dict) -> None:
        now = datetime.now(UTC)
        local_now = now.astimezone(ZoneInfo(user["timezone"]))
        if user.get("paused_until_utc") and datetime.fromisoformat(user["paused_until_utc"]) > now:
            return
        if local_now.hour == 9 and local_now.minute < 2 and user.get("last_morning_prompt_date") != local_now.strftime("%Y-%m-%d"):
            await self.handlers.send_morning_message(app, user)
            user["last_morning_prompt_date"] = local_now.strftime("%Y-%m-%d")
            await self.handlers.db.upsert_user(user)
        if local_now.hour == 22 and local_now.minute < 2 and user.get("last_eod_prompt_date") != local_now.strftime("%Y-%m-%d"):
            user["pending_prompt"] = "awaiting_eod_rating"
            user["last_eod_prompt_date"] = local_now.strftime("%Y-%m-%d")
            await self.handlers.db.upsert_user(user)
            await self.handlers.send_text(app, user["chat_id"], "End-of-day review. Rate your day 1-10, then I'll ask for notes and your planned wake time.")
        if user.get("is_sleeping"):
            return
        due = not user.get("last_checkin_utc") or now - datetime.fromisoformat(user["last_checkin_utc"]) >= timedelta(minutes=user["checkin_frequency_minutes"])
        if not due:
            return

        if user.get("last_logged_end_utc"):
            gap = int((now - datetime.fromisoformat(user["last_logged_end_utc"])).total_seconds() // 60)
            if gap > 90:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("Yes, fill gap", callback_data="gap:fill"),
                    InlineKeyboardButton("Leave blank", callback_data="gap:leave"),
                    InlineKeyboardButton("I was sleeping", callback_data="gap:sleep"),
                ]])
                await self.handlers.send_text(app, user["chat_id"], f"I noticed a ~{self.handlers.human_duration(gap)} gap. Want to fill that in?", keyboard)

        prompt = CHECKIN_MESSAGES[user["checkin_style_index"] % len(CHECKIN_MESSAGES)]
        if user["checkin_frequency_minutes"] != 15:
            prompt = prompt.replace("15-min", f"{user['checkin_frequency_minutes']}-min").replace("past 15 min", f"past {user['checkin_frequency_minutes']} min")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Log it", callback_data="checkin:log"),
            InlineKeyboardButton("Skip", callback_data="checkin:skip"),
            InlineKeyboardButton("I'm sleeping", callback_data="checkin:sleep"),
        ]])
        await self.handlers.send_text(app, user["chat_id"], prompt, keyboard)
        user["last_checkin_utc"] = now.isoformat()
        user["checkin_style_index"] += 1
        await self.handlers.db.upsert_user(user)
