from __future__ import annotations

import anthropic

from app.ai.providers.base import CompletionResult, ImageResult, ProviderError
from app.core.config import settings


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        # The client is only constructed once a call is actually made (see
        # complete()) so importing this module never requires a key to be
        # present -- only running it does.
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not settings.anthropic_api_key:
                raise ProviderError(
                    "provider_not_configured", "No Anthropic API key is configured for this environment."
                )
            self._client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key, timeout=settings.ai_request_timeout_seconds
            )
        return self._client

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024) -> CompletionResult:
        client = self._get_client()
        try:
            response = client.messages.create(
                model=model,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APITimeoutError as exc:
            raise ProviderError("provider_timeout", "The AI provider timed out.") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("provider_rate_limited", "The AI provider is rate-limiting requests.") from exc
        except anthropic.AuthenticationError as exc:
            # A rejected credential will never succeed on retry -- distinct
            # from the generic APIStatusError bucket below (which the retry
            # layer treats as transient) so this fails immediately instead.
            raise ProviderError(
                "provider_not_configured", "The AI provider rejected the configured credentials."
            ) from exc
        except anthropic.BadRequestError as exc:
            # A malformed request will be identically malformed on retry --
            # also excluded from the generic (retryable) bucket below.
            raise ProviderError("invalid_response", "The AI provider rejected the request as invalid.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError("provider_error", "The AI provider returned an error.") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("provider_error", "Could not reach the AI provider.") from exc

        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        if not text_blocks:
            raise ProviderError("invalid_response", "The AI provider returned no text content.")

        return CompletionResult(
            text="".join(text_blocks),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        # Anthropic has no image-generation API -- fail honestly rather than
        # leaving the method unimplemented (which would raise AttributeError
        # deep inside a tool call instead of a clean, sanitized category).
        raise ProviderError("capability_not_supported", "Anthropic does not support image generation.")
