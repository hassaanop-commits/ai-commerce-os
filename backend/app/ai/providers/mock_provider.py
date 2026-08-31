from __future__ import annotations

from app.ai.providers.base import CompletionResult, ImageResult, ProviderError

# A real (if minimal) PNG magic-byte prefix, so sniff_image_content_type()
# accepts it exactly like a real provider's output would -- padded with
# zero bytes since nothing ever decodes this as actual pixel data. Mirrors
# the FAKE_JPEG_BYTES fixture already used for upload tests.
_FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128


class MockProvider:
    """Deterministic, network-free provider used by tests and local dev.

    Never calls out to a real API -- output is derived purely from the
    prompt so tests can assert on it without any provider credentials.
    Prompting it with the literal string "__fail__" triggers a ProviderError
    (category "provider_error") on every call, for exercising the failure
    path without needing a real outage.

    For deterministic retry testing, construct with `fail_times` > 0: the
    first `fail_times` calls (across complete() and generate_image()
    combined) raise ProviderError(fail_category, ...), and every call after
    that succeeds normally. This is independent of the "__fail__" sentinel
    above -- use whichever fits the test:
      - fail_times=2 with a retryable category -> "fails twice, then
        succeeds" (retry-and-recover)
      - fail_times=99 -> "always fails" (retries exhausted)
      - fail_times=1 with a non-retryable category (e.g.
        "provider_not_configured") -> "permanent failure, no retry"
    """

    name = "mock"

    def __init__(self, *, fail_times: int = 0, fail_category: str = "provider_error") -> None:
        self._fail_times = fail_times
        self._fail_category = fail_category
        self.call_count = 0

    def _maybe_fail_from_counter(self) -> None:
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise ProviderError(self._fail_category, "Mock provider was configured to fail.")

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024) -> CompletionResult:
        if "__fail__" in prompt:
            raise ProviderError("provider_error", "Mock provider was asked to fail.")
        self._maybe_fail_from_counter()

        text = f"[mock:{model}] {prompt.strip()[:200]}"
        return CompletionResult(
            text=text,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            model=model,
        )

    def generate_image(self, *, prompt: str, model: str, size: str = "1024x1024") -> ImageResult:
        if "__fail__" in prompt:
            raise ProviderError("provider_error", "Mock provider was asked to fail.")
        self._maybe_fail_from_counter()

        return ImageResult(content=_FAKE_PNG_BYTES, content_type="image/png", model=model)
