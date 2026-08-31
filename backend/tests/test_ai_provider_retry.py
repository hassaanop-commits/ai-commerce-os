from __future__ import annotations

import uuid

import pytest

from app.ai.tools._common import (
    RETRYABLE_ERROR_CATEGORIES,
    ToolExecutionError,
    compute_backoff_delay,
    run_text_completion,
    start_and_call,
)
from app.ai.providers.mock_provider import MockProvider
from app.core.config import settings
from app.models import AIRun


def _run_completion(db, org, provider, *, entity_id=None):
    return run_text_completion(
        db,
        org.id,
        run_type="test.retry",
        provider=provider,
        model="mock-model",
        user_id=None,
        related_entity_type="product",
        related_entity_id=entity_id or uuid.uuid4(),
        workflow_id=None,
        system="system",
        prompt="Describe this widget",
        output_key="text",
    )


class TestBackoffCalculation:
    def test_exponential_growth_with_no_jitter(self):
        delays = [
            compute_backoff_delay(attempt, initial_delay=1.0, max_delay=100.0, random_fn=lambda: 0.0)
            for attempt in range(4)
        ]

        assert delays == [1.0, 2.0, 4.0, 8.0]

    def test_capped_at_max_delay(self):
        delay = compute_backoff_delay(10, initial_delay=1.0, max_delay=5.0, random_fn=lambda: 0.0)

        assert delay == 5.0

    def test_jitter_is_additive_and_bounded(self):
        # random_fn=1.0 is the worst case: base + 25% of base.
        delay = compute_backoff_delay(0, initial_delay=1.0, max_delay=100.0, random_fn=lambda: 1.0)

        assert delay == pytest.approx(1.25)

    def test_jitter_never_produces_an_unbounded_result(self):
        delay = compute_backoff_delay(50, initial_delay=1.0, max_delay=8.0, random_fn=lambda: 1.0)

        # However large `attempt` gets, the result is always a small,
        # finite number bounded by max_delay * 1.25 -- never unbounded.
        assert delay <= 8.0 * 1.25


class TestRetryableCategories:
    def test_retryable_set_matches_spec(self):
        assert RETRYABLE_ERROR_CATEGORIES == {"provider_timeout", "provider_rate_limited", "provider_error"}

    def test_permanent_categories_are_excluded(self):
        for category in ("provider_not_configured", "invalid_response", "capability_not_supported", "content_policy_violation", "unknown_error"):
            assert category not in RETRYABLE_ERROR_CATEGORIES


