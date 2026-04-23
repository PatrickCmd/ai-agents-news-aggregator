"""
RSS feed fetcher using rss-mcp + OpenAI Agents SDK.

Prereqs:
    pip install openai-agents pydantic
    # Node.js installed (npx must be on PATH)
    export OPENAI_API_KEY=...
"""
import asyncio
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

from dotenv import load_dotenv

load_dotenv(override=True)   # Load env vars from .env, but don't override existing ones (like OPENAI_API_KEY)

# ---------- 1. Pydantic schema for the structured output ----------
# Field names mirror rss-mcp's get_feed output. Use snake_case freely —
# the agent maps the tool's pubDate -> pub_date when populating the schema.

class FeedItem(BaseModel):
    title: str
    description: str = ""
    link: Optional[str] = None
    guid: Optional[str] = None
    pub_date: Optional[str] = None     # ISO 8601 from rss-mcp's pubDate
    author: Optional[str] = None
    category: list[str] = []


class FeedResult(BaseModel):
    feed_title: str
    feed_link: Optional[str] = None
    feed_description: Optional[str] = None
    items: list[FeedItem]


# ---------- 2. Agent backed by rss-mcp over stdio ----------

async def fetch_feed(rss_url: str, count: int = 5) -> FeedResult:
    async with MCPServerStdio(
        name="rss-mcp",
        params={
            "command": "node",
            "args": [str(Path(__file__).parent / "rss-mcp" / "dist" / "index.js")],
            # Optional: "env": {"PRIORITY_RSSHUB_INSTANCE": "https://..."}
        },
        cache_tools_list=True,   # tool list is static — safe to cache
        client_session_timeout_seconds=120,   # fetching feeds can be slow, especially on first run when rss-mcp's cache is cold
    ) as rss_server:

        agent = Agent(
            name="RSS Reader",
            instructions=(
                "You fetch RSS/Atom feeds using the get_feed tool. "
                "Always call get_feed exactly once with the URL the user gives you "
                "and the requested count. Return the parsed feed as structured data. "
                "Do not summarise, paraphrase, or drop items — pass them through."
            ),
            model="gpt-5.4-mini",            # any model that supports structured outputs
            mcp_servers=[rss_server],
            output_type=FeedResult,
        )

        prompt = f"Fetch the feed at {rss_url} with count={count}."
        result = await Runner.run(agent, prompt)
        return result.final_output      # already a FeedResult instance


# ---------- 3. Example usage ----------

async def main():
    rss_url = "https://feeds.feedburner.com/AmazonWebServicesBlog"   # Can be any RSS/Atom feed URL
    feed = await fetch_feed(rss_url, count=20)

    print(f"{feed.feed_title}  —  {len(feed.items)} items")
    print("-" * 60)
    for item in feed.items:
        print(f"• {item.title}")
        print(f"  {item.pub_date}  |  {item.link}")


if __name__ == "__main__":
    asyncio.run(main())