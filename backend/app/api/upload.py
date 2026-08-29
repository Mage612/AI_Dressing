from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.schemas.upload import UploadResponse
from app.settings import MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.services.image_service import (
    detect_image_extension,
    validate_image_upload,
)


router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_image(request: Request, file: UploadFile = File(...)) -> UploadResponse:
    content = await file.read(MAX_UPLOAD_BYTES + 1)

    try:
        extension = validate_image_upload(file.filename or "", content)
    except ValueError as exc:
        message = str(exc)
        if "too large" in message:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Image must be 10 MB or smaller.",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only jpg, jpeg, png, and webp images are supported.",
        ) from exc

    detected_extension = detect_image_extension(content)
    if detected_extension is not None:
        extension = detected_extension

    image_id = str(uuid4())
    stored_filename = f"{image_id}.{extension}"
    output_path = Path(UPLOAD_DIR) / stored_filename
    output_path.write_bytes(content)

    image_url = str(request.url_for("uploads", path=stored_filename))
    return UploadResponse(success=True, image_id=image_id, image_url=image_url)
