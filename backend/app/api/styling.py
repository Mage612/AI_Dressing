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
    AnalyzeOutfitJobResponse,
    AnalyzeOutfitRequest,
    AnalyzeOutfitResponse,
    GenerateOutfitImageRequest,
    GenerateOutfitImageResponse,
    RefineOutfitRequest,
    RefineOutfitJobResponse,
    RefineOutfitResponse,
    ReviewOutfitRequest,
    ReviewOutfitResponse,
)
from app.services import styling_service, vision_service
from app.services.image_service import ImageNotFoundError, InvalidImageIdError
from app.services.vision_service import VisionServiceError
from app.services.styling_service import StylingServiceError
from app.services.image_generation_jobs import ImageGenerationLimitError
from app.services.outfit_workflow_jobs import (
    get_outfit_workflow_job,
    start_analysis_job,
    start_refinement_job,
)


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
    except ImageGenerationLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
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


@router.post("/analyze-outfit-job", response_model=AnalyzeOutfitJobResponse)
def create_analyze_outfit_job(request: AnalyzeOutfitRequest) -> AnalyzeOutfitJobResponse:
    job = start_analysis_job(request.image_id)
    return AnalyzeOutfitJobResponse(job_id=job.job_id, status="pending")


@router.get("/analyze-outfit-job/{job_id}", response_model=AnalyzeOutfitJobResponse)
def get_analyze_outfit_job(job_id: str) -> AnalyzeOutfitJobResponse:
    job = get_outfit_workflow_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Outfit analysis job was not found.")
    return AnalyzeOutfitJobResponse(
        job_id=job.job_id,
        status=job.status,
        result=job.result,
        error=job.error,
    )


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


@router.post("/refine-outfit-job", response_model=RefineOutfitJobResponse)
def create_refine_outfit_job(request: RefineOutfitRequest) -> RefineOutfitJobResponse:
    job = start_refinement_job(request)
    return RefineOutfitJobResponse(job_id=job.job_id, status="pending")


@router.get("/refine-outfit-job/{job_id}", response_model=RefineOutfitJobResponse)
def get_refine_outfit_job(job_id: str) -> RefineOutfitJobResponse:
    job = get_outfit_workflow_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Outfit refinement job was not found.")
    return RefineOutfitJobResponse(
        job_id=job.job_id,
        status=job.status,
        result=job.result,
        error=job.error,
    )


@router.post("/outfit-refinement-image", response_model=GenerateOutfitImageResponse)
def generate_outfit_refinement_image(
    request: GenerateOutfitImageRequest,
) -> GenerateOutfitImageResponse:
    try:
        return styling_service.generate_outfit_refinement_image(request)
    except (InvalidImageIdError, ImageNotFoundError) as exc:
        _raise_api_error(exc)
    except ImageGenerationLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except StylingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/outfit-refinement-image/{job_id}",
    response_model=GenerateOutfitImageResponse,
)
def get_outfit_refinement_image(job_id: str) -> GenerateOutfitImageResponse:
    try:
        return styling_service.get_outfit_refinement_image(job_id)
    except StylingServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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
