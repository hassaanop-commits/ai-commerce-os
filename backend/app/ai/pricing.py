from __future__ import annotations

from decimal import Decimal

# USD per 1,000 tokens. Observability-grade estimates, not a billing source of
# truth -- good enough to show a run's approximate cost and to later gate a
# per-plan spending limit, not to reconcile against a provider invoice.
# Unlisted provider/model pairs (including "mock") price at zero.
#
# These figures are carried forward from the equivalent tier's previously
# published pricing (Haiku / Sonnet / Opus have historically kept stable
# relative pricing across model generations) -- confirm against Anthropic's
# current pricing page before treating this as authoritative; it was not
# possible to verify live pricing at the time this table was last updated
# (Betterment Phase Day 1).
_PRICING_PER_1K: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("anthropic", "claude-haiku-4-5-20251001"): (Decimal("0.0008"), Decimal("0.0040")),
    ("anthropic", "claude-sonnet-5"): (Decimal("0.0030"), Decimal("0.0150")),
    ("anthropic", "claude-opus-5"): (Decimal("0.0150"), Decimal("0.0750")),
    # Verified directly against ai.google.dev/gemini-api/docs/pricing (paid
    # tier, standard, text/image/video input) at the time this was added:
    # $0.30 / 1M input tokens, $2.50 / 1M output tokens.
    #
    # Gemini also offers a free tier for this model with $0 input/output --
    # this table has no notion of "free tier" (it prices one provider/model
    # pair a single way), so it always estimates the paid-tier rate. That
    # deliberately overstates cost for anyone actually on the free tier,
    # which is the safe direction to be wrong in for a cost estimate; it is
    # not a billing system and this is not a billing decision.
    ("gemini", "gemini-2.5-flash"): (Decimal("0.0003"), Decimal("0.0025")),
}


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    input_price, output_price = _PRICING_PER_1K.get((provider, model), (Decimal("0"), Decimal("0")))
    cost = (Decimal(input_tokens) / 1000) * input_price + (Decimal(output_tokens) / 1000) * output_price
    return cost.quantize(Decimal("0.000001"))


# Image generation is priced flat-per-call, not per-token, so it doesn't fit
# the token-based estimator above. Unlisted provider/model/size combinations
# (including "mock") price at zero.
_IMAGE_PRICING_PER_CALL: dict[tuple[str, str, str], Decimal] = {
    ("openai", "gpt-image-1", "1024x1024"): Decimal("0.040000"),
    ("openai", "dall-e-3", "1024x1024"): Decimal("0.040000"),
}


def estimate_image_cost_usd(provider: str, model: str, size: str) -> Decimal:
    return _IMAGE_PRICING_PER_CALL.get((provider, model, size), Decimal("0"))
