from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class StorageService(Protocol):
    def upload(self, key: str, content: bytes, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def read(self, key: str) -> bytes: ...
    def get_url(self, key: str) -> str | None: ...


class LocalStorageProvider:
    """Development storage: files live on local disk under a configured root.

    Keys are opaque strings resolved internally; the resolved path is always
    verified to stay inside the storage root before any read/write/delete,
    which closes off path traversal even if a key were ever malformed --
    defense in depth, since generate_storage_key() never lets client input
    reach a key directly anyway.

    get_url() returns None: local storage has no secure public URL of its
    own, so callers serve files through the authenticated asset route
    instead. A future S3/R2 provider would return a real (signed) URL here,
    and callers already prefer whatever this returns when it's not None.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root or settings.local_storage_path).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError("Invalid storage key.")
        return candidate

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def get_url(self, key: str) -> str | None:
        return None


_default_storage_service: StorageService = LocalStorageProvider()


def get_storage_service() -> StorageService:
    return _default_storage_service


def generate_storage_key(organization_id: uuid.UUID, product_id: uuid.UUID, extension: str) -> str:
    # Always server-generated -- the client's filename never reaches this
    # path, so there's nothing for a path-traversal or arbitrary-write
    # attempt to act on.
    unique = uuid.uuid4().hex
    return f"products/{organization_id}/{product_id}/{unique}{extension}"
