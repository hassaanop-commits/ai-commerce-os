from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session as DBSession

from app.agents.graphs.product_content import build_graph as build_product_content_graph
from app.agents.graphs.product_image import build_graph as build_product_image_graph
from app.agents.state import ProductContentState, ProductImageState
from app.ai.providers.base import AIProvider
from app.ai.tools import product_images as image_tools
from app.ai.tools._common import ToolExecutionError
from app.ai.tools.product_images import DEFAULT_IMAGE_SIZE
from app.models import Product
from app.services.storage import StorageService

# Model tiers -- see the Betterment Phase Day 1 audit. Lightweight/utility
# tasks (analysis, image-prompt crafting) use the cheap/fast tier;
# customer-facing content generation uses the mid tier. These are also the
# fallback default for any provider without a specific entry below.
UTILITY_MODEL = "claude-haiku-4-5-20251001"
CONTENT_MODEL = "claude-sonnet-5"
DEFAULT_IMAGE_MODEL = "gpt-image-1"

# Provider-specific defaults for the two text-task tiers. A model string
# that one provider understands is usually meaningless to another (a Claude
# model ID sent to Gemini's API would just fail), so the default can't be a
# single constant shared across every provider -- it has to be resolved
# against whichever provider is actually active. This is the one place that
# resolution happens; the graph nodes and tools stay exactly as
# provider-agnostic as before, always taking a plain `model: str`.
#
# Anything not listed here (including "mock", which accepts any string)
# falls back to UTILITY_MODEL/CONTENT_MODEL above -- deliberately, so
# MockProvider's behavior in existing tests is unchanged by this table.
_UTILITY_MODEL_BY_PROVIDER: dict[str, str] = {
    "anthropic": UTILITY_MODEL,
    "gemini": "gemini-2.5-flash",
}
_CONTENT_MODEL_BY_PROVIDER: dict[str, str] = {
    "anthropic": CONTENT_MODEL,
    "gemini": "gemini-2.5-flash",
}


def default_utility_model(provider_name: str) -> str:
    return _UTILITY_MODEL_BY_PROVIDER.get(provider_name, UTILITY_MODEL)


def default_content_model(provider_name: str) -> str:
    return _CONTENT_MODEL_BY_PROVIDER.get(provider_name, CONTENT_MODEL)


@dataclass
class ProductContentWorkflowResult:
    workflow_id: uuid.UUID
    ai_run_ids: list[uuid.UUID]
    analysis: str | None
    generated_description: str | None
    generated_title: str | None
    generated_tags: list[str] | None
    status: str
    error_category: str | None


def run_product_content_workflow(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    user_id: uuid.UUID | None,
    analysis_model: str | None = None,
    description_model: str | None = None,
    title_model: str | None = None,
    tags_model: str | None = None,
) -> ProductContentWorkflowResult:
    # Title and tags are short, low-ambiguity outputs -- same utility tier
    # as analysis, not the content tier used for the description itself.
    analysis_model = analysis_model or default_utility_model(provider.name)
    description_model = description_model or default_content_model(provider.name)
    title_model = title_model or default_utility_model(provider.name)
    tags_model = tags_model or default_utility_model(provider.name)
    workflow_id = uuid.uuid4()

    graph = build_product_content_graph(
        db,
        provider,
        analysis_model=analysis_model,
        description_model=description_model,
        title_model=title_model,
        tags_model=tags_model,
    )
    initial_state: ProductContentState = {
        "organization_id": str(organization_id),
        "user_id": str(user_id) if user_id else None,
        "product_id": str(product.id),
        "workflow_id": str(workflow_id),
        "ai_run_ids": [],
        "analysis": None,
        "generated_description": None,
        "generated_title": None,
        "generated_tags": None,
        "status": "running",
        "error_category": None,
    }

    final_state = graph.invoke(initial_state)

    return ProductContentWorkflowResult(
        workflow_id=workflow_id,
        ai_run_ids=[uuid.UUID(r) for r in final_state["ai_run_ids"]],
        analysis=final_state.get("analysis"),
        generated_description=final_state.get("generated_description"),
        generated_title=final_state.get("generated_title"),
        generated_tags=final_state.get("generated_tags"),
        status=final_state["status"],
        error_category=final_state.get("error_category"),
    )


