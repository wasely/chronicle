# CHRONICLE

```text
  ________  __  __  ____   ____  _   ________  ____   ______
 / ____/ / / / / / / __ \ / __ \/ | / /  _/ / / / /  / ____/
/ /   / /_/ / / / / /_/ // / / /  |/ // // /_/ / /  / __/
/ /___/ __  / / / / _, _// /_/ / /|  // // __  / /__/ /___
\____/_/ /_/ /_/ /_/ |_| \____/_/ |_/___/_/ /_/____/_____/
```

Chronicle is a personal productivity tracker built around a Telegram bot and a premium read-only calendar dashboard. The bot prompts you throughout the day, parses natural-language activity notes, logs them to Notion, keeps local SQLite state for resilience, tracks sleep and streaks, and queues unsynced entries when Notion is unavailable. The dashboard gives you a dark-mode week, day, and month view directly from the same Notion database.

## What It Includes

- Async Telegram bot using `python-telegram-bot` v20+
- APScheduler-based smart check-ins and daily review prompts
- Regex and keyword-based activity parsing with no external NLP APIs
- Notion integration through the official `notion-client`
- SQLite caching and offline sync queue via `aiosqlite`
- Single-file dashboard in `dashboard/index.html`
- Dockerfile and `docker-compose.yml`
- Parser test coverage in `tests/test_parser.py`

## Project Layout

```text
chronicle-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py
│   ├── handlers.py
│   ├── scheduler.py
│   ├── notion_client.py
│   ├── parser.py
│   ├── db.py
│   └── config.py
├── dashboard/
│   └── index.html
├── tests/
│   └── test_parser.py
├── setup_notion.py
├── requirements.txt
├── .env.example
├── NOTION_PAGE_TEMPLATE.md
├── README.md
├── Dockerfile
└── docker-compose.yml
```

## Prerequisites

- Python 3.11+
- A Telegram bot token from BotFather
- A Notion integration token
- A Notion parent page where the database can be created

### Telegram Setup Via BotFather

1. Open Telegram and start a chat with `@BotFather`.
2. Run `/newbot`.
3. Choose the bot name and username.
4. Copy the bot token and place it in `.env` as `TELEGRAM_BOT_TOKEN`.
5. Send a message to your new bot once so the bot can reach your chat.
6. Optional: set `TELEGRAM_CHAT_ID` in `.env` if you want to pre-register one chat on startup.

### Notion Integration Setup

1. In Notion, create a new internal integration from the integrations page.
2. Copy the secret and place it in `.env` as `NOTION_API_KEY`.
3. Create a blank page in Notion to act as the parent page for the Chronicle database.
4. Share that page with your integration.
5. Copy the parent page ID and place it in `.env` as `NOTION_PARENT_PAGE_ID`.
6. Run `python setup_notion.py`.
7. Copy the returned database ID into `.env` as `NOTION_DATABASE_ID`.
8. Share the new database with the integration if needed.

Suggested screenshots to capture for your own setup notes:

- BotFather token creation screen
- Notion integration secret page
- Notion page share dialog showing the integration added
- The newly created Chronicle database page

## Step-By-Step Setup

1. Create a virtual environment.

```bash
python -m venv .venv
```

2. Activate it.

```bash
.venv\Scripts\activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Copy the environment template.

```bash
copy .env.example .env
```

5. Fill in these values in `.env`:

- `TELEGRAM_BOT_TOKEN`
- `NOTION_API_KEY`
- `NOTION_PARENT_PAGE_ID`
- `NOTION_DATABASE_ID`
- `DEFAULT_TIMEZONE`
- `SQLITE_PATH`

6. Create the Notion database if you have not already.

```bash
python setup_notion.py --parent-page-id YOUR_NOTION_PAGE_ID
```

7. Run the bot.

```bash
python -m bot.main
```

8. Open the dashboard.

- Open `dashboard/index.html` directly in your browser.
- On first load, enter the Notion API key and database ID into the setup modal.

## Bot Onboarding Flow

When a new user runs `/start`, Chronicle walks through:

1. Timezone
   Common timezone buttons plus `Other`
2. Wake time
   Time choice buttons
3. Sleep time
   Time choice buttons
4. Check-in frequency
   `15`, `30`, `45`, or `60` minute buttons
5. Confirmation
   Summary plus the first expected check-in time

All onboarding state is stored in SQLite.

## Commands

`/start`

- Starts onboarding.
- Example: `/start`

`/log [activity]`

- Logs something you just did.
- Example: `/log coding for 2 hours`

`/logpast [time] [activity]`

- Logs something from earlier.
- Example: `/logpast 45m ago lunch with team`

`/sleep`

- Marks the start of sleep mode.
- Example: `/sleep`

`/wake`

- Ends sleep mode and logs the sleep block.
- Example: `/wake`

`/status`

- Shows today's tracked time, streak, and current gap signal.
- Example: `/status`

`/summary [today|week|month]`

- Shows a category breakdown for the chosen period.
- Example: `/summary week`

`/edit`

- Shows the last five entries with edit/delete buttons.
- Example: `/edit`

`/skip`

- Skips the current check-in.
- Example: `/skip`

`/pause [Xh]`

- Pauses check-ins temporarily.
- Example: `/pause 3h`

`/resume`

- Resumes check-ins immediately.
- Example: `/resume`

`/setschedule`

- Lets you choose the check-in interval with buttons.
- Example: `/setschedule`

`/timezone [Area/City]`

- Updates your timezone directly.
- Example: `/timezone America/Edmonton`

`/export [week|month]`

- Sends a compact text export.
- Example: `/export month`

`/help`

- Shows command reference.
- Example: `/help`

## Dashboard

The dashboard is a single self-contained HTML file:

- `dashboard/index.html`

It supports:

- week view
- day view
- month view
- direct Notion API fetching in-browser
- search and category filters
- detail drawer
- stats sidebar
- keyboard shortcuts

To open it, just double-click the file or drag it into a browser window.

## Running Tests

Run the parser test suite:

```bash
python -m unittest tests.test_parser
```

## Docker

Build and run with Docker Compose:

```bash
docker compose up --build -d
```

SQLite is persisted in the mounted volume `chronicle_data`.

## Troubleshooting

### The bot starts but messages never arrive

- Make sure you sent at least one message to your bot first.
- Confirm `TELEGRAM_BOT_TOKEN` is correct.
- Check that polling is running and there is no firewall restriction.

### Notion writes fail

- Make sure the integration has access to the parent page and the database.
- Verify `NOTION_API_KEY` and `NOTION_DATABASE_ID`.
- Chronicle will queue entries locally if Notion is unavailable.

### The dashboard says it cannot fetch from Notion

- Re-enter the API key and database ID in the dashboard setup modal.
- Confirm the browser has network access.
- Confirm the database property names match the Chronicle schema exactly.

### Timezones look wrong

- Use an IANA timezone like `America/Edmonton`.
- Update it with `/timezone` and then log a new entry.

### The parser guessed the wrong category

- Use `/edit` to correct the entry.
- The parser is intentionally regex and keyword based, not AI-driven.

### SQLite file location is unexpected

- Set `SQLITE_PATH` explicitly in `.env`.
- In Docker, use `/data/chronicle.db`.

## Notes

- The dashboard stores the Notion key in browser `localStorage` because it fetches directly from Notion as requested.
- That is convenient, but not ideal for high-security environments.
- If you later want a more secure deployment, add a small backend proxy and remove browser-side credentials.
