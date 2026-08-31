from __future__ import annotations

from app.core.config import settings

# Extension is derived from the sniffed content type, never from the client's
# filename -- keeps the storage key's extension trustworthy regardless of
# what the upload claims to be.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class InvalidUploadError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def sniff_image_content_type(content: bytes) -> str | None:
    # Real content sniffing from the bytes themselves -- the client's
    # declared Content-Type is never consulted for this decision.
    for prefix, content_type in _MAGIC_PREFIXES:
        if content.startswith(prefix):
            return content_type
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image_upload(content: bytes) -> str:
    if not content:
        raise InvalidUploadError("The uploaded file is empty.")

    if len(content) > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes / (1024 * 1024)
        raise InvalidUploadError(f"Files must be {max_mb:.0f}MB or smaller.")

    content_type = sniff_image_content_type(content)
    if content_type is None:
        raise InvalidUploadError("Only JPEG, PNG, WEBP, and GIF images are supported.")

    return content_type


def extension_for_content_type(content_type: str) -> str:
    return ALLOWED_CONTENT_TYPES.get(content_type, "")
