from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from app.schemas.product import ProductAssetRead

if TYPE_CHECKING:
    from app.models import AIRun

WorkflowStatus = Literal["succeeded", "failed"]


class AIRunRead(BaseModel):
    id: uuid.UUID
    run_type: str
    provider: str
    model: str
    status: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    metadata: dict

    model_config = {"from_attributes": True}

    @classmethod
    def from_run(cls, run: "AIRun") -> "AIRunRead":
        return cls(
            id=run.id,
            run_type=run.run_type,
            provider=run.provider,
            model=run.model,
            status=run.status,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            cost_usd=run.cost_usd,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
            metadata=run.metadata_,
        )


class GenerateDescriptionResponse(BaseModel):
    workflow_id: uuid.UUID
    status: WorkflowStatus
    analysis: str | None
    generated_description: str | None
    generated_title: str | None
    generated_tags: list[str] | None
    error_category: str | None
    ai_runs: list[AIRunRead]


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    # Capped at 4 -- each variation is its own paid provider call (see
    # app.ai.pricing._IMAGE_PRICING_PER_CALL), so this bounds the cost/abuse
    # surface of a single request rather than reflecting any provider limit.
    variations: int = Field(default=1, ge=1, le=4)


class GenerateImageVariationResult(BaseModel):
    # 0-based slot number in generation order, stable regardless of which
    # other slots succeeded or failed.
    index: int
    status: WorkflowStatus
    # Exactly one of (asset, error_category) is set -- a failed slot never
    # carries a placeholder asset, and a succeeded slot never carries a
    # leftover error category.
    asset: ProductAssetRead | None = None
    error_category: str | None = None
    # A short, human-readable sentence derived from error_category (see
    # app.services.ai_runs.describe_error_category) -- never built from the
    # provider's own exception text, so it's always safe to display as-is.
    error_message: str | None = None


class GenerateImageResponse(BaseModel):
    workflow_id: uuid.UUID
    status: WorkflowStatus
    image_prompt: str | None
    error_category: str | None
    ai_runs: list[AIRunRead]
    # `asset` is the first successfully generated image (kept for backward
    # compatibility with single-image callers); `assets` holds every
    # successfully generated variation, in generation order. When status is
    # "succeeded", assets has at least one entry. A variations request that
    # partially fails still reports "succeeded" with only the successful
    # assets present -- failed attempts are visible in `ai_runs` (status
    # "failed") but never produce a fabricated asset.
    asset: ProductAssetRead | None = None
    assets: list[ProductAssetRead] = Field(default_factory=list)
    # One entry per image-generation attempt (0, 1, or N depending on how far
    # the request got), success or failure, in generation order -- lets a
    # caller show exactly which variation(s) failed and why, not just an
    # aggregate count. Empty only when no image-generation attempt was ever
    # reached (e.g. prompt-crafting itself failed).
    variations: list[GenerateImageVariationResult] = Field(default_factory=list)
