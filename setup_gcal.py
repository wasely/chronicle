"""Run this once to authorize Chronicle with your Google Calendar.

Usage:
    python setup_gcal.py

A browser window will open asking you to sign in to Google and grant
calendar access. The token is saved to token.json and reused on every
subsequent run (auto-refreshed when expired).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    load_dotenv()
    root = Path(__file__).resolve().parent

    creds_raw = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json").strip()
    creds_path = Path(creds_raw) if Path(creds_raw).is_absolute() else root / creds_raw

    token_raw = os.getenv("GOOGLE_TOKEN_PATH", "token.json").strip()
    token_path = Path(token_raw) if Path(token_raw).is_absolute() else root / token_raw

    if not creds_path.exists():
        print(f"ERROR: credentials.json not found at {creds_path}")
        print("Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    print(f"Authorization complete. Token saved to {token_path}")
    print("You can now start the bot.")


if __name__ == "__main__":
    main()
