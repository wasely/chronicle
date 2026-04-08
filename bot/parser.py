from __future__ import annotations

import re
from datetime import datetime, timedelta


CATEGORY_KEYWORDS = {
    "Work": ("coding", "meeting", "email", "writing", "designing", "debugging", "client", "report", "work", "project", "task", "commit", "deploy", "review", "interview"),
    "Deep Work": ("deep work", "focused", "research", "architecture", "implementation", "refactor", "ship", "deep focus", "flow state"),
    "Exercise": ("gym", "run", "walk", "workout", "yoga", "cycling", "hiked", "soccer", "football", "basketball", "tennis", "swimming", "swim", "sport", "practice", "training", "lifting", "weights", "cardio", "crossfit", "volleyball", "hockey", "baseball", "skateboard", "skate"),
    "Meals": ("lunch", "dinner", "breakfast", "ate", "coffee", "eating", "snack", "food", "meal", "drink", "brunch"),
    "Rest": ("nap", "rested", "relaxed", "couch", "watched", "netflix", "tv", "chilling", "chill", "gaming", "youtube", "scrolling", "browse", "browsing"),
    "Sleep": ("slept", "sleeping", "bed", "woke up", "sleep", "passed out"),
    "Learning": ("reading", "course", "studied", "tutorial", "book", "lesson", "lecture", "class", "learning", "studying", "homework", "assignment"),
    "Social": ("call", "hangout", "friends", "family", "dinner with", "chat", "talked", "texting", "party", "date"),
    "Admin": ("admin", "paperwork", "inbox", "errands", "scheduling", "planning", "organized", "bills", "taxes", "appointment"),
    "Personal": ("shower", "chores", "cleaning", "shopping", "journaling", "hygiene", "laundry", "meditation"),
}

CATEGORY_PRIORITY = [
    "Sleep",
    "Meals",
    "Exercise",
    "Deep Work",
    "Work",
    "Learning",
    "Social",
    "Rest",
    "Admin",
    "Personal",
]

TAG_KEYWORDS = {
    "coding": ("coding", "debugging", "implementation", "deploy", "bugfix", "commit", "code", "programming"),
    "meeting": ("meeting", "standup", "sync", "call", "interview"),
    "health": ("gym", "run", "walk", "workout", "yoga", "sleep", "soccer", "basketball", "tennis", "swimming", "exercise", "sport", "practice"),
    "food": ("lunch", "dinner", "breakfast", "coffee", "meal", "eating"),
    "learning": ("reading", "course", "tutorial", "studied", "book", "class", "homework", "studying"),
    "social": ("friends", "family", "hangout", "call", "party", "date"),
    "planning": ("plan", "planning", "schedule", "roadmap", "organize"),
    "rest": ("chill", "chilling", "gaming", "youtube", "netflix", "relax", "nap"),
}

STOP_WORDS = {
    "today", "from", "have", "that", "this", "with", "will", "been", "were",
    "they", "them", "their", "about", "into", "than", "then", "when", "where",
    "which", "while", "your", "just", "some", "more", "also", "back", "over",
    "like", "time", "very", "still", "only", "even", "such", "much", "most",
    "going", "doing", "some", "other", "these", "those", "here", "there",
    "after", "before", "since", "until", "while", "because", "though",
}

DURATION_PATTERNS = [
    re.compile(r"\bfor\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|hr|h|minutes?|mins?|min|m)\b", re.I),
    re.compile(r"\b(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|hr|h|minutes?|mins?|min|m)\b", re.I),
    re.compile(r"\b(?:past|last)\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|hr|minutes?|mins?|min)\b", re.I),
    re.compile(r"\b(?:past hour|last hour)\b", re.I),
]

FUTURE_OFFSET_RE = re.compile(
    r"\bin\s+(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|hr|h|minutes?|mins?|min|m)\b",
    re.I,
)

# Matches "from 4 to 5 pm", "4 to 5pm", "4-5 pm", "4:30 to 5:30 pm"
TIME_RANGE_RE = re.compile(
    r'\b(?:from\s+)?'
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*'
    r'(?:to|-)\s*'
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',
    re.I,
)

# Phrases to strip when cleaning title
TIME_PHRASE_STRIP_RE = re.compile(
    r'\b(?:from\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:to|-)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b'
    r'|\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b'
    r'|\btoday\b|\btomorrow\b|\byesterday\b',
    re.I,
)

FILLER_PREFIX_RE = re.compile(
    r"^(?:i(?:'m|'ve|'ll|'d)?\s+(?:have\s+(?:a\s+)?|had\s+|was\s+|am\s+|will\s+be\s+|been\s+)?)",
    re.I,
)

LEADING_ACTION_NOISE_RE = re.compile(
    r"^(?:i\s+(?:have|need)\s+to(?:\s+go)?|i\s+gotta(?:\s+go)?|i(?:'m| am)\s+going\s+to|"
    r"have\s+to(?:\s+go)?|need\s+to(?:\s+go)?|gotta(?:\s+go)?|going\s+to|about\s+to)\s+",
    re.I,
)


