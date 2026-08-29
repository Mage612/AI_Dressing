from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


MAX_VISION_IMAGE_EDGE = 1024
VISION_JPEG_QUALITY = 82
LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    mime_type: str
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    original_size_bytes: int
    processed_size_bytes: int


def preprocess_for_vision(
    image_path: Path,
    max_edge: int = MAX_VISION_IMAGE_EDGE,
    quality: int = VISION_JPEG_QUALITY,
) -> ProcessedImage:
    original_size_bytes = image_path.stat().st_size

    with Image.open(image_path) as source:
        source = ImageOps.exif_transpose(source)
        original_width, original_height = source.size

        if source.mode != "RGB":
            source = source.convert("RGB")

        source.thumbnail((max_edge, max_edge), LANCZOS)
        processed_width, processed_height = source.size

        output = BytesIO()
        source.save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=False,
        )

    content = output.getvalue()
    return ProcessedImage(
        content=content,
        mime_type="image/jpeg",
        original_width=original_width,
        original_height=original_height,
        processed_width=processed_width,
        processed_height=processed_height,
        original_size_bytes=original_size_bytes,
        processed_size_bytes=len(content),
    )
