"""
RSS pipeline: fetch many feeds via rss-mcp, filter to last 48h,
dedupe (in-session + at the DB), upsert into Supabase.

Setup:
    pip install openai-agents supabase python-dateutil
    # Node.js with `npx` on PATH (rss-mcp runs as a child process)
    export SUPABASE_URL=https://<project>.supabase.co
    export SUPABASE_KEY=sb_secret_...          # Supabase secret key (replaces service_role); bypasses RLS — keep secret, server-side only

Run:
    psql "$SUPABASE_DB_URL" -f schema.sql      # one-time
    python rss_pipeline.py                     # every fetch (cron / scheduler)
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from agents.mcp import MCPServerStdio
from dateutil import parser as date_parser
from supabase import acreate_client, AsyncClient
from dotenv import load_dotenv

load_dotenv(override=True)   # Load env vars from .env, but don't override existing ones (like OPENAI_API_KEY)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("rss")


# ---------- Feed registry ----------------------------------------------------
# Keys become `feed_name` in the DB. Use stable, lowercase, snake_case names —
# this is what you'll filter on in queries and dashboards.

FEEDS: dict[str, str] = {
    # AWS
    "aws_blog":              "https://feeds.feedburner.com/AmazonWebServicesBlog",
    "aws_bigdata":           "https://blogs.aws.amazon.com/bigdata/blog/feed/recentPosts.rss",
    "aws_compute":           "https://aws.amazon.com/blogs/compute/feed/",
    "aws_security":          "http://blogs.aws.amazon.com/security/blog/feed/recentPosts.rss",
    "aws_devops":            "https://blogs.aws.amazon.com/application-management/blog/feed/recentPosts.rss",

    # AI labs
    "openai_news":           "https://openai.com/news/rss.xml",
    "anthropic_news":        "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
    "anthropic_engineering": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_engineering.xml",
    "anthropic_research":    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml",
    "anthropic_red_team":    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_red.xml",
    "gemini_releases":       "https://cloud.google.com/feeds/gemini-release-notes.xml",

    # Dev / news
    "dev_to":                "https://dev.to/feed",
    "freecodecamp":          "https://www.freecodecamp.org/news/rss",
    "google_devs":           "https://feeds.feedburner.com/GDBcode",
    "sitepoint":             "https://www.sitepoint.com/sitepoint.rss",
    "sd_times":              "https://sdtimes.com/feed/",
    "real_python":           "https://realpython.com/atom.xml?format=xml",
    "real_python_podcast":   "https://realpython.com/podcasts/rpp/feed?sfnsn=mo",
}

LOOKBACK = timedelta(hours=48)
TABLE_NAME = "rss_items"
MAX_CONCURRENT_FEEDS = 5         # bounded concurrency; rss-mcp + your egress IP both like this
RSS_MCP_TIMEOUT_SECONDS = 60     # per tool call


# ---------- MCP tool call ----------------------------------------------------

DEFAULT_FEED_COUNT = 15


async def fetch_feed_json(
    server: MCPServerStdio,
    url: str,
    count: int = DEFAULT_FEED_COUNT,
) -> dict[str, Any]:
    """Call rss-mcp's `get_feed` tool directly. count=0 means 'all items'."""
    result = await server.call_tool("get_feed", {"url": url, "count": count})

    # MCP returns CallToolResult with a list of content blocks.
    # rss-mcp emits a single TextContent whose payload is JSON.
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        err = result.content[0].text if result.content else "unknown error"
        raise RuntimeError(f"get_feed error: {err}")

    if not result.content:
        raise ValueError("Empty response from get_feed")

    return json.loads(result.content[0].text)


# ---------- Normalise + filter ----------------------------------------------

