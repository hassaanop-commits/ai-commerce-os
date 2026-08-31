from __future__ import annotations

from decimal import Decimal

from app.ai.pricing import estimate_image_cost_usd


def test_known_model_returns_flat_price():
    cost = estimate_image_cost_usd("openai", "gpt-image-1", "1024x1024")

    assert cost == Decimal("0.040000")


def test_unknown_model_prices_at_zero():
    cost = estimate_image_cost_usd("mock", "mock-image-model", "1024x1024")

    assert cost == Decimal("0")
