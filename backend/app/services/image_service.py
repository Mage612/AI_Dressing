from pathlib import Path
from typing import Optional
from uuid import UUID

from app.settings import MAX_UPLOAD_BYTES, UPLOAD_DIR

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


class InvalidImageIdError(ValueError):
    pass


class ImageNotFoundError(FileNotFoundError):
    pass


def normalize_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def detect_image_extension(content: bytes) -> Optional[str]:
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_upload(filename: str, content: bytes) -> str:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is too large.")

    extension = normalize_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported image extension.")

    detected_extension = detect_image_extension(content)
    if detected_extension is None:
        raise ValueError("Unsupported image content.")

    if extension in {"jpg", "jpeg"} and detected_extension == "jpg":
        return "jpg"

    if extension != detected_extension:
        raise ValueError("Image extension does not match content.")

    return extension


def get_uploaded_image_path(image_id: str) -> Path:
    try:
        UUID(image_id)
    except ValueError as exc:
        raise InvalidImageIdError("Invalid image_id.") from exc

    upload_root = UPLOAD_DIR.resolve()
    matches = sorted(UPLOAD_DIR.glob(f"{image_id}.*"))
    if not matches:
        raise ImageNotFoundError("Uploaded image was not found.")

    image_path = matches[0].resolve()
    if image_path.suffix.lower().lstrip(".") not in ALLOWED_EXTENSIONS:
        raise ImageNotFoundError("Uploaded image was not found.")
    if upload_root not in image_path.parents:
        raise InvalidImageIdError("Invalid image_id.")

    return image_path


def get_uploaded_image_url_path(image_id: str) -> str:
    image_path = get_uploaded_image_path(image_id)
    return f"/uploads/{image_path.name}"