@dataclass
class VariationOutcome:
    """The outcome of one attempted image (one provider call). `index` is
    the 0-based slot number in generation order -- stable and assigned once,
    regardless of how many of the other slots succeeded or failed. Exactly
    one of (asset_id, error_category) is set, matching the "never fake a
    successful generation" rule: a failed slot never gets a placeholder
    asset, and a succeeded slot never carries a leftover error category.
    """

    index: int
    status: Literal["succeeded", "failed"]
    ai_run_id: uuid.UUID
    asset_id: uuid.UUID | None
    error_category: str | None


@dataclass
class ProductImageWorkflowResult:
    workflow_id: uuid.UUID
    ai_run_ids: list[uuid.UUID]
    image_prompt: str | None
    product_asset_id: uuid.UUID | None
    product_asset_ids: list[uuid.UUID]
    status: str
    error_category: str | None
    # Per-slot detail for every image attempt (0, 1, or N of them depending
    # on how far the workflow got) -- empty only when no image-generation
    # attempt was ever reached at all (e.g. craft_prompt itself failed).
    variations: list[VariationOutcome] = field(default_factory=list)


def run_product_image_workflow(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    user_prompt: str,
    text_provider: AIProvider,
    image_provider: AIProvider,
    storage: StorageService,
    user_id: uuid.UUID | None,
    text_model: str | None = None,
    image_model: str = DEFAULT_IMAGE_MODEL,
    image_size: str = DEFAULT_IMAGE_SIZE,
    variations: int = 1,
) -> ProductImageWorkflowResult:
    text_model = text_model or default_utility_model(text_provider.name)
    workflow_id = uuid.uuid4()

    # The single-image path keeps using the LangGraph graph unchanged (it's
    # the well-tested, exact behavior existing callers rely on). Multiple
    # variations is handled as a thin loop over the same tool functions the
    # graph nodes themselves call (app.ai.tools.product_images) rather than
    # reshaping the graph to be N-image-aware -- see the Phase II audit notes
    # in the final report for why this was the safer seam to extend.
    if variations <= 1:
        graph = build_product_image_graph(
            db,
            text_provider=text_provider,
            text_model=text_model,
            image_provider=image_provider,
            image_model=image_model,
            storage=storage,
            image_size=image_size,
        )
        initial_state: ProductImageState = {
            "organization_id": str(organization_id),
            "user_id": str(user_id) if user_id else None,
            "product_id": str(product.id),
            "workflow_id": str(workflow_id),
            "ai_run_ids": [],
            "user_prompt": user_prompt,
            "image_prompt": None,
            "product_asset_id": None,
            "status": "running",
            "error_category": None,
        }

        final_state = graph.invoke(initial_state)
        product_asset_id = final_state.get("product_asset_id")
        asset_ids = [uuid.UUID(product_asset_id)] if product_asset_id else []
        final_run_ids = [uuid.UUID(r) for r in final_state["ai_run_ids"]]

        # image_prompt is only ever set once craft_prompt has succeeded (see
        # product_image.py's craft_prompt_node) -- if it's still None here,
        # craft_prompt itself failed and generate_image was never reached, so
        # there is no image-generation attempt to report as a variation slot
        # at all (not even a failed one).
        variation_outcomes: list[VariationOutcome] = []
        if final_state.get("image_prompt") is not None:
            # craft_prompt appends its run id first, then generate_image
            # appends its own -- the last id in the accumulated list is
            # always the single generate_image attempt's run, whether it
            # succeeded or failed.
            variation_outcomes.append(
                VariationOutcome(
                    index=0,
                    status="succeeded" if asset_ids else "failed",
                    ai_run_id=final_run_ids[-1],
                    asset_id=asset_ids[0] if asset_ids else None,
                    error_category=None if asset_ids else final_state.get("error_category"),
                )
            )

        return ProductImageWorkflowResult(
            workflow_id=workflow_id,
            ai_run_ids=final_run_ids,
            image_prompt=final_state.get("image_prompt"),
            product_asset_id=asset_ids[0] if asset_ids else None,
            product_asset_ids=asset_ids,
            status=final_state["status"],
            error_category=final_state.get("error_category"),
            variations=variation_outcomes,
        )

    ai_run_ids: list[uuid.UUID] = []

    try:
        craft_run_id, image_prompt = image_tools.generate_image_prompt(
            db,
            organization_id,
            product,
            provider=text_provider,
            model=text_model,
            user_prompt=user_prompt,
            user_id=user_id,
            workflow_id=workflow_id,
        )
    except ToolExecutionError as exc:
        # craft_prompt itself failed -- no image-generation attempt was ever
        # made, so `variations` stays empty (there is nothing to report per
        # slot, not even a failed one).
        return ProductImageWorkflowResult(
            workflow_id=workflow_id,
            ai_run_ids=[exc.run_id],
            image_prompt=None,
            product_asset_id=None,
            product_asset_ids=[],
            status="failed",
            error_category=exc.category,
        )
    ai_run_ids.append(craft_run_id)

    asset_ids: list[uuid.UUID] = []
    variation_outcomes: list[VariationOutcome] = []
    last_error_category: str | None = None
    for index in range(variations):
        try:
            run_id, asset = image_tools.generate_product_image(
                db,
                organization_id,
                product,
                provider=image_provider,
                model=image_model,
                image_prompt=image_prompt,
                storage=storage,
                user_id=user_id,
                workflow_id=workflow_id,
                size=image_size,
            )
        except ToolExecutionError as exc:
            # One variation failing doesn't abort the rest -- each is an
            # independent provider call/AIRun. "Do not fake successful image
            # generation" means a failed variation simply contributes no
            # asset, not a placeholder; the failure is still visible in
            # ai_run_ids (the run is recorded failed) and in this slot's own
            # VariationOutcome, not just folded into a single last-failure-wins
            # category like `error_category` below.
            ai_run_ids.append(exc.run_id)
            last_error_category = exc.category
            variation_outcomes.append(
                VariationOutcome(
                    index=index, status="failed", ai_run_id=exc.run_id, asset_id=None, error_category=exc.category
                )
            )
            continue
        ai_run_ids.append(run_id)
        asset_ids.append(asset.id)
        variation_outcomes.append(
            VariationOutcome(index=index, status="succeeded", ai_run_id=run_id, asset_id=asset.id, error_category=None)
        )

    status = "succeeded" if asset_ids else "failed"
    return ProductImageWorkflowResult(
        workflow_id=workflow_id,
        ai_run_ids=ai_run_ids,
        image_prompt=image_prompt,
        product_asset_id=asset_ids[0] if asset_ids else None,
        product_asset_ids=asset_ids,
        status=status,
        error_category=None if asset_ids else last_error_category,
        variations=variation_outcomes,
    )


