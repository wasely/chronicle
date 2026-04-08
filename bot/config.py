from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


CATEGORY_META = {
    "Work": {"emoji": "💼", "color": "#6366f1"},
    "Deep Work": {"emoji": "🧠", "color": "#8b5cf6"},
    "Exercise": {"emoji": "🏃", "color": "#10b981"},
    "Meals": {"emoji": "🍽️", "color": "#f59e0b"},
    "Social": {"emoji": "👥", "color": "#f472b6"},
    "Rest": {"emoji": "🛋️", "color": "#3b82f6"},
    "Learning": {"emoji": "📚", "color": "#06b6d4"},
    "Admin": {"emoji": "🗂️", "color": "#94a3b8"},
    "Personal": {"emoji": "✨", "color": "#a78bfa"},
    "Sleep": {"emoji": "🌙", "color": "#1e3a5f"},
}

EVENT_COLOR_META = {
    "1": {"label": "Lavender", "color": "#7986cb"},
    "2": {"label": "Sage", "color": "#33b679"},
    "3": {"label": "Grape", "color": "#8e24aa"},
    "4": {"label": "Flamingo", "color": "#e67c73"},
    "5": {"label": "Banana", "color": "#f6c026"},
    "6": {"label": "Tangerine", "color": "#f5511d"},
    "7": {"label": "Peacock", "color": "#039be5"},
    "8": {"label": "Graphite", "color": "#616161"},
    "9": {"label": "Blueberry", "color": "#3f51b5"},
    "10": {"label": "Basil", "color": "#0b8043"},
    "11": {"label": "Tomato", "color": "#d60000"},
}

CATEGORIES = list(CATEGORY_META.keys())
ENERGY_LEVELS = ["Low", "Medium", "High"]
SOURCES = ["Manual", "Auto-logged", "Inferred"]
CHECKIN_MESSAGES = [
    "Hey! What have you been up to for the past 15 min?",
    "Quick check-in. What's keeping you busy?",
    "15-min update time. What did you do?",
    "Brain dump time. What just happened?",
]
STREAK_MILESTONES = {3, 7, 14, 30}
COMMON_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Edmonton",
    "America/Los_Angeles",
    "Europe/London",
]
WAKE_CHOICES = ["05:30", "06:00", "06:30", "07:00", "07:30", "08:00", "08:30", "09:00"]
SLEEP_CHOICES = ["21:30", "22:00", "22:30", "23:00", "23:30", "00:00", "00:30", "01:00"]
FREQUENCY_CHOICES = [15, 30, 45, 60]


@dataclass(slots=True)
class Settings:
    telegram_bot_token: str
    notion_api_key: str
    notion_database_id: str | None
    notion_parent_page_id: str | None
    telegram_chat_id: int | None
    default_timezone: str
    sqlite_path: Path
    openrouter_api_key: str | None
    google_credentials_path: str
    google_token_path: str
    google_calendar_id: str


def load_settings() -> Settings:
    load_dotenv()
    root = Path(__file__).resolve().parent.parent
    sqlite_raw = os.getenv("SQLITE_PATH", "chronicle.db")
    sqlite_path = Path(sqlite_raw)
    if not sqlite_path.is_absolute():
        sqlite_path = root / sqlite_path

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    notion_key = os.getenv("NOTION_API_KEY", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required.")
    if not notion_key:
        raise RuntimeError("NOTION_API_KEY is required.")

    notion_db = os.getenv("NOTION_DATABASE_ID", "").strip() or None
    notion_parent = os.getenv("NOTION_PARENT_PAGE_ID", "").strip() or None
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    gcreds_raw = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json").strip()
    gcreds_path = Path(gcreds_raw) if Path(gcreds_raw).is_absolute() else root / gcreds_raw
    gtoken_raw = os.getenv("GOOGLE_TOKEN_PATH", "token.json").strip()
    gtoken_path = Path(gtoken_raw) if Path(gtoken_raw).is_absolute() else root / gtoken_raw

    return Settings(
        telegram_bot_token=token,
        notion_api_key=notion_key,
        notion_database_id=notion_db,
        notion_parent_page_id=notion_parent,
        telegram_chat_id=int(chat_id) if chat_id else None,
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC").strip() or "UTC",
        sqlite_path=sqlite_path,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip() or None,
        google_credentials_path=str(gcreds_path),
        google_token_path=str(gtoken_path),
        google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary",
    )
