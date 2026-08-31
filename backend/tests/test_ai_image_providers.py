from __future__ import annotations

import pytest

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import ProviderError
from app.ai.providers.mock_provider import MockProvider
from app.ai.providers.openai_image_provider import OpenAIImageProvider


def test_mock_provider_generates_deterministic_image():
    provider = MockProvider()

    result = provider.generate_image(prompt="a red mug on a white background", model="mock-image-model")

    assert result.content_type == "image/png"
    assert result.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.model == "mock-image-model"


def test_mock_provider_image_generation_raises_on_fail_sentinel():
    provider = MockProvider()

    with pytest.raises(ProviderError) as exc_info:
        provider.generate_image(prompt="please __fail__ this", model="mock-image-model")

    assert exc_info.value.category == "provider_error"


def test_anthropic_provider_does_not_support_image_generation():
    # No network call and no API key needed -- the capability check happens
    # before anything provider-specific is touched.
    provider = AnthropicProvider()

    with pytest.raises(ProviderError) as exc_info:
        provider.generate_image(prompt="a red mug", model="claude-3-5-haiku-20241022")

    assert exc_info.value.category == "capability_not_supported"


def test_openai_image_provider_requires_configuration(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "openai_api_key", None)
    provider = OpenAIImageProvider()

    # No network call is made -- the missing-key check short-circuits first.
    with pytest.raises(ProviderError) as exc_info:
        provider.generate_image(prompt="a red mug", model="gpt-image-1")

    assert exc_info.value.category == "provider_not_configured"
