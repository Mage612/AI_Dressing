from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeItemRequest(BaseModel):
    image_id: str


class ClothingItem(BaseModel):
    category: str
    name: str
    primary_color: str
    pattern: str
    silhouette: str
    rise: str
    length: str
    style_tags: List[str] = Field(default_factory=list)
    occasion_tags: List[str] = Field(default_factory=list)


class AnalyzeItemResponse(BaseModel):
    image_id: str
    item: ClothingItem
    confidence: float


class RecommendItemRequest(BaseModel):
    image_id: str
    occasion: str = "不限"
    desired_style: str = "AI 推荐"
    free_text_constraints: Optional[str] = ""
    fixed_item: Optional[ClothingItem] = None
    session_state: Optional[dict[str, Any]] = None
    user_profile: Optional[dict[str, Any]] = None


class UserConstraints(BaseModel):
    occasion: str
    desired_style: str
    free_text_constraints: str = ""


class RecommendationItem(BaseModel):
    type: str
    description: str


class ItemRecommendation(BaseModel):
    plan_id: str
    strategy: Literal["safe", "recommended", "expressive"]
    strategy_label: str
    title: str
    occasion_summary: str
    tags: List[str] = Field(default_factory=list)
    items: List[RecommendationItem] = Field(default_factory=list)
    reason: str
    image_url: str
    image_instruction: str = ""
    constraint_check: dict[str, Any] = Field(default_factory=dict)


class RecommendItemResponse(BaseModel):
    session_id: str
    fixed_item: ClothingItem
    user_constraints: UserConstraints
    recommendations: List[ItemRecommendation]


class GenerateRecommendationImageRequest(BaseModel):
    session_id: str
    recommendation: ItemRecommendation
    fixed_item: ClothingItem
    image_id: Optional[str] = None
    visitor_id: Optional[str] = Field(default=None, max_length=100)


class GenerateRecommendationImageResponse(BaseModel):
    plan_id: str
    image_url: str
    image_status: Literal["pending", "generated", "failed"]
    error: Optional[str] = ""
    job_id: Optional[str] = ""
    cached: bool = False
    remaining_daily_generations: Optional[int] = None
