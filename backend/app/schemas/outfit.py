from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AnalyzeOutfitRequest(BaseModel):
    image_id: str


class DiagnosisDimension(BaseModel):
    dimension: str
    status: Literal["good", "warning", "issue"]
    summary: str


class AnalyzeOutfitResponse(BaseModel):
    image_id: str
    overall_summary: str
    strengths: List[str] = Field(default_factory=list)
    main_issues: List[str] = Field(default_factory=list)
    diagnosis_dimensions: List[DiagnosisDimension] = Field(default_factory=list)
    keep_items: List[str] = Field(default_factory=list)


class ConversationState(BaseModel):
    locked_items: List[str] = Field(default_factory=list)
    unavailable_items: List[str] = Field(default_factory=list)
    available_items: List[str] = Field(default_factory=list)
    style_constraints: List[str] = Field(default_factory=list)
    color_constraints: List[str] = Field(default_factory=list)
    occasion_constraints: List[str] = Field(default_factory=list)
    comfort_constraints: List[str] = Field(default_factory=list)
    current_plan_id: Optional[str] = ""
    current_recommendation_version: int = 0
    # Backward compatibility: disliked in the current recommendation, not banned.
    rejected_items: List[str] = Field(default_factory=list)
    user_notes: Optional[str] = ""


class RefineOutfitRequest(BaseModel):
    image_id: str
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    free_text_constraints: Optional[str] = ""


class OutfitChange(BaseModel):
    target: str
    action: str
    from_: str = Field(..., alias="from")
    to: str
    reason: str


class RefinePlan(BaseModel):
    plan_id: str
    plan_type: Literal["recommended", "minimal", "expressive"]
    title: str
    summary: str
    change_budget: str
    changes: List[OutfitChange] = Field(default_factory=list)
    before_image: str
    after_image: str
    image_instruction: str = ""
    constraint_check: dict = Field(default_factory=dict)


class RefineOutfitResponse(BaseModel):
    session_id: str
    image_id: str
    conversation_state: ConversationState
    overall_summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    main_issues: List[str] = Field(default_factory=list)
    diagnosis_dimensions: List[DiagnosisDimension] = Field(default_factory=list)
    keep_items: List[str] = Field(default_factory=list)
    plans: List[RefinePlan] = Field(default_factory=list)


class ReviewOutfitRequest(BaseModel):
    original_image_id: str
    reviewed_image_id: str
    plan_id: Optional[str] = ""
    free_text_feedback: Optional[str] = ""


class ReviewDimension(BaseModel):
    dimension: str
    result: Literal["improved", "unchanged", "needs_work"]
    summary: str


class ReviewOutfitResponse(BaseModel):
    review_id: str
    original_image_id: str
    reviewed_image_id: str
    overall_result: str
    improved_points: List[str] = Field(default_factory=list)
    remaining_issues: List[str] = Field(default_factory=list)
    comparison_dimensions: List[ReviewDimension] = Field(default_factory=list)
    next_recommendation: str
    original_image: str
    reviewed_image: str
