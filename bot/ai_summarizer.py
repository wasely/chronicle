from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a personal activity logger assistant. Your job is to take a brief, casual description \
of what someone just did and turn it into a clean, polished Google Calendar entry.

Rules:
- Title: concise (max 6 words), starts with a relevant emoji, professional tone
- Description: 2-3 natural sentences summarizing the activity. Weave in any extra context \
provided. Mention duration naturally. Sound human, not robotic.
- Return ONLY a JSON object with keys "title" and "description". No markdown, no preamble."""

CLASSIFY_SYSTEM_PROMPT = """\
You are the brain of a Telegram activity-logging bot called Chronicle. \
Your job is to decide whether the user's message is:
  (a) an ACTIVITY they want logged (something they did or are doing)
  (b) CHAT - casual conversation, greetings, emotions, questions, or anything unrelated to logging

If it's an ACTIVITY, also normalize the raw description into a clean, third-person activity \
phrase (e.g. "working on you" -> "Working on Chronicle", "eating" -> "Eating a meal"). \
Fix pronouns and slang. Keep it short (3-6 words). Do NOT add an emoji.

Return ONLY a JSON object - no markdown, no preamble:
- For activity: {"intent": "log", "normalized": "<clean activity phrase>"}
- For chat:     {"intent": "chat", "reply": "<short friendly reply, 1-2 sentences max>"}"""


class AISummarizer:
    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def is_configured(self) -> bool:
        return bool(self._client.api_key)

    async def enhance_entry(
        self,
        raw_text: str,
        parsed: dict[str, Any],
        extra_context: str = "",
    ) -> dict[str, str] | None:
        """Returns {"title": ..., "description": ...} or None on failure."""
        context_line = f"Extra context: {extra_context}\n" if extra_context else ""
        user_msg = (
            f'Activity (raw): "{raw_text}"\n'
            f"Category: {parsed['category']}\n"
            f"Duration: {parsed['duration']} minutes\n"
            f"{context_line}"
            "Produce a polished title and description for this Google Calendar entry."
        )
        try:
            response = await self._client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct:free",
                max_tokens=256,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            text = response.choices[0].message.content.strip()
            # Strip markdown code fences if model adds them
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return {
                "title": str(data.get("title", parsed["title"]))[:200],
                "description": str(data.get("description", ""))[:2000],
            }
        except Exception:
            logger.exception("AI enhancement failed, falling back to parsed entry")
            return None

    async def classify_message(self, text: str) -> dict[str, str] | None:
        """Returns {"intent": "log", "normalized": "..."} or {"intent": "chat", "reply": "..."} or None on failure."""
        try:
            response = await self._client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct:free",
                max_tokens=128,
                messages=[
                    {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception:
            logger.exception("classify_message failed")
            return None