def clamp_minutes(value: int, minimum: int = 5, maximum: int = 16 * 60) -> int:
    return max(minimum, min(maximum, value))


def extract_future_offset(text: str) -> timedelta | None:
    match = FUTURE_OFFSET_RE.search(text)
    if not match:
        return None
    value = float(match.group("num"))
    unit = match.group("unit").lower()
    minutes = int(value * 60) if unit.startswith("h") else int(value)
    return timedelta(minutes=clamp_minutes(minutes))


def extract_time_range(text: str, now: datetime) -> tuple[datetime, datetime] | None:
    """Extract an absolute time range from text like 'from 4 to 5 pm'."""
    m = TIME_RANGE_RE.search(text)
    if not m:
        return None
    h1_s, m1_s, ampm1, h2_s, m2_s, ampm2 = m.groups()
    if not ampm2:
        return None
    h1, h2 = int(h1_s), int(h2_s)
    min1 = int(m1_s) if m1_s else 0
    min2 = int(m2_s) if m2_s else 0
    ampm2 = ampm2.lower()
    ampm1 = ampm1.lower() if ampm1 else ampm2  # inherit from end if missing

    def to_24h(h: int, ap: str) -> int:
        if ap == "pm" and h != 12:
            return h + 12
        if ap == "am" and h == 12:
            return 0
        return h

    h1 = to_24h(h1, ampm1)
    h2 = to_24h(h2, ampm2)

    date = now.date()
    tz = now.tzinfo
    start = datetime(date.year, date.month, date.day, h1, min1, tzinfo=tz)
    end = datetime(date.year, date.month, date.day, h2, min2, tzinfo=tz)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def extract_duration_minutes(text: str, fallback_minutes: int | None = None) -> int:
    duration_text = FUTURE_OFFSET_RE.sub("", text)
    lowered = duration_text.lower()
    if "past hour" in lowered or "last hour" in lowered:
        return 60
    for pattern in DURATION_PATTERNS:
        match = pattern.search(duration_text)
        if not match:
            continue
        if "num" not in match.groupdict():
            return 60
        value = float(match.group("num"))
        unit = match.group("unit").lower()
        minutes = int(value * 60) if unit.startswith("h") else int(value)
        return clamp_minutes(minutes)
    return clamp_minutes(fallback_minutes or 30)


def infer_category(text: str) -> str:
    lowered = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score:
            scores[category] = score
    if not scores:
        return "Personal"
    priority = {name: index for index, name in enumerate(CATEGORY_PRIORITY)}
    return sorted(scores.items(), key=lambda item: (-item[1], priority.get(item[0], 999), item[0]))[0][0]


def infer_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = [tag for tag, keywords in TAG_KEYWORDS.items() if any(keyword in lowered for keyword in keywords)]
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", lowered)
    freeform = [w for w in words if w not in tags and w not in STOP_WORDS][:3]
    return list(dict.fromkeys(tags + freeform))


def clean_title(text: str) -> str:
    """Strip time expressions, filler prefixes, and extra whitespace from a title."""
    cleaned = TIME_PHRASE_STRIP_RE.sub("", text)
    cleaned = FUTURE_OFFSET_RE.sub("", cleaned)
    cleaned = FILLER_PREFIX_RE.sub("", cleaned.strip())
    cleaned = LEADING_ACTION_NOISE_RE.sub("", cleaned.strip())
    cleaned = re.sub(r"^to\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\bgo\s+eat\b", "eat", cleaned, flags=re.I)
    cleaned = re.sub(r"\bgo\s+to\s+bed\b|\bgo\s+to\s+sleep\b", "sleep", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:go|head)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned or text.strip()


def strip_duration_phrases(text: str) -> str:
    cleaned = FUTURE_OFFSET_RE.sub("", text)
    for pattern in DURATION_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\b(?:past hour|last hour)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    return cleaned or "Activity log"


def parse_activity(
    text: str,
    *,
    now: datetime,
    fallback_minutes: int | None = None,
    end_time: datetime | None = None,
    source: str = "Manual",
) -> dict:
    # Try to extract an explicit time range first ("from 4 to 5 pm")
    time_range = extract_time_range(text, now)
    if time_range:
        start_dt, end_dt = time_range
        duration = max(5, int((end_dt - start_dt).total_seconds() // 60))
    elif end_time is None and (future_offset := extract_future_offset(text)):
        duration = extract_duration_minutes(text, fallback_minutes)
        start_dt = now + future_offset
        end_dt = start_dt + timedelta(minutes=duration)
    else:
        end_dt = end_time or now
        duration = extract_duration_minutes(text, fallback_minutes)
        start_dt = end_dt - timedelta(minutes=duration)

    # Clean title: strip time phrases and filler words
    title = clean_title(strip_duration_phrases(text))
    category = infer_category(text)  # use original text for better category detection
    tags = infer_tags(title)

    return {
        "title": title[:200],
        "start": start_dt,
        "end": end_dt,
        "duration": duration,
        "category": category,
        "tags": tags,
        "energy_level": None,
        "notes": None,
        "source": source,
        "day_rating": None,
    }
