from __future__ import annotations

from app.ai.providers.base import AIProvider, CompletionResult, ProviderError
from app.ai.providers.mock_provider import MockProvider
from app.core.config import settings

_PROVIDERS: dict[str, AIProvider] = {}


def _build_provider(name: str) -> AIProvider:
    if name == "mock":
        return MockProvider()
    if name == "anthropic":
        from app.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "gemini":
        from app.ai.providers.gemini_provider import GeminiProvider

        return GeminiProvider()
    if name == "openai":
        from app.ai.providers.openai_image_provider import OpenAIImageProvider

        return OpenAIImageProvider()
    raise ProviderError(f"Unknown AI provider: {name}")


def get_provider(name: str) -> AIProvider:
    # Providers are cheap, stateless clients -- cached per name so repeated
    # tool calls within a process don't reconstruct an SDK client each time.
    if name not in _PROVIDERS:
        _PROVIDERS[name] = _build_provider(name)
    return _PROVIDERS[name]


def get_default_ai_provider() -> AIProvider:
    # A FastAPI-dependency-shaped seam (same pattern as get_storage_service /
    # get_email_service): routes depend on this rather than calling
    # get_provider() directly, so tests can override it with MockProvider and
    # make zero real network calls.
    return get_provider(settings.ai_default_provider)


def get_default_image_provider() -> AIProvider:
    # A separate seam from get_default_ai_provider(): the text and image
    # capabilities can legitimately resolve to different providers (e.g.
    # Anthropic for text, OpenAI for images), so they're configured and
    # overridden independently.
    return get_provider(settings.ai_image_provider)


__all__ = [
    "AIProvider",
    "CompletionResult",
    "ProviderError",
    "get_provider",
    "get_default_ai_provider",
    "get_default_image_provider",
]