def parse_pub_date(raw: Optional[str]) -> Optional[datetime]:
    """rss-mcp emits ISO 8601, but parse defensively for odd feeds."""
    if not raw:
        return None
    try:
        dt = date_parser.parse(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def stable_dedup_key(item: dict) -> str:
    """Prefer guid → link → hash(title+pubDate). Never returns empty."""
    if item.get("guid"):
        return item["guid"]
    if item.get("link"):
        return item["link"]
    fingerprint = f"{item.get('title','')}|{item.get('pubDate','')}"
    return "sha256:" + hashlib.sha256(fingerprint.encode()).hexdigest()


def normalise_items(
    feed_name: str,
    feed_json: dict,
    cutoff: datetime,
    seen: set[str],
) -> list[dict]:
    """Filter to items with pub_date >= cutoff and dedupe within this batch."""
    rows: list[dict] = []
    skipped_old = skipped_dup = skipped_undated = 0

    for item in feed_json.get("items", []):
        pub_dt = parse_pub_date(item.get("pubDate"))
        if pub_dt is None:
            skipped_undated += 1
            continue
        if pub_dt < cutoff:
            skipped_old += 1
            continue

        guid = stable_dedup_key(item)
        marker = f"{feed_name}::{guid}"
        if marker in seen:
            skipped_dup += 1
            continue
        seen.add(marker)

        rows.append({
            "feed_name":   feed_name,
            "feed_title":  feed_json.get("title"),
            "feed_link":   feed_json.get("link"),
            "guid":        guid,
            "item_title":  item.get("title") or "(untitled)",
            "description": item.get("description"),
            "link":        item.get("link"),
            "pub_date":    pub_dt.isoformat(),
            "author":      item.get("author"),
            "categories":  item.get("category") or [],
            "raw":         item,
        })

    log.debug(
        "%-22s  kept=%d  old=%d  undated=%d  in_session_dups=%d",
        feed_name, len(rows), skipped_old, skipped_undated, skipped_dup,
    )
    return rows


# ---------- Supabase upsert --------------------------------------------------

async def upsert_rows(supabase: AsyncClient, rows: list[dict]) -> int:
    """ON CONFLICT (feed_name, guid) DO NOTHING — returns count of *new* rows."""
    if not rows:
        return 0
    resp = await (
        supabase.table(TABLE_NAME)
        .upsert(rows, on_conflict="feed_name,guid", ignore_duplicates=True)
        .execute()
    )
    return len(resp.data or [])


# ---------- Per-feed worker --------------------------------------------------

async def process_feed(
    feed_name: str,
    url: str,
    server: MCPServerStdio,
    supabase: AsyncClient,
    cutoff: datetime,
    seen: set[str],
    sem: asyncio.Semaphore,
) -> tuple[str, int, int]:
    """Returns (feed_name, items_in_window, newly_inserted)."""
    async with sem:
        try:
            log.info("fetch  %s", feed_name)
            feed_json = await asyncio.wait_for(
                fetch_feed_json(server, url),
                timeout=RSS_MCP_TIMEOUT_SECONDS,
            )
            rows = normalise_items(feed_name, feed_json, cutoff, seen)
            inserted = await upsert_rows(supabase, rows)
            log.info(
                "done   %-22s  in_window=%d  inserted=%d",
                feed_name, len(rows), inserted,
            )
            return feed_name, len(rows), inserted
        except Exception as exc:
            log.exception("FAIL   %-22s  (%s)", feed_name, exc)
            return feed_name, 0, 0


# ---------- Main -------------------------------------------------------------

async def run_pipeline() -> None:
    supabase: AsyncClient = await acreate_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )

    cutoff = datetime.now(timezone.utc) - LOOKBACK
    sem = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)
    seen: set[str] = set()

    log.info("starting fetch session  cutoff=%s  feeds=%d", cutoff.isoformat(), len(FEEDS))

    # Single rss-mcp subprocess for the whole session.
    async with MCPServerStdio(
        name="rss-mcp",
        params={"command": "node", "args": [str(Path(__file__).parent.parent / "rss-mcp" / "dist" / "index.js")]},
        cache_tools_list=True,
        client_session_timeout_seconds=RSS_MCP_TIMEOUT_SECONDS,
    ) as server:
        results = await asyncio.gather(*[
            process_feed(name, url, server, supabase, cutoff, seen, sem)
            for name, url in FEEDS.items()
        ])

    total_in_window = sum(r[1] for r in results)
    total_inserted  = sum(r[2] for r in results)
    log.info(
        "session complete  feeds=%d  unique_keys=%d  in_window=%d  inserted=%d",
        len(results), len(seen), total_in_window, total_inserted,
    )


if __name__ == "__main__":
    asyncio.run(run_pipeline())