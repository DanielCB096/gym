"""Safe local storage for member progress photos.

The database keeps only metadata; image bytes are written under a random name
inside ``PROGRESS_PHOTOS_DIR`` (default ``./uploads/progress_photos``). The
directory is created with owner-only permissions, files are created
exclusively and the original filename is never reused, so a crafted upload
cannot choose its own path. Production must mount this directory on persistent
storage and include it in backups.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
from uuid import uuid4

MAX_PROGRESS_PHOTO_BYTES = 8 * 1024 * 1024
DEFAULT_PROGRESS_PHOTOS_DIR = "./uploads/progress_photos"

_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_STORAGE_KEY = re.compile(r"[0-9a-f]{32}\.(?:jpg|png|webp)")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class StoredPhoto:
    key: str
    content_type: str
    byte_size: int


def photos_root() -> Path:
    configured = os.getenv("PROGRESS_PHOTOS_DIR", "").strip()
    return Path(configured or DEFAULT_PROGRESS_PHOTOS_DIR).resolve()


def detect_image_type(data: bytes) -> str | None:
    """Return the declared image type confirmed by its magic bytes."""

    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(_PNG_SIGNATURE):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_photo(data: bytes, content_type: str) -> StoredPhoto:
    detected = detect_image_type(data)
    if detected is None:
        raise ValueError("La imagen no es un JPEG, PNG o WebP válido")
    if detected != content_type:
        raise ValueError("El contenido de la imagen no coincide con el tipo declarado")

    root = photos_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = f"{uuid4().hex}{_EXTENSIONS[detected]}"
    path = root / key
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return StoredPhoto(key=key, content_type=detected, byte_size=len(data))


def photo_path(key: str) -> Path:
    if _STORAGE_KEY.fullmatch(key) is None:
        raise ValueError("La clave de almacenamiento no es válida")
    return photos_root() / key


def delete_photo(key: str) -> None:
    photo_path(key).unlink(missing_ok=True)
