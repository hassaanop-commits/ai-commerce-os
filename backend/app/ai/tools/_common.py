from __future__ import annotations

import random
import time
import uuid
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session as DBSession

from app.ai.pricing import estimate_cost_usd
from app.ai.providers.base import AIProvider, ProviderError
from app.core.config import settings
from app.models import AIRun
from app.services import ai_runs

# Shared by every tool module (product_content.py, product_images.py, and
# any future one): the AIRun create -> running -> succeeded/failed lifecycle
# is identical regardless of what the provider call actually does. Extracted
# here rather than duplicated per tool module.

T = TypeVar("T")

# Only these sanitized categories are worth retrying -- genuinely transient
# conditions (network hiccup, momentary timeout, rate limit) where an
# identical retry has a real chance of succeeding. Everything else
# (provider_not_configured, invalid_response, capability_not_supported,
# content_policy_violation, unknown_error) describes a request or
# configuration that will fail exactly the same way every time, so retrying
# it would only waste time and money.
RETRYABLE_ERROR_CATEGORIES = frozenset({"provider_timeout", "provider_rate_limited", "provider_error"})


class ToolExecutionError(Exception):
    """Raised when a provider call fails (after retries, if any, are
    exhausted). The AIRun is already recorded as failed (with a sanitized
    category) before this is raised -- callers never need to record the
    failure themselves, only handle it."""

    def __init__(self, run_id: uuid.UUID, category: str) -> None:
        super().__init__(category)
        self.run_id = run_id
        self.category = category


def compute_backoff_delay(
    attempt: int,
    *,
    initial_delay: float,
    max_delay: float,
    random_fn: Callable[[], float] = random.random,
) -> float:
    """Delay in seconds before retry attempt `attempt` (0-indexed: 0 is the
    delay before the *first* retry, i.e. after the first failure).

    Exponential growth (initial_delay * 2**attempt), capped at max_delay,
    plus up to 25% jitter on top so concurrent callers retrying the same
    failing dependency don't all wake up in lockstep. The jitter is
    intentionally allowed to push the final delay slightly above max_delay
    (up to max_delay * 1.25) -- the cap bounds the exponential growth, not
    the jitter; the result is still always a small, finite number, never
    unbounded.
    """
    base = min(initial_delay * (2**attempt), max_delay)
    jitter = base * 0.25 * random_fn()
    return base + jitter


def start_and_call(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    run_type: str,
    provider: AIProvider,
    model: str,
    user_id: uuid.UUID | None,
    related_entity_type: str,
    related_entity_id: uuid.UUID,
    workflow_id: uuid.UUID | None,
    call: Callable[[], T],
) -> tuple[AIRun, T]:
    """Create a run, mark it running, invoke `call` (retrying transient
    failures with bounded exponential backoff), and fail the run (with a
    sanitized category) once retries are exhausted or the failure is
    permanent. Does NOT mark the run succeeded -- that's left to the
    caller, since some callers (image generation) need to validate the
    result before it's safe to call the run a success.

    One `call()` still produces exactly one AIRun regardless of how many
    attempts it took -- retries happen inside this single run's lifecycle,
    never as separate AIRun rows.
    """
    # Each AIRun's lifecycle is committed independently of the caller's own
    # transaction (same reasoning as app.services.audit.record_event): a
    # provider invocation must be durably recorded for cost/usage tracking
    # even if a later step in the workflow fails and the caller never
    # reaches its own commit.
    run = ai_runs.create_run(
        db,
        organization_id,
        run_type=run_type,
        provider=provider.name,
        model=model,
        user_id=user_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        workflow_id=workflow_id,
    )
    db.commit()

    ai_runs.mark_running(db, run)
    db.commit()

    attempt = 0
    while True:
        attempt += 1
        try:
            result = call()
        except ProviderError as exc:
            retries_used = attempt - 1
            can_retry = exc.category in RETRYABLE_ERROR_CATEGORIES and retries_used < settings.ai_max_retries
            if can_retry:
                delay = compute_backoff_delay(
                    retries_used,
                    initial_delay=settings.ai_retry_initial_delay_seconds,
                    max_delay=settings.ai_retry_max_delay_seconds,
                )
                time.sleep(delay)
                continue

            # Permanent failure, or retries exhausted -- record once and
            # give up. `retries` never contains anything beyond a count and
            # a category name, both already part of the sanitized vocabulary
            # -- never the raw exception or any provider/request detail.
            if attempt > 1:
                run.metadata_ = {**run.metadata_, "attempts": attempt, "retries": retries_used}
            ai_runs.fail_run(db, run, category=exc.category, detail=str(exc))
            db.commit()
            raise ToolExecutionError(run.id, exc.category) from exc
        else:
            if attempt > 1:
                run.metadata_ = {**run.metadata_, "attempts": attempt, "retries": attempt - 1}
            return run, result


def run_text_completion(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    run_type: str,
    provider: AIProvider,
    model: str,
    user_id: uuid.UUID | None,
    related_entity_type: str,
    related_entity_id: uuid.UUID,
    workflow_id: uuid.UUID | None,
    system: str,
    prompt: str,
    output_key: str,
) -> tuple[uuid.UUID, str]:
    run, result = start_and_call(
        db,
        organization_id,
        run_type=run_type,
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        workflow_id=workflow_id,
        call=lambda: provider.complete(system=system, prompt=prompt, model=model),
    )

    cost = estimate_cost_usd(provider.name, result.model, result.input_tokens, result.output_tokens)
    ai_runs.complete_run(
        db,
        run,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost,
        output_metadata={output_key: result.text},
    )
    db.commit()

    return run.id, result.text
