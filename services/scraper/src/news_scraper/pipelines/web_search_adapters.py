"""Web-search adapter — Playwright MCP + OpenAI Agents SDK."""

from __future__ import annotations

from time import perf_counter

from agents import Agent, Runner, trace
from agents.mcp import MCPServer
from news_config.loader import WebSearchSiteConfig
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.sanitizer import sanitize_prompt_input
from news_observability.validators import validate_structured_output

from news_scraper.mcp_servers import create_playwright_mcp_server
from news_scraper.pipelines.adapters import CrawlOutcome, SiteCrawlResult

_log = get_logger("web_search_adapter")


def _build_agent(pw_mcp: MCPServer, *, model: str, lookback_hours: int) -> Agent:
    instructions = (
        "You are a web crawler. You will be given a site URL and instructed to "
        "list recent posts. Use the Playwright browser tools to navigate to the "
        "URL and identify a list of posts. For each post extract:\n"
        "  - title (required)\n"
        "  - url (required, absolute)\n"
        "  - author (if visible, else null)\n"
        "  - published_at (ISO 8601 if visible, else null)\n"
        "  - summary (short excerpt, under 2000 chars)\n"
        f"Include at most 20 items. Return only items from the last {lookback_hours} "
        "hours based on published_at, or include the item if it appears prominently "
        "on the front page when published_at is missing."
    )
    return Agent(
        name="WebSearchCrawler",
        instructions=instructions,
        model=model,
        mcp_servers=[pw_mcp],
        output_type=SiteCrawlResult,
    )


class PlaywrightAgentCrawler:
    def __init__(self, *, model: str, max_turns: int, site_timeout: int) -> None:
        self._model = model
        self._max_turns = max_turns
        self._site_timeout = site_timeout

    async def crawl_site(self, site: WebSearchSiteConfig, *, lookback_hours: int) -> CrawlOutcome:
        t0 = perf_counter()
        async with create_playwright_mcp_server(timeout_seconds=self._site_timeout) as pw:
            agent = _build_agent(pw, model=self._model, lookback_hours=lookback_hours)
            safe_hint = sanitize_prompt_input(site.list_selector_hint)
            prompt = f"Visit {site.url} and list recent posts. {safe_hint}"
            with trace(f"web_search.{site.name}"):
                result = await Runner.run(agent, input=prompt, max_turns=self._max_turns)
            crawl = validate_structured_output(SiteCrawlResult, result.final_output)
            usage = extract_usage(result, model=self._model)
            elapsed_ms = int((perf_counter() - t0) * 1000)
            return CrawlOutcome(
                result=crawl,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                requests=usage.requests,
                cost_usd=usage.estimated_cost_usd,
                duration_ms=elapsed_ms,
            )
