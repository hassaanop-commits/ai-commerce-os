from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass(frozen=True)
class ImageResult:
    content: bytes
    content_type: str
    model: str


class ProviderError(Exception):
    """Raised for any provider failure, carrying only a sanitized category.

    `category` is one of a small closed set (see app.services.ai_runs) that
    is safe to persist on an AIRun row and show to a user. The original
    exception (which may include request/response bodies, headers, or other
    provider-internal detail) is available on `__cause__` for server-side
    logging only -- it must never be persisted or serialized back to a client.
    """

    def __init__(self, category: str, message: str | None = None) -> None:
        super().__init__(message or category)
        self.category = category


class AIProvider(Protocol):
    name: str

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
    ) -> CompletionResult:
        """Run one text-generation call. Raises ProviderError on failure."""
        ...

    def generate_image(
        self,
        *,
        prompt: str,
        model: str,
        size: str = "1024x1024",
    ) -> ImageResult:
        """Run one image-generation call. Raises ProviderError on failure.

        Not every provider supports this -- one that doesn't should raise
        ProviderError("capability_not_supported", ...) rather than leave the
        method unimplemented, so callers always get a clean, sanitized error
        instead of an AttributeError.
        """
        ...
