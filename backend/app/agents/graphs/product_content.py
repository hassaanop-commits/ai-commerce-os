from __future__ import annotations

import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session as DBSession

from app.agents.state import ProductContentState
from app.ai.providers.base import AIProvider
from app.ai.tools import product_content as tools
from app.ai.tools.product_content import ToolExecutionError
from app.services.products import get_product

# The vertical-slice graph for product content: Product -> analyze ->
# generate description -> generate title -> generate tags. Nodes are
# closures over `db`/`provider`/the per-task models (built fresh per
# invocation by app.agents.runner) rather than fields on the state, so
# state itself stays plain and JSON-serializable.
#
# Each step short-circuits the rest on failure (same conditional-edge
# pattern repeated at each step) rather than letting title/tags run against
# a workflow that's already failed -- consistent with the original
# analyze -> generate_description behavior, just applied at every step now.


def build_graph(
    db: DBSession,
    provider: AIProvider,
    *,
    analysis_model: str,
    description_model: str,
    title_model: str,
    tags_model: str,
):
    def _ids(state: ProductContentState) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None, uuid.UUID]:
        org_id = uuid.UUID(state["organization_id"])
        product_id = uuid.UUID(state["product_id"])
        user_id = uuid.UUID(state["user_id"]) if state["user_id"] else None
        workflow_id = uuid.UUID(state["workflow_id"])
        return org_id, product_id, user_id, workflow_id

    def analyze_node(state: ProductContentState) -> dict:
        org_id, product_id, user_id, workflow_id = _ids(state)
        product = get_product(db, org_id, product_id)
        try:
            run_id, analysis = tools.analyze_product(
                db,
                org_id,
                product,
                provider=provider,
                model=analysis_model,
                user_id=user_id,
                workflow_id=workflow_id,
            )
        except ToolExecutionError as exc:
            return {"status": "failed", "error_category": exc.category, "ai_run_ids": [str(exc.run_id)]}
        return {"analysis": analysis, "ai_run_ids": [str(run_id)]}

    def generate_description_node(state: ProductContentState) -> dict:
        org_id, product_id, user_id, workflow_id = _ids(state)
        product = get_product(db, org_id, product_id)
        try:
            run_id, description = tools.generate_product_description(
                db,
                org_id,
                product,
                provider=provider,
                model=description_model,
                analysis=state.get("analysis"),
                user_id=user_id,
                workflow_id=workflow_id,
            )
        except ToolExecutionError as exc:
            return {"status": "failed", "error_category": exc.category, "ai_run_ids": [str(exc.run_id)]}
        return {"generated_description": description, "ai_run_ids": [str(run_id)]}

    def generate_title_node(state: ProductContentState) -> dict:
        org_id, product_id, user_id, workflow_id = _ids(state)
        product = get_product(db, org_id, product_id)
        try:
            run_id, title = tools.generate_product_title(
                db,
                org_id,
                product,
                provider=provider,
                model=title_model,
                analysis=state.get("analysis"),
                description=state.get("generated_description"),
                user_id=user_id,
                workflow_id=workflow_id,
            )
        except ToolExecutionError as exc:
            return {"status": "failed", "error_category": exc.category, "ai_run_ids": [str(exc.run_id)]}
        return {"generated_title": title, "ai_run_ids": [str(run_id)]}

    def generate_tags_node(state: ProductContentState) -> dict:
        org_id, product_id, user_id, workflow_id = _ids(state)
        product = get_product(db, org_id, product_id)
        try:
            run_id, tags = tools.generate_product_tags(
                db,
                org_id,
                product,
                provider=provider,
                model=tags_model,
                analysis=state.get("analysis"),
                description=state.get("generated_description"),
                user_id=user_id,
                workflow_id=workflow_id,
            )
        except ToolExecutionError as exc:
            return {"status": "failed", "error_category": exc.category, "ai_run_ids": [str(exc.run_id)]}
        return {"generated_tags": tags, "status": "succeeded", "ai_run_ids": [str(run_id)]}

    def _continue_or_end(state: ProductContentState) -> str:
        return "failed" if state["status"] == "failed" else "continue"

    graph = StateGraph(ProductContentState)
    graph.add_node("analyze", analyze_node)
    graph.add_node("generate_description", generate_description_node)
    graph.add_node("generate_title", generate_title_node)
    graph.add_node("generate_tags", generate_tags_node)
    graph.set_entry_point("analyze")
    graph.add_conditional_edges("analyze", _continue_or_end, {"failed": END, "continue": "generate_description"})
    graph.add_conditional_edges(
        "generate_description", _continue_or_end, {"failed": END, "continue": "generate_title"}
    )
    graph.add_conditional_edges("generate_title", _continue_or_end, {"failed": END, "continue": "generate_tags"})
    graph.add_edge("generate_tags", END)
    return graph.compile()
