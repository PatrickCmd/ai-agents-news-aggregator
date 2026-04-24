from __future__ import annotations

from dataclasses import dataclass

import pytest

from news_observability.costs import LLMUsage, estimate_cost_usd, extract_usage


def test_known_model_returns_expected_cost() -> None:
    # gpt-5.4-mini: $0.15 / 1M input, $0.60 / 1M output
    cost = estimate_cost_usd("gpt-5.4-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(0.75)


def test_small_token_counts_compute_correctly() -> None:
    cost = estimate_cost_usd("gpt-5.4-mini", input_tokens=1000, output_tokens=500)
    assert cost == pytest.approx(0.00015 + 0.0003)


def test_unknown_model_returns_none() -> None:
    cost = estimate_cost_usd("made-up-model-99", input_tokens=1000, output_tokens=1000)
    assert cost is None


def test_zero_tokens_returns_zero() -> None:
    cost = estimate_cost_usd("gpt-5.4-mini", input_tokens=0, output_tokens=0)
    assert cost == pytest.approx(0.0)


def test_llm_usage_dataclass_is_frozen() -> None:
    u = LLMUsage(
        model="gpt-5.4-mini",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        requests=1,
        estimated_cost_usd=0.01,
    )
    with pytest.raises(AttributeError):
        u.model = "something-else"  # type: ignore[misc]


def test_extract_usage_reads_context_wrapper() -> None:
    @dataclass
    class _Usage:
        input_tokens: int
        output_tokens: int
        total_tokens: int
        requests: int

    @dataclass
    class _Wrapper:
        usage: _Usage

    @dataclass
    class _Result:
        context_wrapper: _Wrapper

    result = _Result(
        context_wrapper=_Wrapper(
            usage=_Usage(input_tokens=120, output_tokens=80, total_tokens=200, requests=3)
        )
    )
    usage = extract_usage(result, model="gpt-5.4-mini")  # type: ignore[arg-type]
    assert usage.input_tokens == 120
    assert usage.requests == 3
    assert usage.estimated_cost_usd is not None
    assert usage.estimated_cost_usd > 0
