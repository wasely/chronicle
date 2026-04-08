from __future__ import annotations

import asyncio
import logging

from telegram.ext import AIORateLimiter, ApplicationBuilder

from bot.ai_summarizer import AISummarizer
from bot.config import load_settings
from bot.db import Database
from bot.gcal_client import GoogleCalendarClient
from bot.handlers import BotHandlers
from bot.notion_client import NotionService
from bot.scheduler import TelegramCalendarScheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    db = Database(settings.sqlite_path)
    await db.init()
    if settings.telegram_chat_id:
        await db.ensure_user(settings.telegram_chat_id, settings.default_timezone)

    notion = NotionService(settings.notion_api_key, settings.notion_database_id)
    gcal = GoogleCalendarClient(
        settings.google_credentials_path,
        settings.google_token_path,
        settings.google_calendar_id,
    )
    ai = AISummarizer(settings.openrouter_api_key) if settings.openrouter_api_key else None
    handlers = BotHandlers(settings, db, notion, gcal, ai)
    scheduler = TelegramCalendarScheduler(handlers)

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .rate_limiter(AIORateLimiter())
        .build()
    )
    handlers.register(app)

    await app.initialize()
    await handlers.register_telegram_commands(app)
    scheduler.start(app)
    await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
