"""Shared entity-image storage (UI/UX Evolution milestone — Entity Media
Foundation). One save/delete implementation reused by the Company logo,
Partner (customer/vendor) image, and Product image endpoints — not three
separate ones. Local disk only (see settings.py's `media_root` docstring
for why); this module is the single place that would change if storage
ever moves to an object store.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from src.shared.config.settings import get_settings

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class InvalidImageError(ValueError):
    pass


async def save_entity_image(file: UploadFile, *, entity_type: str, entity_id: str) -> str:
    """Validates and stores an uploaded image, returning the relative path
    to persist on the entity's `*_path` column. Never a full URL — the API
    layer builds that from the request, so the stored value stays portable
    across environments (dev/staging/prod each have a different origin).
    """
    content_type = file.content_type or ""
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise InvalidImageError(
            f"Unsupported image type: {content_type or 'unknown'}. Allowed: JPEG, PNG, WEBP."
        )

    settings = get_settings()
    contents = await file.read()
    if len(contents) == 0:
        raise InvalidImageError("Uploaded file is empty.")
    if len(contents) > settings.media_max_bytes:
        max_mb = settings.media_max_bytes / (1024 * 1024)
        raise InvalidImageError(f"Image exceeds the {max_mb:.0f}MB limit.")

    # entity_type is always one of a small set of literals we control at
    # each call site (never user input); entity_id is always a UUID the
    # route already parsed via FastAPI's path-param typing — neither can
    # carry a path-traversal segment.
    relative_dir = Path(entity_type) / entity_id
    absolute_dir = Path(settings.media_root) / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{extension}"
    (absolute_dir / filename).write_bytes(contents)

    return str(relative_dir / filename).replace("\\", "/")


def delete_entity_image(relative_path: str | None) -> None:
    """Best-effort delete — a missing file is not an error. The database
    column is the source of truth for whether an entity "has" an image;
    disk cleanup failing is a cheap thing to accept, not a reason to fail
    the request."""
    if not relative_path:
        return
    settings = get_settings()
    try:
        (Path(settings.media_root) / relative_path).unlink(missing_ok=True)
    except OSError:
        pass


def build_media_url(relative_path: str | None) -> str | None:
    """Relative-path-on-disk -> the URL the frontend actually loads
    (served by the /media StaticFiles mount in api/main.py)."""
    if not relative_path:
        return None
    return f"/media/{relative_path}"
