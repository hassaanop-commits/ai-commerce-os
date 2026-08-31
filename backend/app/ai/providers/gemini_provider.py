from __future__ import annotations

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.ai.providers.base import CompletionResult, ImageResult, ProviderError
from app.core.config import settings

# gemini-2.5-flash is the recommended default when this provider is
# selected -- Google's cost-effective, generally-available "flash" tier
# (verified against ai.google.dev/gemini-api/docs/pricing: $0.30 / 1M input
# tokens, $2.50 / 1M output tokens, paid tier). Not hardcoded into this
# provider: callers choose the actual model string per task, exactly like
# AnthropicProvider -- see app.agents.runner for where that decision lives.
RECOMMENDED_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    """Google Gemini, via the official `google-genai` SDK (the GA package
    recommended by Google as of this writing; the older `google-generativeai`
    package is not used). Implements the same AIProvider contract as
    AnthropicProvider -- callers (tools, LangGraph nodes, the retry layer in
    app.ai.tools._common) never know which provider they're talking to.
    """

    name = "gemini"

    def __init__(self) -> None:
        # Constructed lazily, same reasoning as AnthropicProvider: importing
        # this module never requires a key to be present, only calling it does.
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not settings.gemini_api_key:
                raise ProviderError(
                    "provider_not_configured", "No Gemini API key is configured for this environment."
                )
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024) -> CompletionResult:
        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                ),
            )
        except genai_errors.ClientError as exc:
            # The SDK doesn't expose typed subclasses per status code (unlike
            # anthropic's SDK) -- .code is the HTTP status, so it's inspected
            # directly to reach the same sanitized categories.
            status = exc.code
            if status in (401, 403):
                raise ProviderError(
                    "provider_not_configured", "The AI provider rejected the configured credentials."
                ) from exc
            if status == 429:
                raise ProviderError("provider_rate_limited", "The AI provider is rate-limiting requests.") from exc
            if status == 400:
                raise ProviderError("invalid_response", "The AI provider rejected the request as invalid.") from exc
            raise ProviderError("provider_error", "The AI provider returned a client error.") from exc
        except genai_errors.ServerError as exc:
            raise ProviderError("provider_error", "The AI provider returned a server error.") from exc
        except genai_errors.APIError as exc:
            # Defensive catch-all for anything else in the hierarchy --
            # ClientError/ServerError cover every case Google documents
            # today, but a bare APIError should still map cleanly.
            raise ProviderError("provider_error", "The AI provider returned an error.") from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderError("provider_timeout", "The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            # The SDK is built on httpx -- connection-level failures (DNS,
            # refused connection, etc.) surface as httpx's own exception
            # types, not APIError, since no HTTP response was ever received.
            raise ProviderError("provider_error", "Could not reach the AI provider.") from exc
        except Exception as exc:  # noqa: BLE001 -- never let a raw SDK exception escape this boundary
            raise ProviderError("unknown_error", "The AI provider failed unexpectedly.") from exc

        text = response.text
        if not text:
            raise ProviderError("invalid_response", "The AI provider returned no text content.")

        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count if usage else None) or 0
        output_tokens = (usage.candidates_token_count if usage else None) or 0

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=response.model_version or model,
        )

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        # Out of scope for this integration -- fail honestly rather than
        # leaving the method unimplemented, same pattern as AnthropicProvider.
        raise ProviderError("capability_not_supported", "Gemini image generation is not implemented in this integration.")