def run_product_image_regeneration(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    image_prompt: str,
    image_provider: AIProvider,
    storage: StorageService,
    user_id: uuid.UUID | None,
    derived_from_asset_id: uuid.UUID,
    image_model: str = DEFAULT_IMAGE_MODEL,
    image_size: str = DEFAULT_IMAGE_SIZE,
) -> ProductImageWorkflowResult:
    """Regenerate a single new image from an *already-crafted* prompt (reused
    verbatim from the asset being regenerated), skipping the craft_prompt
    step entirely. Own workflow_id, own AIRun, own ProductAsset -- the
    original asset is untouched; the new one links back via
    derived_from_asset_id and starts pending_review like any other
    AI-generated asset (see app.services.product_assets.create_generated_asset).
    """
    workflow_id = uuid.uuid4()

    try:
        run_id, asset = image_tools.generate_product_image(
            db,
            organization_id,
            product,
            provider=image_provider,
            model=image_model,
            image_prompt=image_prompt,
            storage=storage,
            user_id=user_id,
            workflow_id=workflow_id,
            size=image_size,
            derived_from_asset_id=derived_from_asset_id,
        )
    except ToolExecutionError as exc:
        return ProductImageWorkflowResult(
            workflow_id=workflow_id,
            ai_run_ids=[exc.run_id],
            image_prompt=image_prompt,
            product_asset_id=None,
            product_asset_ids=[],
            status="failed",
            error_category=exc.category,
            variations=[
                VariationOutcome(
                    index=0, status="failed", ai_run_id=exc.run_id, asset_id=None, error_category=exc.category
                )
            ],
        )

    return ProductImageWorkflowResult(
        workflow_id=workflow_id,
        ai_run_ids=[run_id],
        image_prompt=image_prompt,
        product_asset_id=asset.id,
        product_asset_ids=[asset.id],
        status="succeeded",
        error_category=None,
        variations=[VariationOutcome(index=0, status="succeeded", ai_run_id=run_id, asset_id=asset.id, error_category=None)],
    )
