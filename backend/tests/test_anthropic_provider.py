from __future__ import annotations

import anthropic
import httpx
import pytest

from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import ProviderError
from app.ai.tools._common import RETRYABLE_ERROR_CATEGORIES

# These tests exercise AnthropicProvider's exception -> sanitized-category
# mapping directly, without any real network call: _get_client() is
# replaced with a fake object whose messages.create() raises a real SDK
# exception instance (constructed standalone -- httpx.Request/Response
# don't require an active connection).


class _FakeMessages:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create(self, **kwargs):
        raise self._exc


class _FakeClient:
    def __init__(self, exc: Exception) -> None:
        self.messages = _FakeMessages(exc)


def _status_error(cls, status_code: int, message: str = "error"):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=status_code, request=request)
    return cls(message, response=response, body=None)


def _provider_with_fake_client(monkeypatch, exc: Exception) -> AnthropicProvider:
    provider = AnthropicProvider()
    monkeypatch.setattr(provider, "_get_client", lambda: _FakeClient(exc))
    return provider


def test_authentication_error_maps_to_provider_not_configured(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, _status_error(anthropic.AuthenticationError, 401))

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "provider_not_configured"
    assert exc_info.value.category not in RETRYABLE_ERROR_CATEGORIES


def test_bad_request_error_maps_to_invalid_response(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, _status_error(anthropic.BadRequestError, 400))

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "invalid_response"
    assert exc_info.value.category not in RETRYABLE_ERROR_CATEGORIES


def test_rate_limit_error_maps_to_retryable_category(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, _status_error(anthropic.RateLimitError, 429))

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "provider_rate_limited"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_internal_server_error_maps_to_retryable_generic_category(monkeypatch):
    provider = _provider_with_fake_client(monkeypatch, _status_error(anthropic.InternalServerError, 500))

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "provider_error"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_timeout_error_maps_to_retryable_category(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APITimeoutError(request=request)
    provider = _provider_with_fake_client(monkeypatch, exc)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "provider_timeout"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_connection_error_maps_to_retryable_generic_category(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIConnectionError(request=request)
    provider = _provider_with_fake_client(monkeypatch, exc)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "provider_error"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_not_configured_raised_without_touching_the_network(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None)
    provider = AnthropicProvider()

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="m")

    assert exc_info.value.category == "provider_not_configured"
