from __future__ import annotations

import pytest

from app.ai.providers.base import ProviderError
from app.ai.providers.mock_provider import MockProvider


def test_mock_provider_returns_deterministic_completion():
    provider = MockProvider()

    result = provider.complete(system="system", prompt="Describe this widget", model="mock-model")

    assert "Describe this widget" in result.text
    assert result.model == "mock-model"
    assert result.input_tokens > 0
    assert result.output_tokens > 0


def test_mock_provider_raises_provider_error_on_fail_sentinel():
    provider = MockProvider()

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="system", prompt="please __fail__ this call", model="mock-model")

    assert exc_info.value.category == "provider_error"
