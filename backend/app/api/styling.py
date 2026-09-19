from fastapi import APIRouter, HTTPException, status

from app.schemas.item import (
    AnalyzeItemRequest,
    AnalyzeItemResponse,
    GenerateRecommendationImageRequest,
    GenerateRecommendationImageResponse,
    RecommendItemRequest,
    RecommendItemResponse,
)
from app.schemas.outfit import (
    AnalyzeOutfitRequest,
    AnalyzeOutfitResponse,
    RefineOutfitRequest,
    RefineOutfitResponse,
    ReviewOutfitRequest,
    ReviewOutfitResponse,
)
from app.services import styling_service, vision_service
from app.services.image_service import ImageNotFoundError, InvalidImageIdError
from app.services.vision_service import VisionServiceError
from app.services.styling_service import StylingServiceError


router = APIRouter(tags=["styling"])


def _raise_api_error(exc: Exception) -> None:
    if isinstance(exc, InvalidImageIdError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image_id.",
        ) from exc

    if isinstance(exc, ImageNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Uploaded image was not found.",
        ) from exc

    raise exc


@router.post("/analyze-item", response_model=AnalyzeItemResponse)
def analyze_item(request: AnalyzeItemRequest) -> AnalyzeItemResponse:
    try:
        return vision_service.analyze_item(request.image_id)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
    except VisionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/recommend-item", response_model=RecommendItemResponse)
def recommend_item(request: RecommendItemRequest) -> RecommendItemResponse:
    try:
        return styling_service.recommend_item(request)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
    except StylingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/recommendation-image", response_model=GenerateRecommendationImageResponse)
def generate_recommendation_image(
    request: GenerateRecommendationImageRequest,
) -> GenerateRecommendationImageResponse:
    try:
        return styling_service.generate_recommendation_image(request)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
    except StylingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/recommendation-image/{job_id}",
    response_model=GenerateRecommendationImageResponse,
)
def get_recommendation_image(job_id: str) -> GenerateRecommendationImageResponse:
    try:
        return styling_service.get_recommendation_image(job_id)
    except StylingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/analyze-outfit", response_model=AnalyzeOutfitResponse)
def analyze_outfit(request: AnalyzeOutfitRequest) -> AnalyzeOutfitResponse:
    try:
        return vision_service.analyze_outfit(request.image_id)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
    except VisionServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/refine-outfit", response_model=RefineOutfitResponse)
def refine_outfit(request: RefineOutfitRequest) -> RefineOutfitResponse:
    try:
        return styling_service.refine_outfit(request)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
    except StylingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/styling/smoke-test")
def styling_smoke_test() -> dict:
    try:
        return styling_service.smoke_test_deepseek()
    except (RuntimeError, StylingServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/review-outfit", response_model=ReviewOutfitResponse)
def review_outfit(request: ReviewOutfitRequest) -> ReviewOutfitResponse:
    try:
        return styling_service.review_outfit(request)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
