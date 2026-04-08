from __future__ import annotations

import argparse
import asyncio
import json

from dotenv import load_dotenv

from bot.config import load_settings
from bot.notion_client import NotionService


async def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Create the Notion database for Chronicle.")
    parser.add_argument("--parent-page-id", help="Notion parent page ID. Falls back to NOTION_PARENT_PAGE_ID.")
    parser.add_argument("--title", default="Chronicle Activity Log", help="Database title.")
    args = parser.parse_args()

    settings = load_settings()
    parent_page_id = args.parent_page_id or settings.notion_parent_page_id
    if not parent_page_id:
        raise SystemExit("Missing parent page ID. Provide --parent-page-id or set NOTION_PARENT_PAGE_ID.")

    notion = NotionService(settings.notion_api_key, settings.notion_database_id)
    result = await notion.create_database(parent_page_id=parent_page_id, title=args.title)
    print(json.dumps({"database_id": result["id"], "url": result["url"]}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
