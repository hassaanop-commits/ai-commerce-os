from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

from app.ai.pricing import estimate_cost_usd
from app.ai.providers import get_provider
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import ProviderError
from app.ai.providers.gemini_provider import GeminiProvider, RECOMMENDED_MODEL
from app.ai.providers.mock_provider import MockProvider
from app.ai.tools._common import RETRYABLE_ERROR_CATEGORIES, ToolExecutionError, run_text_completion
from app.core.config import settings
from app.models import AIRun


# ---- fakes -----------------------------------------------------------------
# No real Gemini API call anywhere in this file: GeminiProvider._get_client()
# is always replaced with a fake object, so `google.genai.Client` is never
# actually constructed with a real transport.


def _fake_response(*, text="A generated product description.", input_tokens=12, output_tokens=6, model_version="gemini-2.5-flash-001"):
    usage = SimpleNamespace(prompt_token_count=input_tokens, candidates_token_count=output_tokens)
    return SimpleNamespace(text=text, usage_metadata=usage, model_version=model_version)


class _FakeModels:
    """Stateful fake standing in for client.models -- raises `exc` for the
    first `fail_times` calls (default 0, i.e. never), then returns
    `response`. Records every call's kwargs for assertions."""

    def __init__(self, *, response=None, exc: Exception | None = None, fail_times: int = 0):
        self._response = response if response is not None else _fake_response()
        self._exc = exc
        self._fail_times = fail_times
        self.call_count = 0
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.call_count += 1
        self.calls.append(kwargs)
        if self._exc is not None and self.call_count <= self._fail_times:
            raise self._exc
        return self._response


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


def _provider_with_fake(monkeypatch, **kwargs) -> tuple[GeminiProvider, _FakeModels]:
    models = _FakeModels(**kwargs)
    provider = GeminiProvider()
    monkeypatch.setattr(provider, "_get_client", lambda: _FakeClient(models))
    return provider, models


def _client_error(code: int, message: str = "error") -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"message": message, "status": "ERROR"}})


def _server_error(code: int = 500, message: str = "internal error") -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"message": message, "status": "ERROR"}})


# ---- basic completion behavior ---------------------------------------------


def test_successful_completion(monkeypatch):
    provider, models = _provider_with_fake(
        monkeypatch, response=_fake_response(text="Sleek wireless mouse.", input_tokens=20, output_tokens=8)
    )

    result = provider.complete(system="You are a copywriter.", prompt="Describe this mouse.", model="gemini-2.5-flash")

    assert result.text == "Sleek wireless mouse."
    assert result.input_tokens == 20
    assert result.output_tokens == 8
    assert models.call_count == 1


def test_model_is_forwarded_to_the_sdk(monkeypatch):
    provider, models = _provider_with_fake(monkeypatch)

    provider.complete(system="s", prompt="p", model="gemini-2.5-flash-lite")

    assert models.calls[0]["model"] == "gemini-2.5-flash-lite"


def test_prompt_and_system_are_forwarded_correctly(monkeypatch):
    provider, models = _provider_with_fake(monkeypatch)

    provider.complete(system="Be concise.", prompt="Describe this widget.", model="gemini-2.5-flash")

    call = models.calls[0]
    assert call["contents"] == "Describe this widget."
    assert call["config"].system_instruction == "Be concise."


def test_max_tokens_is_forwarded(monkeypatch):
    provider, models = _provider_with_fake(monkeypatch)

    provider.complete(system="s", prompt="p", model="gemini-2.5-flash", max_tokens=256)

    assert models.calls[0]["config"].max_output_tokens == 256


def test_result_model_prefers_the_response_model_version(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, response=_fake_response(model_version="gemini-2.5-flash-002"))

    result = provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert result.model == "gemini-2.5-flash-002"


def test_result_model_falls_back_to_requested_model_if_unset(monkeypatch):
    response = _fake_response()
    response.model_version = None
    provider, _ = _provider_with_fake(monkeypatch, response=response)

    result = provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert result.model == "gemini-2.5-flash"


def test_generate_image_is_not_supported(monkeypatch):
    provider = GeminiProvider()

    with pytest.raises(ProviderError) as exc_info:
        provider.generate_image(prompt="a red mug", model="gemini-2.5-flash")

    assert exc_info.value.category == "capability_not_supported"


# ---- configuration -----------------------------------------------------------


