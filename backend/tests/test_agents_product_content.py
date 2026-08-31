from __future__ import annotations

from app.agents.runner import (
    CONTENT_MODEL,
    UTILITY_MODEL,
    default_content_model,
    default_utility_model,
    run_product_content_workflow,
)
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import CompletionResult, ProviderError
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.mock_provider import MockProvider
from app.models import AIRun


class _FailOnNthCallProvider:
    """A provider that behaves exactly like MockProvider (same deterministic
    echo) except it fails on one specific call, by call order rather than
    prompt content -- lets a test isolate "step N fails" precisely, which
    the "__fail__" sentinel can't do here since every node's prompt is
    built from the same shared _product_prompt().

    Uses "invalid_response" (non-retryable) rather than "provider_error":
    the latter is retryable (Betterment Day 2), so the shared retry loop
    would silently call complete() again and this test double would then
    succeed on the retry, masking the very failure the test wants to force.
    """

    name = "mock"

    def __init__(self, fail_on_call: int) -> None:
        self._fail_on_call = fail_on_call
        self._call_count = 0

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024) -> CompletionResult:
        self._call_count += 1
        if self._call_count == self._fail_on_call:
            raise ProviderError("invalid_response", "Forced failure for test.")
        text = f"[mock:{model}] {prompt.strip()[:200]}"
        return CompletionResult(
            text=text, input_tokens=max(1, len(prompt) // 4), output_tokens=max(1, len(text) // 4), model=model
        )

    def generate_image(self, **kwargs):
        raise ProviderError("capability_not_supported", "Not supported by this test double.")


def test_workflow_succeeds_and_correlates_runs(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = MockProvider()

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.status == "succeeded"
    assert result.analysis is not None
    assert result.generated_description is not None
    assert result.generated_title is not None
    assert result.generated_tags is not None
    assert len(result.ai_run_ids) == 4

    runs = db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()
    assert len(runs) == 4
    assert {r.run_type for r in runs} == {
        "product_content.analyze",
        "product_content.generate_description",
        "product_content.generate_title",
        "product_content.generate_tags",
    }
    assert all(r.status == "succeeded" for r in runs)
    workflow_ids = {r.metadata_["workflow_id"] for r in runs}
    assert workflow_ids == {str(result.workflow_id)}


def test_workflow_routes_each_task_to_its_own_model_tier(db, make_organization, make_product):
    # Analysis is a lightweight summarization task; the description is
    # customer-facing content -- they should NOT share a model, unlike the
    # single-model setup this replaced (Betterment Phase Day 1).
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = MockProvider()

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    runs = {r.run_type: r for r in db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()}
    assert runs["product_content.analyze"].model == UTILITY_MODEL
    assert runs["product_content.generate_description"].model == CONTENT_MODEL
    assert UTILITY_MODEL != CONTENT_MODEL


def test_workflow_short_circuits_when_analyze_fails(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="__fail__ Widget")
    provider = MockProvider()

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.status == "failed"
    assert result.error_category == "provider_error"
    assert result.generated_description is None
    assert result.generated_title is None
    assert result.generated_tags is None
    # Only the analyze run was created -- nothing downstream ran.
    assert len(result.ai_run_ids) == 1
    run = db.query(AIRun).filter(AIRun.id == result.ai_run_ids[0]).one()
    assert run.run_type == "product_content.analyze"
    assert run.status == "failed"
    assert run.error_message == "provider_error"


def test_workflow_generates_title_and_tags(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = MockProvider()

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.generated_title
    assert isinstance(result.generated_tags, list)
    assert len(result.generated_tags) > 0

    tags_run = db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids), AIRun.run_type == "product_content.generate_tags").one()
    # The parsed list, not the raw comma-separated text, is what's persisted
    # -- this is what apply_tags and the frontend actually consume.
    assert tags_run.metadata_["tags"] == result.generated_tags
    assert all(isinstance(tag, str) for tag in tags_run.metadata_["tags"])


def test_workflow_title_and_tags_use_the_utility_model_tier(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = MockProvider()

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    runs = {r.run_type: r for r in db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()}
    assert runs["product_content.generate_title"].model == UTILITY_MODEL
    assert runs["product_content.generate_tags"].model == UTILITY_MODEL


def test_workflow_short_circuits_when_description_fails(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = _FailOnNthCallProvider(fail_on_call=2)  # 1=analyze, 2=description

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.status == "failed"
    assert result.analysis is not None
    assert result.generated_description is None
    assert result.generated_title is None
    assert result.generated_tags is None
    run_types = {r.run_type for r in db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()}
    assert run_types == {"product_content.analyze", "product_content.generate_description"}


def test_workflow_short_circuits_when_title_fails(db, make_organization, make_product):
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = _FailOnNthCallProvider(fail_on_call=3)  # 1=analyze, 2=description, 3=title

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.status == "failed"
    assert result.generated_description is not None
    assert result.generated_title is None
    assert result.generated_tags is None
    # generate_tags never ran once title failed.
    run_types = {r.run_type for r in db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()}
    assert run_types == {
        "product_content.analyze",
        "product_content.generate_description",
        "product_content.generate_title",
    }


def test_default_utility_and_content_model_helpers():
    assert default_utility_model("anthropic") == UTILITY_MODEL
    assert default_content_model("anthropic") == CONTENT_MODEL
    assert default_utility_model("gemini") == "gemini-2.5-flash"
    assert default_content_model("gemini") == "gemini-2.5-flash"
    # Unlisted providers (including "mock", which accepts any string) fall
    # back to the same constants every MockProvider-based test already
    # exercises -- this table is additive, never a behavior change for them.
    assert default_utility_model("mock") == UTILITY_MODEL
    assert default_content_model("mock") == CONTENT_MODEL
    assert default_utility_model("some-future-provider") == UTILITY_MODEL


class _FakeAnthropicMessages:
    def __init__(self, response) -> None:
        self._response = response

    def create(self, **kwargs):
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response) -> None:
        self.messages = _FakeAnthropicMessages(response)


def _fake_anthropic_response(text: str = "Generated text.", model: str = "claude-haiku-4-5-20251001"):
    from types import SimpleNamespace

    block = SimpleNamespace(type="text", text=text)
    usage = SimpleNamespace(input_tokens=15, output_tokens=8)
    return SimpleNamespace(content=[block], usage=usage, model=model)


def test_workflow_routes_anthropic_specific_models_when_anthropic_is_the_provider(
    db, make_organization, make_product, monkeypatch
):
    from app.ai.providers.anthropic_provider import AnthropicProvider

    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = AnthropicProvider()
    monkeypatch.setattr(provider, "_get_client", lambda: _FakeAnthropicClient(_fake_anthropic_response()))

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.status == "succeeded"
    runs = db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()
    assert all(r.provider == "anthropic" for r in runs)
    # Two different tiers, both Anthropic-specific -- no provider-specific
    # branching in the graph itself made this happen, only runner.py's
    # per-provider default tables.
    assert {r.model for r in runs} == {UTILITY_MODEL, CONTENT_MODEL}


class _FakeGeminiModels:
    def __init__(self, response) -> None:
        self._response = response

    def generate_content(self, **kwargs):
        return self._response


class _FakeGeminiClient:
    def __init__(self, response) -> None:
        self.models = _FakeGeminiModels(response)


def _fake_gemini_response(text: str = "Generated text.", model_version: str = "gemini-2.5-flash"):
    from types import SimpleNamespace

    usage = SimpleNamespace(prompt_token_count=15, candidates_token_count=8)
    return SimpleNamespace(text=text, usage_metadata=usage, model_version=model_version)


def test_workflow_routes_gemini_specific_models_when_gemini_is_the_provider(
    db, make_organization, make_product, monkeypatch
):
    from app.ai.providers.gemini_provider import GeminiProvider

    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    provider = GeminiProvider()
    monkeypatch.setattr(provider, "_get_client", lambda: _FakeGeminiClient(_fake_gemini_response()))

    result = run_product_content_workflow(db, org.id, product, provider=provider, user_id=None)

    assert result.status == "succeeded"
    runs = db.query(AIRun).filter(AIRun.id.in_(result.ai_run_ids)).all()
    assert all(r.provider == "gemini" for r in runs)
    assert all(r.model == "gemini-2.5-flash" for r in runs)
