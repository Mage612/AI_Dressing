from pydantic import BaseModel


class UploadResponse(BaseModel):
    success: bool
    image_id: str
    image_url: str
