from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

# Deliberately plain, JSON-serializable data only -- no ORM objects, no
# database Session. Node functions receive `db` and the resolved AIProvider
# as closures built by the runner, not through this state, so this shape
# stays compatible with LangGraph's own (unused, for now) checkpointing.


class ProductContentState(TypedDict):
    organization_id: str
    user_id: str | None
    product_id: str
    workflow_id: str
    ai_run_ids: Annotated[list[str], operator.add]
    analysis: str | None
    generated_description: str | None
    generated_title: str | None
    generated_tags: list[str] | None
    status: Literal["running", "succeeded", "failed"]
    error_category: str | None


class ProductImageState(TypedDict):
    organization_id: str
    user_id: str | None
    product_id: str
    workflow_id: str
    ai_run_ids: Annotated[list[str], operator.add]
    user_prompt: str
    image_prompt: str | None
    product_asset_id: str | None
    status: Literal["running", "succeeded", "failed"]
    error_category: str | None
