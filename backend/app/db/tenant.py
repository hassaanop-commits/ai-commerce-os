from __future__ import annotations

import uuid
from typing import TypeVar

from sqlalchemy import Select, select

ModelT = TypeVar("ModelT")


def org_scoped(model: type[ModelT], organization_id: uuid.UUID) -> Select:
    # Every organization-owned query should build on this instead of querying the
    # model directly, so the tenant filter can never be left out by mistake.
    return select(model).where(model.organization_id == organization_id)
