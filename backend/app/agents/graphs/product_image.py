from __future__ import annotations

import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session as DBSession

from app.agents.state import ProductImageState
from app.ai.providers.base import AIProvider
from app.ai.tools import product_images as tools
from app.ai.tools._common import ToolExecutionError
from app.services.products import get_product
from app.services.storage import StorageService

# The vertical-slice graph for Phase I: Product -> craft an image-generation
# prompt (text provider) -> generate the image (image provider). Two
# separate providers are deliberate -- Anthropic (text) doesn't do image
# generation, and OpenAI's image endpoint isn't wired for text completions
# here, so each node resolves its own provider rather than sharing one.
# Nodes are closures over `db`/providers/`storage` (built fresh per
# invocation by app.agents.runner), never fields on the state.


def build_graph(
    db: DBSession,
    *,
    text_provider: AIProvider,
    text_model: str,
    image_provider: AIProvider,
    image_model: str,
    storage: StorageService,
    image_size: str = tools.DEFAULT_IMAGE_SIZE,
):
    def _ids(state: ProductImageState) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None, uuid.UUID]:
        org_id = uuid.UUID(state["organization_id"])
        product_id = uuid.UUID(state["product_id"])
        user_id = uuid.UUID(state["user_id"]) if state["user_id"] else None
        workflow_id = uuid.UUID(state["workflow_id"])
        return org_id, product_id, user_id, workflow_id

    def craft_prompt_node(state: ProductImageState) -> dict:
        org_id, product_id, user_id, workflow_id = _ids(state)
        product = get_product(db, org_id, product_id)
        try:
            run_id, image_prompt = tools.generate_image_prompt(
                db,
                org_id,
                product,
                provider=text_provider,
                model=text_model,
                user_prompt=state["user_prompt"],
                user_id=user_id,
                workflow_id=workflow_id,
            )
        except ToolExecutionError as exc:
            return {"status": "failed", "error_category": exc.category, "ai_run_ids": [str(exc.run_id)]}
        return {"image_prompt": image_prompt, "ai_run_ids": [str(run_id)]}

    def generate_image_node(state: ProductImageState) -> dict:
        org_id, product_id, user_id, workflow_id = _ids(state)
        product = get_product(db, org_id, product_id)
        try:
            run_id, asset = tools.generate_product_image(
                db,
                org_id,
                product,
                provider=image_provider,
                model=image_model,
                image_prompt=state["image_prompt"] or "",
                storage=storage,
                user_id=user_id,
                workflow_id=workflow_id,
                size=image_size,
            )
        except ToolExecutionError as exc:
            return {"status": "failed", "error_category": exc.category, "ai_run_ids": [str(exc.run_id)]}
        return {
            "product_asset_id": str(asset.id),
            "status": "succeeded",
            "ai_run_ids": [str(run_id)],
        }

    def _route_after_craft_prompt(state: ProductImageState) -> str:
        return "failed" if state["status"] == "failed" else "continue"

    graph = StateGraph(ProductImageState)
    graph.add_node("craft_prompt", craft_prompt_node)
    graph.add_node("generate_image", generate_image_node)
    graph.set_entry_point("craft_prompt")
    graph.add_conditional_edges(
        "craft_prompt", _route_after_craft_prompt, {"failed": END, "continue": "generate_image"}
    )
    graph.add_edge("generate_image", END)
    return graph.compile()
