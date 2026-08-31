from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session as DBSession

from app.db.tenant import org_scoped
from app.models import AIRun

# The only error categories ever persisted to ai_runs.error_message. Kept
# closed and separate from any provider's own exception text so a raw
# provider error (which can echo request detail) never reaches the database
# or a client -- see app.ai.providers.base.ProviderError.
SANITIZED_ERROR_CATEGORIES = frozenset(
    {
        "provider_not_configured",
        "provider_timeout",
        "provider_rate_limited",
        "provider_error",
        "invalid_response",
        "capability_not_supported",
        "content_policy_violation",
        "unknown_error",
    }
)

# One short, human-readable sentence per sanitized category -- never built
# from a provider's own exception text (see ProviderError), so it's safe to
# return straight to a client. Kept alongside the closed set above rather
# than in a frontend-only lookup, so any client (not just this repo's own
# frontend, which has its own similar copy for other surfaces) gets a
# ready-to-display message without needing to know the category vocabulary.
_ERROR_CATEGORY_MESSAGES: dict[str, str] = {
    "provider_not_configured": "AI provider is not configured.",
    "provider_timeout": "The AI provider timed out. Please try again.",
    "provider_rate_limited": "AI service is temporarily rate limited. Please try again.",
    "provider_error": "The AI provider returned an error. Please try again.",
    "invalid_response": "The AI provider returned a response that couldn't be used. Please try again.",
    "capability_not_supported": "This AI provider doesn't support that capability.",
    "content_policy_violation": "The request was rejected by content moderation.",
    "unknown_error": "AI generation failed. Please try again.",
}


def describe_error_category(category: str | None) -> str | None:
    if category is None:
        return None
    return _ERROR_CATEGORY_MESSAGES.get(category, _ERROR_CATEGORY_MESSAGES["unknown_error"])


class AIRunNotFoundError(Exception):
    pass


def create_run(
    db: DBSession,
    organization_id: uuid.UUID,
    *,
    run_type: str,
    provider: str,
    model: str,
    user_id: uuid.UUID | None = None,
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> AIRun:
    run_metadata = dict(metadata or {})
    if workflow_id is not None:
        run_metadata["workflow_id"] = str(workflow_id)

    run = AIRun(
        organization_id=organization_id,
        user_id=user_id,
        run_type=run_type,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        provider=provider,
        model=model,
        status="pending",
        metadata_=run_metadata,
    )
    db.add(run)
    db.flush()
    return run


def mark_running(db: DBSession, run: AIRun) -> AIRun:
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.flush()
    return run


def complete_run(
    db: DBSession,
    run: AIRun,
    *,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal,
    output_metadata: dict | None = None,
) -> AIRun:
    run.status = "succeeded"
    run.completed_at = datetime.now(timezone.utc)
    run.input_tokens = input_tokens
    run.output_tokens = output_tokens
    run.cost_usd = cost_usd
    if output_metadata:
        run.metadata_ = {**run.metadata_, **output_metadata}
    db.flush()
    return run


def fail_run(db: DBSession, run: AIRun, *, category: str, detail: str | None = None) -> AIRun:
    safe_category = category if category in SANITIZED_ERROR_CATEGORIES else "unknown_error"
    run.status = "failed"
    run.completed_at = datetime.now(timezone.utc)
    run.error_message = safe_category
    if detail:
        run.metadata_ = {**run.metadata_, "error_detail": detail}
    db.flush()
    return run


def get_run(db: DBSession, organization_id: uuid.UUID, run_id: uuid.UUID) -> AIRun:
    run = (
        db.execute(org_scoped(AIRun, organization_id).where(AIRun.id == run_id)).scalars().one_or_none()
    )
    if run is None:
        raise AIRunNotFoundError(run_id)
    return run


def list_runs_for_entity(
    db: DBSession, organization_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> list[AIRun]:
    return (
        db.execute(
            org_scoped(AIRun, organization_id)
            .where(AIRun.related_entity_type == entity_type, AIRun.related_entity_id == entity_id)
            .order_by(AIRun.created_at.desc())
        )
        .scalars()
        .all()
    )
