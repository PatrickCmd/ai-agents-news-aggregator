"""LLM usage + cost tracking (OpenAI Agents SDK)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from news_observability.logging import get_logger

if TYPE_CHECKING:
    from agents import RunResult

_log = get_logger("costs")

# Prices per 1M tokens, USD. Update when OpenAI changes pricing.
_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    # model          : (input_per_million, output_per_million)
    "gpt-5.5": (Decimal("2.50"), Decimal("10.00")),
    "gpt-5.5-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-5.5-nano": (Decimal("0.05"), Decimal("0.40")),
    "gpt-5.4.1": (Decimal("2.00"), Decimal("8.00")),
    "gpt-5.4.1-mini": (Decimal("0.40"), Decimal("1.60")),
}


@dataclass(frozen=True)
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int
    estimated_cost_usd: float | None


def estimate_cost_usd(model: str, *, input_tokens: int, output_tokens: int) -> float | None:
    """Return estimated USD cost, or None when pricing for *model* is unknown."""
    pricing = _PRICING.get(model)
    if pricing is None:
        _log.warning("unknown model for cost estimate: {}", model)
        return None
    price_in, price_out = pricing
    cost = (Decimal(input_tokens) / Decimal(1_000_000)) * price_in + (
        Decimal(output_tokens) / Decimal(1_000_000)
    ) * price_out
    return float(cost)


def extract_usage(result: RunResult, *, model: str) -> LLMUsage:
    """Build an LLMUsage from an OpenAI Agents SDK RunResult.

    Uses `result.context_wrapper.usage` as documented in
    https://openai.github.io/openai-agents-python/.
    """
    u = result.context_wrapper.usage
    return LLMUsage(
        model=model,
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        total_tokens=u.total_tokens,
        requests=u.requests,
        estimated_cost_usd=estimate_cost_usd(
            model, input_tokens=u.input_tokens, output_tokens=u.output_tokens
        ),
    )
