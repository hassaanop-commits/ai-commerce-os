from __future__ import annotations

import base64

import httpx

from app.ai.providers.base import ImageResult, ProviderError
from app.core.config import settings

_IMAGES_ENDPOINT = "https://api.openai.com/v1/images/generations"


class OpenAIImageProvider:
    """Real image provider, implemented against the plain REST endpoint via
    httpx (already a dependency) rather than the full openai SDK -- the
    images/generations call is a single JSON POST, so a whole SDK buys
    nothing here. Only generate_image() is implemented; this provider is
    never resolved for text completions.
    """

    name = "openai"

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        if not settings.openai_api_key:
            raise ProviderError(
                "provider_not_configured", "No OpenAI API key is configured for this environment."
            )

        try:
            response = httpx.post(
                _IMAGES_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": model, "prompt": prompt, "size": size, "n": 1, "response_format": "b64_json"},
                timeout=settings.ai_request_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout", "The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_error", "Could not reach the AI provider.") from exc

        if response.status_code == 429:
            raise ProviderError("provider_rate_limited", "The AI provider is rate-limiting requests.")

        if response.status_code == 400:
            error_code = _safe_error_code(response)
            if error_code in ("content_policy_violation", "moderation_blocked"):
                raise ProviderError(
                    "content_policy_violation", "The prompt was rejected by content moderation."
                )
            raise ProviderError("provider_error", "The AI provider rejected the request.")

        if response.status_code >= 400:
            raise ProviderError("provider_error", "The AI provider returned an error.")

        try:
            payload = response.json()
            b64_data = payload["data"][0]["b64_json"]
            content = base64.b64decode(b64_data)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("invalid_response", "The AI provider returned an unusable response.") from exc

        return ImageResult(content=content, content_type="image/png", model=model)


def _safe_error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("error", {}).get("code")
    except ValueError:
        return None