def test_missing_api_key_raises_without_touching_the_network(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    provider = GeminiProvider()

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_not_configured"


def test_configured_key_is_never_present_in_the_error(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "secret-test-key-should-never-leak")
    provider, _ = _provider_with_fake(monkeypatch, exc=_client_error(401), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert "secret-test-key-should-never-leak" not in str(exc_info.value)
    assert "secret-test-key-should-never-leak" not in repr(exc_info.value)


# ---- error mapping ---------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_and_permission_errors_map_to_not_configured(monkeypatch, status):
    provider, _ = _provider_with_fake(monkeypatch, exc=_client_error(status), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_not_configured"
    assert exc_info.value.category not in RETRYABLE_ERROR_CATEGORIES


def test_rate_limit_maps_to_retryable_category(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, exc=_client_error(429), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_rate_limited"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_invalid_request_maps_to_non_retryable_category(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, exc=_client_error(400), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "invalid_response"
    assert exc_info.value.category not in RETRYABLE_ERROR_CATEGORIES


def test_other_client_errors_map_to_generic_retryable_category(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, exc=_client_error(404), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_error"


def test_server_error_maps_to_retryable_category(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, exc=_server_error(503), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_error"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_timeout_maps_to_retryable_category(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, exc=httpx.TimeoutException("timed out"), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_timeout"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_network_failure_maps_to_retryable_generic_category(monkeypatch):
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
    exc = httpx.ConnectError("connection refused", request=request)
    provider, _ = _provider_with_fake(monkeypatch, exc=exc, fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "provider_error"
    assert exc_info.value.category in RETRYABLE_ERROR_CATEGORIES


def test_empty_response_text_maps_to_invalid_response(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, response=_fake_response(text=None))

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "invalid_response"


def test_completely_unexpected_exception_still_maps_to_a_sanitized_category(monkeypatch):
    provider, _ = _provider_with_fake(monkeypatch, exc=RuntimeError("something nobody anticipated"), fail_times=1)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="gemini-2.5-flash")

    assert exc_info.value.category == "unknown_error"
    assert "nobody anticipated" not in str(exc_info.value)


# ---- registry ---------------------------------------------------------------


def test_registry_resolves_gemini():
    provider = get_provider("gemini")

    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_registry_still_resolves_anthropic():
    provider = get_provider("anthropic")

    assert isinstance(provider, AnthropicProvider)


def test_registry_still_resolves_mock():
    provider = get_provider("mock")

    assert isinstance(provider, MockProvider)


def test_registry_rejects_unknown_provider():
    with pytest.raises(ProviderError):
        get_provider("some-provider-that-does-not-exist")


# ---- pricing -----------------------------------------------------------------


def test_gemini_pricing_is_calculated():
    cost = estimate_cost_usd("gemini", RECOMMENDED_MODEL, input_tokens=1_000_000, output_tokens=1_000_000)

    # $0.30 / 1M input + $2.50 / 1M output, at 1M tokens each.
    assert cost == Decimal("2.800000")


def test_unknown_gemini_model_prices_at_zero():
    cost = estimate_cost_usd("gemini", "gemini-not-a-real-model", input_tokens=1000, output_tokens=1000)

    assert cost == 0


# ---- AIRun / retry integration ----------------------------------------------


def _run_completion(db, org, provider, *, entity_id=None):
    return run_text_completion(
        db,
        org.id,
        run_type="test.gemini",
        provider=provider,
        model="gemini-2.5-flash",
        user_id=None,
        related_entity_type="product",
        related_entity_id=entity_id or uuid.uuid4(),
        workflow_id=None,
        system="system",
        prompt="Describe this widget",
        output_key="text",
    )


def test_airun_integration_records_provider_model_tokens_and_cost(db, make_organization, monkeypatch):
    org = make_organization()
    # model_version matches the pricing table key exactly here so cost_usd
    # comes out non-zero and testable -- the "response echoes back a more
    # specific model string than requested" behavior has its own dedicated
    # tests above (test_result_model_prefers_the_response_model_version).
    provider, _ = _provider_with_fake(
        monkeypatch, response=_fake_response(input_tokens=100, output_tokens=50, model_version="gemini-2.5-flash")
    )

    run_id, text = _run_completion(db, org, provider)

    assert text
    run = db.get(AIRun, run_id)
    assert run.provider == "gemini"
    assert run.model == "gemini-2.5-flash"
    assert run.status == "succeeded"
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert run.cost_usd > 0


def test_retry_integration_transient_failure_then_success(db, make_organization, monkeypatch):
    org = make_organization()
    entity_id = uuid.uuid4()
    provider, models = _provider_with_fake(monkeypatch, exc=_client_error(503), fail_times=2)

    run_id, text = _run_completion(db, org, provider, entity_id=entity_id)

    assert text
    assert models.call_count == 3
    run = db.get(AIRun, run_id)
    assert run.status == "succeeded"
    # Retrying never creates a second AIRun for the same logical call.
    assert db.query(AIRun).filter(AIRun.id == run_id).count() == 1


def test_retry_metadata_is_recorded_for_gemini_runs(db, make_organization, monkeypatch):
    org = make_organization()
    provider, _ = _provider_with_fake(monkeypatch, exc=_client_error(429), fail_times=1)

    run_id, _ = _run_completion(db, org, provider)

    run = db.get(AIRun, run_id)
    assert run.metadata_["attempts"] == 2
    assert run.metadata_["retries"] == 1


def test_permanent_gemini_failure_is_not_retried(db, make_organization, monkeypatch):
    org = make_organization()
    provider, models = _provider_with_fake(monkeypatch, exc=_client_error(401), fail_times=99)

    with pytest.raises(ToolExecutionError):
        _run_completion(db, org, provider)

    assert models.call_count == 1


# ---- co-existing providers ---------------------------------------------------


def test_anthropic_provider_still_works_unaffected_by_gemini(monkeypatch):
    from google.genai import errors as _unused  # noqa: F401 -- import side effects only, sanity check

    provider = AnthropicProvider()
    monkeypatch.setattr(settings, "anthropic_api_key", None)

    with pytest.raises(ProviderError) as exc_info:
        provider.complete(system="s", prompt="p", model="claude-haiku-4-5-20251001")

    assert exc_info.value.category == "provider_not_configured"


def test_mock_provider_still_works_unaffected_by_gemini():
    provider = MockProvider()

    result = provider.complete(system="s", prompt="describe this", model="mock-model")

    assert "describe this" in result.text