class TestRetryBehavior:
    def test_transient_failure_then_success_retries_and_succeeds(self, db, make_organization, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr("app.ai.tools._common.time.sleep", lambda seconds: sleeps.append(seconds))
        org = make_organization()
        provider = MockProvider(fail_times=2, fail_category="provider_timeout")

        run_id, text = _run_completion(db, org, provider)

        assert text
        assert provider.call_count == 3
        run = db.get(AIRun, run_id)
        assert run.status == "succeeded"
        assert run.metadata_["attempts"] == 3
        assert run.metadata_["retries"] == 2
        # Retrying never creates a second AIRun for the same logical call.
        assert db.query(AIRun).filter(AIRun.id == run_id).count() == 1
        assert len(sleeps) == 2

    def test_rate_limit_is_retried(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="provider_rate_limited")

        run_id, _ = _run_completion(db, org, provider)

        assert provider.call_count == 2
        assert db.get(AIRun, run_id).status == "succeeded"

    def test_timeout_is_retried(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="provider_timeout")

        run_id, _ = _run_completion(db, org, provider)

        assert provider.call_count == 2
        assert db.get(AIRun, run_id).status == "succeeded"

    def test_all_retries_exhausted_produces_one_failed_run(self, db, make_organization):
        org = make_organization()
        entity_id = uuid.uuid4()
        provider = MockProvider(fail_times=99, fail_category="provider_rate_limited")

        with pytest.raises(ToolExecutionError) as exc_info:
            _run_completion(db, org, provider, entity_id=entity_id)

        assert exc_info.value.category == "provider_rate_limited"
        assert provider.call_count == settings.ai_max_retries + 1

        runs = db.query(AIRun).filter(AIRun.related_entity_id == entity_id).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "failed"
        assert run.error_message == "provider_rate_limited"
        assert run.metadata_["attempts"] == settings.ai_max_retries + 1
        assert run.metadata_["retries"] == settings.ai_max_retries

    def test_permanent_failure_is_not_retried(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="provider_not_configured")

        with pytest.raises(ToolExecutionError) as exc_info:
            _run_completion(db, org, provider)

        assert exc_info.value.category == "provider_not_configured"
        assert provider.call_count == 1  # never retried

        run = db.get(AIRun, exc_info.value.run_id)
        assert run.status == "failed"
        # No retry ever happened, so no retry metadata was stashed.
        assert "attempts" not in run.metadata_
        assert "retries" not in run.metadata_

    def test_invalid_response_is_not_retried(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="invalid_response")

        with pytest.raises(ToolExecutionError):
            _run_completion(db, org, provider)

        assert provider.call_count == 1

    def test_capability_not_supported_is_not_retried(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="capability_not_supported")

        with pytest.raises(ToolExecutionError):
            _run_completion(db, org, provider)

        assert provider.call_count == 1

    def test_max_retries_is_configurable(self, db, make_organization, monkeypatch):
        monkeypatch.setattr(settings, "ai_max_retries", 1)
        org = make_organization()
        provider = MockProvider(fail_times=99, fail_category="provider_error")

        with pytest.raises(ToolExecutionError):
            _run_completion(db, org, provider)

        assert provider.call_count == 2  # 1 initial attempt + 1 retry

    def test_existing_successful_flow_is_unchanged(self, db, make_organization):
        org = make_organization()
        provider = MockProvider()

        run_id, text = _run_completion(db, org, provider)

        assert text
        assert provider.call_count == 1
        run = db.get(AIRun, run_id)
        assert run.status == "succeeded"
        # No retry occurred, so no retry-noise keys on the common-case run.
        assert "attempts" not in run.metadata_
        assert "retries" not in run.metadata_


class TestSanitizedMetadata:
    def test_no_raw_exception_text_in_error_message(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="provider_not_configured")

        with pytest.raises(ToolExecutionError) as exc_info:
            _run_completion(db, org, provider)

        run = db.get(AIRun, exc_info.value.run_id)
        from app.services.ai_runs import SANITIZED_ERROR_CATEGORIES

        assert run.error_message in SANITIZED_ERROR_CATEGORIES

    def test_metadata_contains_only_safe_keys(self, db, make_organization):
        org = make_organization()
        provider = MockProvider(fail_times=99, fail_category="provider_error")

        with pytest.raises(ToolExecutionError) as exc_info:
            _run_completion(db, org, provider)

        run = db.get(AIRun, exc_info.value.run_id)
        # workflow_id is only present when one was passed in (it wasn't
        # here); error_detail carries ProviderError's own developer-authored
        # safe message, never a raw exception repr/traceback.
        assert set(run.metadata_.keys()) <= {"workflow_id", "attempts", "retries", "error_detail"}
        assert "api_key" not in run.metadata_["error_detail"].lower()
        assert "traceback" not in run.metadata_["error_detail"].lower()


class TestStartAndCallDirectly:
    def test_retry_metadata_survives_a_manual_completion(self, db, make_organization):
        # Exercises the lower-level start_and_call() directly, the same way
        # app.ai.tools.product_images.generate_product_image() uses it, to
        # confirm the retry metadata isn't specific to run_text_completion.
        org = make_organization()
        provider = MockProvider(fail_times=1, fail_category="provider_timeout")

        run, result = start_and_call(
            db,
            org.id,
            run_type="test.retry.direct",
            provider=provider,
            model="mock-model",
            user_id=None,
            related_entity_type="product",
            related_entity_id=uuid.uuid4(),
            workflow_id=None,
            call=lambda: provider.complete(system="s", prompt="p", model="mock-model"),
        )

        assert result.text
        assert run.metadata_["attempts"] == 2
        assert run.metadata_["retries"] == 1
