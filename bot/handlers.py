from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.config import CATEGORY_META, COMMON_TIMEZONES, FREQUENCY_CHOICES, SLEEP_CHOICES, STREAK_MILESTONES, WAKE_CHOICES
from bot.parser import extract_time_range, parse_activity


class BotHandlers:
    def __init__(self, settings, db, notion, gcal=None, ai=None) -> None:
        self.settings = settings
        self.db = db
        self.notion = notion
        self.gcal = gcal
        self.ai = ai
        self.logger = logging.getLogger(__name__)
        self._last_sent: dict[int, datetime] = {}

    def register(self, app) -> None:
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("log", self.log_now))
        app.add_handler(CommandHandler("logpast", self.log_past))
        app.add_handler(CommandHandler("sleep", self.sleep))
        app.add_handler(CommandHandler("wake", self.wake))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("summary", self.summary))
        app.add_handler(CommandHandler("edit", self.edit))
        app.add_handler(CommandHandler("skip", self.skip))
        app.add_handler(CommandHandler("pause", self.pause))
        app.add_handler(CommandHandler("resume", self.resume))
        app.add_handler(CommandHandler("setschedule", self.setschedule))
        app.add_handler(CommandHandler("timezone", self.timezone))
        app.add_handler(CommandHandler("export", self.export))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    def telegram_commands(self) -> list[BotCommand]:
        return [
            BotCommand("start", "Run onboarding"),
            BotCommand("help", "Show command reference"),
            BotCommand("log", "Log what you just did"),
            BotCommand("logpast", "Log something from earlier"),
            BotCommand("sleep", "Pause check-ins and start sleep mode"),
            BotCommand("wake", "End sleep mode and log sleep"),
            BotCommand("status", "Show today's tracked time"),
            BotCommand("summary", "Show a summary for today, week, or month"),
            BotCommand("edit", "Edit or delete recent entries"),
            BotCommand("skip", "Skip the current check-in"),
            BotCommand("pause", "Temporarily pause check-ins"),
            BotCommand("resume", "Resume check-ins"),
            BotCommand("setschedule", "Choose check-in frequency"),
            BotCommand("timezone", "Update your timezone"),
            BotCommand("export", "Export your recent logs"),
        ]

    async def register_telegram_commands(self, app) -> None:
        await app.bot.set_my_commands(self.telegram_commands())

    async def send_text(self, context_or_app, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None) -> None:
        last = self._last_sent.get(chat_id)
        now = datetime.now(UTC)
        if last and (now - last).total_seconds() < 5:
            await context_or_app.bot.send_chat_action(chat_id=chat_id, action="typing")
        self._last_sent[chat_id] = now
        await context_or_app.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.db.ensure_user(update.effective_chat.id, self.settings.default_timezone)
        user["onboarding_step"] = "timezone"
        user["onboarding_data_json"] = json.dumps({})
        await self.db.upsert_user(user)
        await self.send_text(context, user["chat_id"], "Step 1 of 5. What timezone are you in?", self._timezone_keyboard())

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_text(context, update.effective_chat.id, self.help_text())

    async def log_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = " ".join(context.args).strip()
        if not text:
            await self.send_text(context, update.effective_chat.id, "Use /log followed by what you did.")
            return
        await self.preview_activity(update.effective_chat.id, context, text, source="Manual")

    async def log_past(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        raw = update.message.text.removeprefix("/logpast").strip()
        match = re.match(r"^(?P<offset>(?:~?\d+(?:\.\d+)?\s*(?:h|hr|hrs|hour|hours|m|min|mins|minute|minutes))(?:\s*ago)?)\s+(?P<body>.+)$", raw, re.I)
        if not match:
            await self.send_text(context, update.effective_chat.id, "Example: /logpast 2h ago I was in a meeting")
            return
        offset = self.parse_offset(match.group("offset"))
        if not offset:
            await self.send_text(context, update.effective_chat.id, "I couldn't parse that offset.")
            return
        await self.preview_activity(update.effective_chat.id, context, match.group("body"), source="Manual", end_time=datetime.now(UTC) - offset)

    async def sleep(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        user["is_sleeping"] = 1
        user["sleep_started_utc"] = datetime.now(UTC).isoformat()
        await self.db.upsert_user(user)
        await self.send_text(context, user["chat_id"], "Sleep mode on. I'll suppress check-ins until you wake.")

    async def wake(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        if not user.get("is_sleeping") or not user.get("sleep_started_utc"):
            await self.send_text(context, user["chat_id"], "You're not marked as sleeping right now.")
            return
        await self._finalize_sleep(context, user, datetime.now(UTC))

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        start, end = self.period_bounds("today", user["timezone"])
        entries = await self.db.activities_between(user["chat_id"], start, end)
        total = sum(int(item["duration_minutes"]) for item in entries if not item["day_rating"])
        top = self.top_category(entries)
        gap = 0
        if user.get("last_logged_end_utc"):
            gap = int((datetime.now(UTC) - datetime.fromisoformat(user["last_logged_end_utc"])).total_seconds() // 60)
        message = f"Today's tracked time: {self.human_duration(total)}\nCurrent streak: {user['streak_count']} day(s)\nTop category: {top or 'None'}"
        if gap > 90:
            message += f"\nUnlogged gap: about {self.human_duration(gap)}"
        await self.send_text(context, user["chat_id"], message)

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        period = (context.args[0] if context.args else "today").lower()
        start, end = self.period_bounds(period, user["timezone"])
        entries = await self.db.activities_between(user["chat_id"], start, end)
        await self.send_text(context, user["chat_id"], self.summary_text(entries, period))

    async def edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        entries = await self.db.recent_activities(user["chat_id"], 5)
        if not entries:
            await self.send_text(context, user["chat_id"], "No recent entries to edit.")
            return
        rows = []
        for entry in entries:
            rows.append([InlineKeyboardButton(f"Edit {entry['title'][:20]}", callback_data=f"edit:{entry['id']}")])
            rows.append([InlineKeyboardButton(f"Delete {entry['title'][:20]}", callback_data=f"delete:{entry['id']}")])
        await self.send_text(context, user["chat_id"], "Choose an entry to edit or delete.", InlineKeyboardMarkup(rows))

    async def skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        user["last_checkin_utc"] = datetime.now(UTC).isoformat()
        await self.db.upsert_user(user)
        await self.send_text(context, user["chat_id"], "Skipped.")

    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        token = (context.args[0] if context.args else "1h").lower()
        offset = self.parse_offset(token)
        if not offset:
            await self.send_text(context, user["chat_id"], "Use /pause 3h or /pause 45m")
            return
        user["paused_until_utc"] = (datetime.now(UTC) + offset).isoformat()
        await self.db.upsert_user(user)
        await self.send_text(context, user["chat_id"], "Check-ins paused.")

    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        user["paused_until_utc"] = None
        await self.db.upsert_user(user)
        await self.send_text(context, user["chat_id"], "Check-ins resumed.")

    async def setschedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        rows = [[InlineKeyboardButton(f"{minutes} min", callback_data=f"schedule:{minutes}")] for minutes in FREQUENCY_CHOICES]
        await self.send_text(context, update.effective_chat.id, "Choose a check-in frequency.", InlineKeyboardMarkup(rows))

    async def timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        if context.args:
            zone = context.args[0]
            if not self.valid_timezone(zone):
                await self.send_text(context, user["chat_id"], "Invalid timezone. Example: America/Edmonton")
                return
            user["timezone"] = zone
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], f"Timezone updated to {zone}.")
            return
        await self.send_text(context, user["chat_id"], "Pick a timezone.", self._timezone_keyboard())

    async def export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        period = (context.args[0] if context.args else "week").lower()
        start, end = self.period_bounds(period, user["timezone"])
        entries = await self.db.activities_between(user["chat_id"], start, end)
        lines = [f"{period.title()} export", ""]
        for item in entries:
            lines.append(f"- {item['title']} [{item['category']}] {item['duration_minutes']}m")
        await self.send_text(context, user["chat_id"], "\n".join(lines[:60]) or "No entries.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.require_user(update.effective_chat.id)
        text = (update.message.text or "").strip()

        if user.get("onboarding_step") == "timezone_text":
            if not self.valid_timezone(text):
                await self.send_text(context, user["chat_id"], "Invalid timezone. Example: America/Edmonton")
                return
            await self._save_onboarding_step(context, user, "timezone", text)
            return
        if user.get("pending_prompt") == "awaiting_eod_rating":
            if not text.isdigit() or not 1 <= int(text) <= 10:
                await self.send_text(context, user["chat_id"], "Send a rating from 1 to 10.")
                return
            user["pending_prompt"] = "awaiting_eod_notes"
            user["pending_prompt_payload"] = json.dumps({"day_rating": int(text)})
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Any final notes?")
            return
        if user.get("pending_prompt") == "awaiting_eod_notes":
            payload = json.loads(user.get("pending_prompt_payload") or "{}")
            payload["notes"] = text
            user["pending_prompt"] = "awaiting_eod_wake"
            user["pending_prompt_payload"] = json.dumps(payload)
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Planned wake time tomorrow? Use HH:MM")
            return
        if user.get("pending_prompt") == "awaiting_eod_wake":
            await self._save_eod_review(context, user, text)
            return
        if user.get("pending_prompt") == "awaiting_preview_rewrite":
            user["pending_prompt"] = None
            user["pending_prompt_payload"] = None
            await self.db.upsert_user(user)
            await self.preview_activity(user["chat_id"], context, text, source="Manual")
            return
        if user.get("pending_prompt") == "awaiting_edit_replacement":
            await self._replace_entry(context, user, text)
            return
        if user.get("pending_prompt") == "awaiting_gap_fill":
            user["pending_prompt"] = None
            await self.db.upsert_user(user)
            await self.preview_activity(user["chat_id"], context, text, source="Inferred")
            return

        if self.ai:
            result = await self.ai.classify_message(text)
            if result:
                if result.get("intent") == "chat":
                    await self.send_text(context, user["chat_id"], result.get("reply", "Hey!"))
                    return
                normalized = result.get("normalized") or text
                # Extract time range from original text so it isn't lost after AI normalization
                time_range = extract_time_range(text, datetime.now(UTC))
                if time_range:
                    start_dt, end_dt = time_range
                    await self.preview_activity(user["chat_id"], context, normalized, source="Manual", start_time=start_dt, end_time=end_dt)
                else:
                    await self.preview_activity(user["chat_id"], context, normalized, source="Manual")
                return

        await self.preview_activity(user["chat_id"], context, text, source="Manual")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        user = await self.require_user(query.message.chat_id)
        data = query.data or ""

        if data.startswith("onboard:timezone:"):
            zone = data.split(":", 2)[2]
            if zone == "other":
                user["onboarding_step"] = "timezone_text"
                await self.db.upsert_user(user)
                await self.send_text(context, user["chat_id"], "Send your timezone in IANA format. Example: America/Edmonton")
                return
            await self._save_onboarding_step(context, user, "timezone", zone)
            return
        if data.startswith("onboard:wake:"):
            await self._save_onboarding_step(context, user, "wake_time", data.split(":", 2)[2])
            return
        if data.startswith("onboard:sleep:"):
            await self._save_onboarding_step(context, user, "sleep_time", data.split(":", 2)[2])
            return
        if data.startswith("onboard:freq:"):
            await self._save_onboarding_step(context, user, "frequency", int(data.split(":", 2)[2]))
            return
        if data == "preview:confirm":
            preview = await self.db.get_pending_preview(user["chat_id"])
            if not preview:
                await self.send_text(context, user["chat_id"], "Preview expired. Send the activity again.")
                return
            await self.db.clear_pending_preview(user["chat_id"])
            await self.persist_and_ack(context, user, preview)
            return
        if data == "preview:edit":
            user["pending_prompt"] = "awaiting_preview_rewrite"
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Send the corrected activity text.")
            return
        if data == "preview:cancel":
            await self.db.clear_pending_preview(user["chat_id"])
            await self.send_text(context, user["chat_id"], "Cancelled.")
            return
        if data == "preview:category":
            await query.message.edit_text("Pick a category:", reply_markup=self._category_keyboard())
            return
        if data == "preview:energy":
            await query.message.edit_text("Pick an energy level:", reply_markup=self._energy_keyboard())
            return
        if data == "preview:back":
            preview = await self.db.get_pending_preview(user["chat_id"])
            if not preview:
                await self.send_text(context, user["chat_id"], "Preview expired. Send the activity again.")
                return
            await query.message.edit_text(self._preview_text(preview, user["timezone"]), reply_markup=self._preview_keyboard(), parse_mode="HTML")
            return
        if data.startswith("preview:set_cat:"):
            cat = data.split(":", 2)[2]
            if cat not in CATEGORY_META:
                return
            preview = await self.db.get_pending_preview(user["chat_id"])
            if not preview:
                await self.send_text(context, user["chat_id"], "Preview expired. Send the activity again.")
                return
            preview["category"] = cat
            await self.db.save_pending_preview(user["chat_id"], preview)
            await query.message.edit_text(self._preview_text(preview, user["timezone"]), reply_markup=self._preview_keyboard(), parse_mode="HTML")
            return
        if data.startswith("preview:set_energy:"):
            level = data.split(":", 2)[2]
            preview = await self.db.get_pending_preview(user["chat_id"])
            if not preview:
                await self.send_text(context, user["chat_id"], "Preview expired. Send the activity again.")
                return
            preview["energy_level"] = level
            await self.db.save_pending_preview(user["chat_id"], preview)
            await query.message.edit_text(self._preview_text(preview, user["timezone"]), reply_markup=self._preview_keyboard(), parse_mode="HTML")
            return
        if data.startswith("preview:dur:"):
            delta = int(data.split(":", 2)[2])
            preview = await self.db.get_pending_preview(user["chat_id"])
            if not preview:
                await self.send_text(context, user["chat_id"], "Preview expired. Send the activity again.")
                return
            new_end = preview["end"] + timedelta(minutes=delta)
            if new_end <= preview["start"]:
                await query.answer("Duration can't go below zero.")
                return
            preview["end"] = new_end
            preview["duration"] = max(1, int((new_end - preview["start"]).total_seconds() // 60))
            await self.db.save_pending_preview(user["chat_id"], preview)
            await query.message.edit_text(self._preview_text(preview, user["timezone"]), reply_markup=self._preview_keyboard(), parse_mode="HTML")
            return
        if data == "checkin:log":
            user["pending_prompt"] = "awaiting_preview_rewrite"
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Reply with what you were doing.")
            return
        if data == "checkin:skip":
            user["last_checkin_utc"] = datetime.now(UTC).isoformat()
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Skipped.")
            return
        if data == "checkin:sleep":
            user["is_sleeping"] = 1
            user["sleep_started_utc"] = datetime.now(UTC).isoformat()
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Sleep mode on.")
            return
        if data.startswith("schedule:"):
            user["checkin_frequency_minutes"] = int(data.split(":", 1)[1])
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], f"Check-ins will run every {user['checkin_frequency_minutes']} minutes.")
            return
        if data.startswith("edit:"):
            user["pending_prompt"] = "awaiting_edit_replacement"
            user["pending_prompt_payload"] = json.dumps({"activity_id": int(data.split(":", 1)[1])})
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Send the replacement activity description.")
            return
        if data.startswith("delete:"):
            await self.delete_entry(user["chat_id"], int(data.split(":", 1)[1]))
            await self.send_text(context, user["chat_id"], "Entry deleted.")
            return
        if data == "gap:fill":
            user["pending_prompt"] = "awaiting_gap_fill"
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Reply with what happened during the gap.")
            return
        if data == "gap:leave":
            await self.send_text(context, user["chat_id"], "Leaving the gap blank.")
            return
        if data == "gap:sleep":
            user["is_sleeping"] = 1
            user["sleep_started_utc"] = user.get("last_logged_end_utc") or datetime.now(UTC).isoformat()
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Marked as sleep time.")

    async def preview_activity(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str, *, source: str, end_time: datetime | None = None, start_time: datetime | None = None) -> None:
        user = await self.require_user(chat_id)
        fallback = 15
        if user.get("last_checkin_utc"):
            fallback = max(5, int((datetime.now(UTC) - datetime.fromisoformat(user["last_checkin_utc"])).total_seconds() // 60))
        preview = parse_activity(text, now=datetime.now(UTC), fallback_minutes=fallback, end_time=end_time, source=source)
        if start_time and end_time:
            preview["start"] = start_time
            preview["end"] = end_time
            preview["duration"] = max(5, int((end_time - start_time).total_seconds() // 60))

        if self.ai:
            enhanced = await self.ai.enhance_entry(text, preview)
            if enhanced:
                preview["title"] = enhanced["title"]
                preview["notes"] = enhanced["description"]

        await self.db.save_pending_preview(chat_id, preview)
        await self.send_text(context, chat_id, self._preview_text(preview, user["timezone"]), self._preview_keyboard(), parse_mode="HTML")

    def _preview_text(self, preview: dict, timezone: str) -> str:
        emoji = CATEGORY_META[preview["category"]]["emoji"]
        energy = preview.get("energy_level") or "—"
        tags = ", ".join(preview["tags"]) if preview.get("tags") else "none"
        start_str = self.local_time(preview["start"], timezone)
        end_str = self.local_time(preview["end"], timezone)
        return (
            "<b>Ready to log:</b>\n\n"
            f"📋 <b>{preview['title']}</b>\n"
            f"⏰ {start_str} → {end_str}\n"
            f"⏱ {preview['duration']} min\n"
            f"📁 {preview['category']} {emoji}\n"
            f"⚡ {energy}\n"
            f"🏷 {tags}\n\n"
            "Tap <b>Log it</b> to confirm, or adjust below."
        )

    def _preview_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Log it", callback_data="preview:confirm"),
                InlineKeyboardButton("✏️ Rewrite", callback_data="preview:edit"),
                InlineKeyboardButton("❌ Cancel", callback_data="preview:cancel"),
            ],
            [
                InlineKeyboardButton("📁 Category", callback_data="preview:category"),
                InlineKeyboardButton("⚡ Energy", callback_data="preview:energy"),
            ],
            [
                InlineKeyboardButton("−15m", callback_data="preview:dur:-15"),
                InlineKeyboardButton("−5m", callback_data="preview:dur:-5"),
                InlineKeyboardButton("+5m", callback_data="preview:dur:+5"),
                InlineKeyboardButton("+15m", callback_data="preview:dur:+15"),
            ],
        ])

    def _category_keyboard(self) -> InlineKeyboardMarkup:
        rows = []
        cats = list(CATEGORY_META.keys())
        for i in range(0, len(cats), 2):
            row = [
                InlineKeyboardButton(f"{CATEGORY_META[cat]['emoji']} {cat}", callback_data=f"preview:set_cat:{cat}")
                for cat in cats[i:i + 2]
            ]
            rows.append(row)
        rows.append([InlineKeyboardButton("← Back", callback_data="preview:back")])
        return InlineKeyboardMarkup(rows)

    def _energy_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔋 Low", callback_data="preview:set_energy:Low"),
                InlineKeyboardButton("⚡ Medium", callback_data="preview:set_energy:Medium"),
                InlineKeyboardButton("🔥 High", callback_data="preview:set_energy:High"),
            ],
            [InlineKeyboardButton("← Back", callback_data="preview:back")],
        ])

    async def persist_and_ack(self, context: ContextTypes.DEFAULT_TYPE, user: dict, entry: dict) -> None:
        previous_streak = user["streak_count"]
        message = await self.persist_entry(user["chat_id"], entry)
        refreshed = await self.require_user(user["chat_id"])
        if refreshed["streak_count"] in STREAK_MILESTONES and refreshed["streak_count"] != previous_streak:
            message += f"\nStreak milestone: {refreshed['streak_count']} days."
        await self.send_text(context, user["chat_id"], message)

    async def persist_entry(self, chat_id: int, entry: dict) -> str:
        synced_notion = False
        synced_gcal = False
        errors: list[str] = []

        if self.notion.is_configured():
            try:
                entry["notion_page_id"] = await self.notion.create_entry(entry)
                synced_notion = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Notion: {exc}")
                self.logger.exception("Notion create failed")
        else:
            errors.append("NOTION_DATABASE_ID is not configured.")

        if self.gcal and self.gcal.is_configured() and self.gcal.is_authenticated():
            try:
                entry["gcal_event_id"] = await self.gcal.create_event(entry)
                synced_gcal = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Google Calendar: {exc}")
                self.logger.exception("Google Calendar create failed")

        synced = synced_notion or synced_gcal
        activity_id = await self.db.add_activity(chat_id, entry, synced)
        if not synced_notion and self.notion.is_configured():
            payload = self.serialize_entry(entry)
            payload["activity_id"] = activity_id
            await self.db.queue_action(chat_id, "create_entry", payload, errors[0] if errors else None)

        user = await self.require_user(chat_id)
        user["last_logged_end_utc"] = entry["end"].isoformat()
        user["last_activity_title"] = entry["title"]
        user["last_checkin_utc"] = datetime.now(UTC).isoformat()
        user["pending_prompt"] = None
        user["pending_prompt_payload"] = None
        user["streak_count"] = await self.compute_streak(chat_id, user["timezone"])
        await self.db.upsert_user(user)

        if synced_gcal and synced_notion:
            return "Logged to Google Calendar and Notion."
        if synced_gcal:
            return "Logged to Google Calendar."
        if synced_notion:
            return "Logged to Notion."
        return "Saved locally. (Check GOOGLE_CREDENTIALS_PATH / NOTION_DATABASE_ID to enable sync.)"

    async def sync_queue(self) -> None:
        if not self.notion.is_configured():
            return
        for item in await self.db.queue_items():
            payload = json.loads(item["payload_json"])
            try:
                if item["action"] == "create_entry":
                    entry = self.deserialize_entry(payload)
                    page_id = await self.notion.create_entry(entry)
                    if payload.get("activity_id"):
                        await self.db.mark_activity_synced(int(payload["activity_id"]), page_id)
                elif item["action"] == "update_entry":
                    entry = self.deserialize_entry(payload)
                    await self.notion.update_entry(payload["page_id"], entry)
                    if payload.get("activity_id"):
                        await self.db.mark_activity_synced(int(payload["activity_id"]), payload["page_id"])
                elif item["action"] == "archive_entry":
                    await self.notion.archive_entry(payload["page_id"])
                await self.db.queue_done(int(item["id"]))
            except Exception as exc:  # noqa: BLE001
                await self.db.queue_retry(int(item["id"]), str(exc))
                break

    async def send_morning_message(self, app, user: dict) -> None:
        start, end = self.period_bounds("today", user["timezone"])
        yesterday = start - timedelta(days=1)
        yesterday_entries = await self.db.activities_between(user["chat_id"], yesterday, start)
        today_entries = await self.db.activities_between(user["chat_id"], start, end)
        total = sum(int(item["duration_minutes"]) for item in yesterday_entries if not item["day_rating"])
        top = self.top_category(yesterday_entries)
        top_emoji = f" {CATEGORY_META[top]['emoji']}" if top and top in CATEGORY_META else ""
        message = (
            "<b>Good morning!</b> ☀️\n\n"
            f"📊 Yesterday: <b>{self.human_duration(total)}</b> logged\n"
            f"🏆 Top: {top or 'None'}{top_emoji}\n"
            f"📅 Today so far: <b>{len(today_entries)}</b> entries\n\n"
            "<i>Small honest logs beat perfect memory.</i>"
        )
        await self.send_text(app, user["chat_id"], message, parse_mode="HTML")

    async def delete_entry(self, chat_id: int, activity_id: int) -> None:
        entry = await self.db.get_activity(activity_id)
        if not entry:
            return
        if entry.get("notion_page_id"):
            try:
                await self.notion.archive_entry(entry["notion_page_id"])
            except Exception as exc:  # noqa: BLE001
                await self.db.queue_action(chat_id, "archive_entry", {"page_id": entry["notion_page_id"]}, str(exc))
        await self.db.archive_activity(activity_id)

    async def _replace_entry(self, context: ContextTypes.DEFAULT_TYPE, user: dict, text: str) -> None:
        payload = json.loads(user.get("pending_prompt_payload") or "{}")
        activity_id = int(payload["activity_id"])
        existing = await self.db.get_activity(activity_id)
        if not existing:
            user["pending_prompt"] = None
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "That entry no longer exists.")
            return
        entry = parse_activity(
            text,
            now=datetime.now(UTC),
            end_time=datetime.fromisoformat(existing["end_utc"]),
            fallback_minutes=int(existing["duration_minutes"]),
            source=existing["source"],
        )
        entry["notion_page_id"] = existing["notion_page_id"]
        synced = False
        try:
            if entry.get("notion_page_id"):
                await self.notion.update_entry(entry["notion_page_id"], entry)
                synced = True
            else:
                entry["notion_page_id"] = await self.notion.create_entry(entry)
                synced = True
        except Exception as exc:  # noqa: BLE001
            payload = self.serialize_entry(entry)
            payload["activity_id"] = activity_id
            if entry.get("notion_page_id"):
                payload["page_id"] = entry["notion_page_id"]
                await self.db.queue_action(user["chat_id"], "update_entry", payload, str(exc))
            else:
                await self.db.queue_action(user["chat_id"], "create_entry", payload, str(exc))
        await self.db.update_activity(activity_id, entry, synced)
        user["pending_prompt"] = None
        user["pending_prompt_payload"] = None
        await self.db.upsert_user(user)
        await self.send_text(context, user["chat_id"], "Entry updated.")

    async def _save_eod_review(self, context: ContextTypes.DEFAULT_TYPE, user: dict, wake_time: str) -> None:
        payload = json.loads(user.get("pending_prompt_payload") or "{}")
        entry = {
            "title": "End of day review",
            "start": datetime.now(UTC),
            "end": datetime.now(UTC),
            "duration": 0,
            "category": "Admin",
            "tags": ["review"],
            "energy_level": None,
            "notes": f"{payload.get('notes', '')}\nPlanned wake: {wake_time}".strip(),
            "source": "Manual",
            "day_rating": int(payload["day_rating"]),
        }
        if re.match(r"^\d{1,2}:\d{2}$", wake_time):
            user["wake_time"] = wake_time
        user["pending_prompt"] = None
        user["pending_prompt_payload"] = None
        await self.db.upsert_user(user)
        await self.persist_and_ack(context, user, entry)

    async def _finalize_sleep(self, context: ContextTypes.DEFAULT_TYPE, user: dict, wake_time: datetime) -> None:
        start = datetime.fromisoformat(user["sleep_started_utc"])
        entry = {
            "title": "Sleep",
            "start": start,
            "end": wake_time,
            "duration": max(5, int((wake_time - start).total_seconds() // 60)),
            "category": "Sleep",
            "tags": ["sleep"],
            "energy_level": None,
            "notes": None,
            "source": "Auto-logged",
            "day_rating": None,
        }
        user["is_sleeping"] = 0
        user["sleep_started_utc"] = None
        await self.db.upsert_user(user)
        await self.persist_and_ack(context, user, entry)

    async def _save_onboarding_step(self, context: ContextTypes.DEFAULT_TYPE, user: dict, key: str, value) -> None:
        payload = json.loads(user.get("onboarding_data_json") or "{}")
        payload[key] = value
        if key == "timezone":
            user["timezone"] = value
            user["onboarding_step"] = "wake_time"
            user["onboarding_data_json"] = json.dumps(payload)
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Step 2 of 5. What time do you usually wake up?", self._time_keyboard("wake", WAKE_CHOICES))
            return
        if key == "wake_time":
            user["wake_time"] = value
            user["onboarding_step"] = "sleep_time"
            user["onboarding_data_json"] = json.dumps(payload)
            await self.db.upsert_user(user)
            await self.send_text(context, user["chat_id"], "Step 3 of 5. What time do you go to sleep?", self._time_keyboard("sleep", SLEEP_CHOICES))
            return
        if key == "sleep_time":
            user["sleep_time"] = value
            user["onboarding_step"] = "frequency"
            user["onboarding_data_json"] = json.dumps(payload)
            await self.db.upsert_user(user)
            rows = [[InlineKeyboardButton(f"{minutes} min", callback_data=f"onboard:freq:{minutes}")] for minutes in FREQUENCY_CHOICES]
            await self.send_text(context, user["chat_id"], "Step 4 of 5. How often should I check in?", InlineKeyboardMarkup(rows))
            return
        if key == "frequency":
            user["checkin_frequency_minutes"] = int(value)
            user["onboarding_step"] = None
            user["onboarding_data_json"] = json.dumps(payload)
            await self.db.upsert_user(user)
            first_checkin = self.next_checkin_text(user["timezone"], user["wake_time"], user["checkin_frequency_minutes"])
            summary = (
                "Step 5 of 5. All set.\n"
                f"Timezone: {user['timezone']}\n"
                f"Wake time: {user['wake_time']}\n"
                f"Sleep time: {user['sleep_time']}\n"
                f"Check-in frequency: {user['checkin_frequency_minutes']} min\n\n"
                f"Your first check-in is at {first_checkin}."
            )
            await self.send_text(context, user["chat_id"], summary)

    def next_checkin_text(self, timezone: str, wake_time: str, frequency: int) -> str:
        now_local = datetime.now(UTC).astimezone(ZoneInfo(timezone))
        wake_hour = int(wake_time.split(":")[0])
        if now_local.hour < wake_hour:
            return wake_time
        return (now_local + timedelta(minutes=frequency)).strftime("%I:%M %p")

    async def require_user(self, chat_id: int) -> dict:
        return await self.db.ensure_user(chat_id, self.settings.default_timezone)

    def serialize_entry(self, entry: dict) -> dict:
        payload = dict(entry)
        payload["start"] = entry["start"].isoformat()
        payload["end"] = entry["end"].isoformat()
        return payload

    def deserialize_entry(self, payload: dict) -> dict:
        entry = dict(payload)
        entry["start"] = datetime.fromisoformat(payload["start"])
        entry["end"] = datetime.fromisoformat(payload["end"])
        return entry

    async def compute_streak(self, chat_id: int, timezone: str) -> int:
        streak = 0
        now = datetime.now(UTC)
        for days_back in range(365):
            local = (now - timedelta(days=days_back)).astimezone(ZoneInfo(timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
            start = local.astimezone(UTC)
            end = (local + timedelta(days=1)).astimezone(UTC)
            entries = await self.db.activities_between(chat_id, start, end)
            total = sum(int(item["duration_minutes"]) for item in entries if not item["day_rating"])
            if total >= 240:
                streak += 1
            else:
                break
        return streak

    def period_bounds(self, period: str, timezone: str) -> tuple[datetime, datetime]:
        local_now = datetime.now(UTC).astimezone(ZoneInfo(timezone))
        start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "week":
            start -= timedelta(days=6)
        elif period == "month":
            start -= timedelta(days=29)
        return start.astimezone(UTC), (local_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(UTC)

    def summary_text(self, entries: list[dict], period: str) -> str:
        total = sum(int(item["duration_minutes"]) for item in entries if not item["day_rating"])
        categories: dict[str, int] = {}
        for item in entries:
            if item["day_rating"]:
                continue
            categories[item["category"]] = categories.get(item["category"], 0) + int(item["duration_minutes"])
        lines = [f"{period.title()} summary", f"Total tracked: {self.human_duration(total)}"]
        for category, minutes in sorted(categories.items(), key=lambda it: it[1], reverse=True):
            lines.append(f"- {category}: {self.human_duration(minutes)}")
        return "\n".join(lines)

    def top_category(self, entries: list[dict]) -> str | None:
        counts: dict[str, int] = {}
        for item in entries:
            if item["day_rating"]:
                continue
            counts[item["category"]] = counts.get(item["category"], 0) + int(item["duration_minutes"])
        if not counts:
            return None
        return sorted(counts.items(), key=lambda it: it[1], reverse=True)[0][0]

    def local_time(self, dt: datetime, timezone: str) -> str:
        return dt.astimezone(ZoneInfo(timezone)).strftime("%I:%M %p")

    def human_duration(self, minutes: int) -> str:
        hours, mins = divmod(max(0, int(minutes)), 60)
        if hours and mins:
            return f"{hours}h {mins}m"
        if hours:
            return f"{hours}h"
        return f"{mins}m"

    def parse_offset(self, token: str) -> timedelta | None:
        cleaned = token.strip().lower()
        if cleaned.endswith("ago"):
            cleaned = cleaned[:-3].strip()
        if cleaned in {"past hour", "last hour", "hour"}:
            return timedelta(hours=1)
        units = {"h": 60, "hr": 60, "hrs": 60, "hour": 60, "hours": 60, "m": 1, "min": 1, "mins": 1, "minute": 1, "minutes": 1}
        parts = cleaned.split()
        if len(parts) == 2 and parts[0].replace(".", "", 1).isdigit() and parts[1] in units:
            return timedelta(minutes=int(float(parts[0]) * units[parts[1]]))
        for suffix, factor in units.items():
            if cleaned.endswith(suffix):
                num = cleaned[:-len(suffix)].strip().replace("~", "")
                if num.replace(".", "", 1).isdigit():
                    return timedelta(minutes=int(float(num) * factor))
        return None

    def valid_timezone(self, zone: str) -> bool:
        try:
            ZoneInfo(zone)
            return True
        except ZoneInfoNotFoundError:
            return False

    def _timezone_keyboard(self) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(zone, callback_data=f"onboard:timezone:{zone}")] for zone in COMMON_TIMEZONES]
        rows.append([InlineKeyboardButton("Other", callback_data="onboard:timezone:other")])
        return InlineKeyboardMarkup(rows)

    def _time_keyboard(self, prefix: str, choices: list[str]) -> InlineKeyboardMarkup:
        rows = []
        for index in range(0, len(choices), 2):
            rows.append([InlineKeyboardButton(choice, callback_data=f"onboard:{prefix}:{choice}") for choice in choices[index:index + 2]])
        return InlineKeyboardMarkup(rows)

    def help_text(self) -> str:
        return (
            "/start - onboarding flow\n"
            "/log coding for 2h\n"
            "/logpast 45m ago lunch with team\n"
            "/sleep - start sleep mode\n"
            "/wake - end sleep mode\n"
            "/status - today's progress\n"
            "/summary week - category breakdown\n"
            "/edit - edit or delete recent entries\n"
            "/skip - skip the current check-in\n"
            "/pause 3h - pause prompts\n"
            "/resume - resume prompts\n"
            "/setschedule - choose 15/30/45/60 min\n"
            "/timezone America/Edmonton - update timezone\n"
            "/export month - compact report\n"
            "/help - command reference"
        )
