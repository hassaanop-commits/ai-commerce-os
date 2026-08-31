from __future__ import annotations

from decimal import Decimal

from app.agents.runner import CONTENT_MODEL, UTILITY_MODEL
from app.ai.pricing import estimate_cost_usd


def test_utility_model_is_priced():
    cost = estimate_cost_usd("anthropic", UTILITY_MODEL, input_tokens=1000, output_tokens=1000)

    assert cost > Decimal("0")


def test_content_model_is_priced_higher_than_utility_model():
    utility_cost = estimate_cost_usd("anthropic", UTILITY_MODEL, input_tokens=1000, output_tokens=1000)
    content_cost = estimate_cost_usd("anthropic", CONTENT_MODEL, input_tokens=1000, output_tokens=1000)

    # The whole point of routing description generation to a higher tier is
    # that it costs more per token -- if this ever stops being true, the
    # model-tier strategy in runner.py needs to be revisited.
    assert content_cost > utility_cost


def test_unknown_model_prices_at_zero():
    cost = estimate_cost_usd("anthropic", "claude-3-5-haiku-20241022", input_tokens=1000, output_tokens=1000)

    # The old, now-superseded dated snapshot is deliberately no longer in
    # the pricing table -- confirms it falls back to the documented
    # unlisted-model behavior rather than silently keeping stale pricing.
    assert cost == Decimal("0")
