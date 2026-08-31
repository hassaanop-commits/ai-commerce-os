from __future__ import annotations

import uuid

from sqlalchemy.orm import Session as DBSession

from app.ai.pricing import estimate_cost_usd
from app.ai.providers.base import AIProvider
from app.ai.tools._common import ToolExecutionError, run_text_completion, start_and_call
from app.models import Product
from app.services import ai_runs

# Tools are the framework-agnostic capability layer: they take a db session,
# an organization-scoped product, and an already-resolved AIProvider, and
# know nothing about FastAPI, LangGraph, or MCP. Both today's LangGraph nodes
# and a future MCP tool wrapper call these same functions unchanged.

# Re-exported so existing call sites (app.agents.graphs.product_content)
# keep working unchanged -- ToolExecutionError now lives in _common.py,
# shared with app.ai.tools.product_images.
__all__ = [
    "ToolExecutionError",
    "analyze_product",
    "generate_product_description",
    "generate_product_title",
    "generate_product_tags",
    "generate_product_metadata",
]


def _product_prompt(product: Product) -> str:
    lines = [
        f"Title: {product.title}",
        f"SKU: {product.sku}",
        f"Price: {product.price} {product.currency}" if product.price is not None else "Price: (not set)",
        f"Existing description: {product.description or '(none)'}",
    ]
    return "\n".join(lines)


def analyze_product(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    model: str,
    user_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, str]:
    system = (
        "You are a product cataloging assistant for an e-commerce platform. "
        "Given raw product data, write a short, factual analysis (2-4 sentences) "
        "noting what information is present and what's missing or unclear for a "
        "customer-facing listing. Do not invent facts not present in the input."
    )
    return run_text_completion(
        db,
        organization_id,
        run_type="product_content.analyze",
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type="product",
        related_entity_id=product.id,
        workflow_id=workflow_id,
        system=system,
        prompt=_product_prompt(product),
        output_key="analysis",
    )


def generate_product_description(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    model: str,
    analysis: str | None = None,
    user_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, str]:
    system = (
        "You are a product copywriter for an e-commerce platform. Write a clear, "
        "accurate marketing description (2-4 sentences) for the product described below. "
        "Do not invent specifications, materials, or claims not supported by the input."
    )
    prompt = _product_prompt(product)
    if analysis:
        prompt += f"\n\nAnalysis notes:\n{analysis}"

    return run_text_completion(
        db,
        organization_id,
        run_type="product_content.generate_description",
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type="product",
        related_entity_id=product.id,
        workflow_id=workflow_id,
        system=system,
        prompt=prompt,
        output_key="description",
    )


def generate_product_title(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    model: str,
    analysis: str | None = None,
    description: str | None = None,
    user_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, str]:
    system = (
        "You are a product copywriter for an e-commerce platform. Write ONE concise, "
        "compelling product title (roughly 5-10 words). Respond with only the title "
        "itself -- no quotation marks, no explanation, no alternatives. Do not invent "
        "specifications, materials, or claims not supported by the input."
    )
    prompt = _product_prompt(product)
    if analysis:
        prompt += f"\n\nAnalysis notes:\n{analysis}"
    if description:
        prompt += f"\n\nDescription:\n{description}"

    return run_text_completion(
        db,
        organization_id,
        run_type="product_content.generate_title",
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type="product",
        related_entity_id=product.id,
        workflow_id=workflow_id,
        system=system,
        prompt=prompt,
        output_key="title",
    )


def generate_product_tags(
    db: DBSession,
    organization_id: uuid.UUID,
    product: Product,
    *,
    provider: AIProvider,
    model: str,
    analysis: str | None = None,
    description: str | None = None,
    user_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, list[str]]:
    system = (
        "You are an e-commerce SEO specialist. Given the product details below, list "
        "5-8 short, relevant search tags/keywords a shopper might use to find this "
        "product. Respond with ONLY a comma-separated list of tags -- no numbering, "
        "no explanation, no surrounding text. Do not invent attributes not supported "
        "by the input."
    )
    prompt = _product_prompt(product)
    if analysis:
        prompt += f"\n\nAnalysis notes:\n{analysis}"
    if description:
        prompt += f"\n\nDescription:\n{description}"

    # Not run_text_completion here (unlike the other tools above): that
    # helper stores the provider's raw text verbatim in metadata_, but tags
    # need to be stored as the parsed list itself -- that's what apply_tags
    # and the frontend actually consume -- so this uses the lower-level
    # start_and_call directly to control what gets persisted, the same way
    # generate_product_image controls its own output_metadata.
    run, result = start_and_call(
        db,
        organization_id,
        run_type="product_content.generate_tags",
        provider=provider,
        model=model,
        user_id=user_id,
        related_entity_type="product",
        related_entity_id=product.id,
        workflow_id=workflow_id,
        call=lambda: provider.complete(system=system, prompt=prompt, model=model),
    )

    tags = [tag.strip() for tag in result.text.split(",") if tag.strip()]

    cost = estimate_cost_usd(provider.name, result.model, result.input_tokens, result.output_tokens)
    ai_runs.complete_run(
        db,
        run,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost,
        output_metadata={"tags": tags},
    )
    db.commit()

    return run.id, tags


def generate_product_metadata(*args, **kwargs) -> tuple[uuid.UUID, str]:
    # Deliberately still a stub: unlike title/tags, "metadata" has no agreed
    # shape yet (SEO meta description? structured attributes? something
    # else?) -- implementing it now would mean inventing a schema nobody
    # asked for. Flagged in the Betterment audit as a future candidate once
    # there's a concrete shape to build against.
    raise NotImplementedError("Metadata generation is not implemented yet (planned for a later phase).")
