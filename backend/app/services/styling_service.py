import json
from pathlib import Path
from typing import Any, Optional, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app import settings
from app.providers.deepseek_provider import DeepSeekError, DeepSeekProvider
from app.schemas.item import (
    ClothingItem,
    ItemRecommendation,
    GenerateRecommendationImageRequest,
    GenerateRecommendationImageResponse,
    RecommendationItem,
    RecommendItemRequest,
    RecommendItemResponse,
    UserConstraints,
)
from app.schemas.outfit import (
    ConversationState,
    DiagnosisDimension,
    RefineOutfitRequest,
    RefineOutfitResponse,
    RefinePlan,
    ReviewOutfitRequest,
    ReviewOutfitResponse,
)
from app.services.image_service import get_uploaded_image_path, get_uploaded_image_url_path
from app.services.image_generation_jobs import (
    get_image_generation_job,
    start_image_generation_job,
)
from app.services.styling_constraint_validator import (
    ConstraintValidationError,
    validate_item_recommendations,
    validate_refine_plans,
)
from app.services.styling_context_loader import load_styling_context
from app.services.vision_service import analyze_item, analyze_outfit


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

REFERENCE_IMAGES = {
    "safe": "https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&w=900&q=80",
    "recommended": "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&w=900&q=80",
    "expressive": "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=900&q=80",
    "outfit_after": "https://images.unsplash.com/photo-1483985988355-763728e1935-763728e1935b?auto=format&fit=crop&w=900&q=80",
}


class StylingServiceError(RuntimeError):
    pass


class StylingService(Protocol):
    def recommend_item(self, request: RecommendItemRequest) -> RecommendItemResponse:
        ...

    def refine_outfit(self, request: RefineOutfitRequest) -> RefineOutfitResponse:
        ...


class DeepSeekItemOutput(BaseModel):
    recommendations: list[ItemRecommendation] = Field(default_factory=list)


class DeepSeekRefineOutput(BaseModel):
    overall_summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    main_issues: list[str] = Field(default_factory=list)
    diagnosis_dimensions: list[DiagnosisDimension] = Field(default_factory=list)
    keep_items: list[str] = Field(default_factory=list)
    plans: list[RefinePlan] = Field(default_factory=list)


class MockStylingService:
    def recommend_item(self, request: RecommendItemRequest) -> RecommendItemResponse:
        session_id = str(uuid4())
        fixed_item, _vision_json = _item_context(request)
        constraints = UserConstraints(
            occasion=request.occasion,
            desired_style=request.desired_style,
            free_text_constraints=request.free_text_constraints or "",
        )
        fixed_name = fixed_item.name
        wants_short_top = _wants_short_top(
            request.free_text_constraints or "",
            _session_list(request.session_state, "available_items"),
        )
        safe_top = "浅色短款衬衫或短袖短上衣。" if wants_short_top else "浅色衬衫或短款针织上衣。"
        recommended_top = "短款酒红色针织或合身短上衣。"
        expressive_top = "白色短T或短款衬衫。"

        recommendations = [
            ItemRecommendation(
                plan_id="item-safe-001",
                strategy="safe",
                strategy_label="最稳妥",
                title="清爽通勤",
                occasion_summary="适合上班、见客户和日常出门。",
                tags=["通勤", "简洁", "低风险"],
                items=[
                    RecommendationItem(type="固定单品", description=f"保留{fixed_name}。"),
                    RecommendationItem(type="上衣", description=safe_top),
                    RecommendationItem(type="鞋子", description="黑色乐福鞋或干净的平底鞋。"),
                    RecommendationItem(type="外套", description="浅灰西装外套，可选。"),
                ],
                reason="这套以你上传的单品为核心，其他单品尽量克制，整体更稳、更容易直接穿出门。",
                image_url=REFERENCE_IMAGES["safe"],
                image_instruction="以固定单品作为画面核心，生成清爽通勤风参考图。",
            ),
            ItemRecommendation(
                plan_id="item-recommended-001",
                strategy="recommended",
                strategy_label="AI推荐",
                title="柔和提亮",
                occasion_summary="适合日常通勤，也比基础搭配更有精神。",
                tags=["平衡", "显气色", "好执行"],
                items=[
                    RecommendationItem(type="固定单品", description=f"保留{fixed_name}。"),
                    RecommendationItem(type="上衣", description=recommended_top),
                    RecommendationItem(type="鞋子", description="黑色平底尖头鞋。"),
                    RecommendationItem(type="配饰", description="小号黑色肩背包。"),
                ],
                reason="小面积暖色能提亮整体，但不会抢走固定单品的主线，通勤场景也不夸张。",
                image_url=REFERENCE_IMAGES["recommended"],
                image_instruction="保留固定单品，用小面积暖色做视觉重点。",
            ),
            ItemRecommendation(
                plan_id="item-expressive-001",
                strategy="expressive",
                strategy_label="更有风格",
                title="松弛城市感",
                occasion_summary="适合周末、约朋友或轻松出门。",
                tags=["休闲", "有层次", "松弛"],
                items=[
                    RecommendationItem(type="固定单品", description=f"保留{fixed_name}。"),
                    RecommendationItem(type="上衣", description=expressive_top),
                    RecommendationItem(type="鞋子", description="干净白色运动鞋。"),
                    RecommendationItem(type="外套", description="短夹克或薄针织披肩。"),
                ],
                reason="通过短上衣和运动鞋改变风格表达，让固定单品变得更轻松，但不会重新换掉它。",
                image_url=REFERENCE_IMAGES["expressive"],
                image_instruction="保留固定单品，生成更休闲的城市感参考。",
            ),
        ]

        validate_item_recommendations(
            recommendations,
            fixed_item=fixed_item,
            unavailable_items=_session_list(request.session_state, "unavailable_items"),
            free_text_constraints=request.free_text_constraints or "",
        )
        return RecommendItemResponse(
            session_id=session_id,
            fixed_item=fixed_item,
            user_constraints=constraints,
            recommendations=recommendations,
        )

    def refine_outfit(self, request: RefineOutfitRequest) -> RefineOutfitResponse:
        before_image = get_uploaded_image_url_path(request.image_id)
        state = _update_session_state(request.conversation_state, request.free_text_constraints or "")
        adjustable_target = "鞋子" if "上衣" in state.locked_items else "上衣"
        recommended_from = "普通休闲鞋" if adjustable_target == "鞋子" else "现有修身无袖上衣"
        recommended_to = "黑色平底尖头鞋" if adjustable_target == "鞋子" else "保持修身上衣，外搭短款薄外套"
        minimal_action = "替换" if adjustable_target == "鞋子" else "调整穿法"
        minimal_from = "厚重鞋型" if adjustable_target == "鞋子" else "自然垂放"
        minimal_to = "轻便平底鞋" if adjustable_target == "鞋子" else "前摆轻塞"

        plans = [
            RefinePlan(
                plan_id="outfit-recommended-001",
                plan_type="recommended",
                title="AI最推荐",
                summary="只改一个影响最大的地方，其余尽量保留原来的感觉。",
                change_budget="替换1件核心单品，可选调整1处穿法",
                changes=[
                    {"target": adjustable_target, "action": "调整", "from": recommended_from, "to": recommended_to, "reason": "现有上衣已经偏修身，也有腰线；这里主要增加层次和视觉重心，不把问题夸大。"},
                ],
                before_image=before_image,
                after_image=REFERENCE_IMAGES["outfit_after"],
                image_instruction="Phase 4 前仅使用占位图。",
            ),
            RefinePlan(
                plan_id="outfit-minimal-001",
                plan_type="minimal",
                title="少改就更好",
                summary="尽量不新增单品，优先调整穿法。",
                change_budget="不新增配饰，最多替换1件",
                changes=[
                    {"target": adjustable_target, "action": minimal_action, "from": minimal_from, "to": minimal_to, "reason": "改动很小，但能让比例和完成度更清楚。"},
                ],
                before_image=before_image,
                after_image=REFERENCE_IMAGES["safe"],
                image_instruction="Phase 4 前仅使用占位图。",
            ),
            RefinePlan(
                plan_id="outfit-expressive-001",
                plan_type="expressive",
                title="更出彩",
                summary="增加一点颜色或材质对比，但不把整套搭配推翻。",
                change_budget="最多替换2件核心单品，新增1件配饰",
                changes=[
                    {"target": adjustable_target, "action": "替换风格", "from": minimal_from, "to": "更有线条感的版本", "reason": "能增加一点风格表达，同时不改变已锁定的部分。"},
                ],
                before_image=before_image,
                after_image=REFERENCE_IMAGES["recommended"],
                image_instruction="Phase 4 前仅使用占位图。",
            ),
        ]
        validate_refine_plans(plans, state=state)

        return RefineOutfitResponse(
            session_id=str(uuid4()),
            image_id=request.image_id,
            conversation_state=state,
            overall_summary="这身已经比较协调：上衣偏修身，腰线也能看出来。主要可以优化的是层次感和视觉重心。",
            strengths=["上衣贴合度不错，腰线并不弱。", "黑色上衣和灰色长裙的颜色关系比较稳。"],
            main_issues=["整体层次略少。", "视觉重点可以再明确一点。"],
            diagnosis_dimensions=[
                DiagnosisDimension(dimension="color", status="good", summary="配色中性实用。"),
                DiagnosisDimension(dimension="proportion", status="good", summary="上衣修身，腰线已经可见。"),
                DiagnosisDimension(dimension="visual_focus", status="warning", summary="可以增加一个小面积重点。"),
            ],
            keep_items=["鞋子"],
            plans=plans,
        )


class DeepSeekStylingService:
    def __init__(self) -> None:
        self.provider = DeepSeekProvider()

    def smoke_test(self) -> dict[str, Any]:
        context = load_styling_context()
        output, metadata = self.provider.generate_json(
            system_prompt="Return JSON only.",
            user_prompt='Return {"ok": true}.',
            task_type="styling_smoke_test",
            prompt_version=settings.STYLING_PROMPT_VERSION,
            skill_version=context.skill_version,
            response_model=SmokeOutput,
            session_id=str(uuid4()),
        )
        return {"ok": output.ok, **metadata}

    def recommend_item(self, request: RecommendItemRequest) -> RecommendItemResponse:
        session_id = _session_id(request.session_state)
        fixed_item, vision_json = _item_context(request)
        constraints = UserConstraints(
            occasion=request.occasion,
            desired_style=request.desired_style,
            free_text_constraints=request.free_text_constraints or "",
        )
        state = request.session_state or {}
        context = load_styling_context()
        output = self._generate_with_constraint_retry(
            task_type="recommend_item",
            response_model=DeepSeekItemOutput,
            system_prompt=_system_prompt(context.skill_yaml, context.knowledge_markdown),
            user_prompt=_item_user_prompt(request, vision_json, state),
            skill_version=context.skill_version,
            session_id=session_id,
            validator=lambda result: validate_item_recommendations(
                result.recommendations,
                fixed_item=fixed_item,
                unavailable_items=_session_list(state, "unavailable_items"),
                free_text_constraints=request.free_text_constraints or "",
            ),
        )
        return RecommendItemResponse(
            session_id=session_id,
            fixed_item=fixed_item,
            user_constraints=constraints,
            recommendations=output.recommendations,
        )

    def refine_outfit(self, request: RefineOutfitRequest) -> RefineOutfitResponse:
        session_id = str(uuid4())
        before_image = get_uploaded_image_url_path(request.image_id)
        observation = analyze_outfit(request.image_id)
        state = _update_session_state(request.conversation_state, request.free_text_constraints or "")
        context = load_styling_context()
        output = self._generate_with_constraint_retry(
            task_type="refine_outfit",
            response_model=DeepSeekRefineOutput,
            system_prompt=_system_prompt(context.skill_yaml, context.knowledge_markdown),
            user_prompt=_outfit_user_prompt(request, observation.dict(), state.dict(), before_image),
            skill_version=context.skill_version,
            session_id=session_id,
            validator=lambda result: validate_refine_plans(result.plans, state=state),
        )
        for plan in output.plans:
            plan.before_image = plan.before_image or before_image
            plan.after_image = plan.after_image or REFERENCE_IMAGES["outfit_after"]
        return RefineOutfitResponse(
            session_id=session_id,
            image_id=request.image_id,
            conversation_state=state,
            overall_summary=output.overall_summary,
            strengths=output.strengths[:2],
            main_issues=output.main_issues[:2],
            diagnosis_dimensions=output.diagnosis_dimensions,
            keep_items=output.keep_items,
            plans=output.plans,
        )

    def _generate_with_constraint_retry(
        self,
        *,
        task_type: str,
        response_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        skill_version: str,
        session_id: str,
        validator,
    ):
        last_error: Exception | None = None
        prompt = user_prompt
        for attempt in range(2):
            result, _metadata = self.provider.generate_json(
                system_prompt=system_prompt,
                user_prompt=prompt,
                task_type=task_type,
                prompt_version=settings.STYLING_PROMPT_VERSION,
                skill_version=skill_version,
                response_model=response_model,
                session_id=session_id,
            )
            try:
                validator(result)
                _print_validation_debug(
                    session_id=session_id,
                    metadata=_metadata,
                    skill_version=skill_version,
                    validation_result="ok",
                )
                return result
            except ConstraintValidationError as exc:
                _print_validation_debug(
                    session_id=session_id,
                    metadata=_metadata,
                    skill_version=skill_version,
                    validation_result="failed",
                )
                last_error = exc
                if attempt >= 1:
                    break
                prompt = prompt + f"\n\nBackend constraint validation failed: {exc}. Regenerate JSON once."
        raise StylingServiceError(f"Styling constraint validation failed: {last_error}")


class SmokeOutput(BaseModel):
    ok: bool


def get_styling_service() -> StylingService:
    if settings.is_live_styling_enabled():
        return DeepSeekStylingService()
    return MockStylingService()


def recommend_item(request: RecommendItemRequest) -> RecommendItemResponse:
    return get_styling_service().recommend_item(request)


def refine_outfit(request: RefineOutfitRequest) -> RefineOutfitResponse:
    return get_styling_service().refine_outfit(request)


def generate_recommendation_image(
    request: GenerateRecommendationImageRequest,
) -> GenerateRecommendationImageResponse:
    if not settings.is_live_image_enabled():
        return GenerateRecommendationImageResponse(
            plan_id=request.recommendation.plan_id,
            image_url=request.recommendation.image_url,
            image_status="failed",
            error="AI_IMAGE_MODE is not live.",
        )
    reference_image_path = (
        get_uploaded_image_path(request.image_id) if request.image_id else None
    )
    job = start_image_generation_job(
        plan_id=request.recommendation.plan_id,
        fallback_image_url=request.recommendation.image_url,
        prompt=_build_item_image_prompt(
            request.recommendation,
            request.fixed_item,
            has_reference_image=reference_image_path is not None,
        ),
        task_type="item_outfit_image_generation",
        prompt_version=settings.STYLING_PROMPT_VERSION,
        session_id=request.session_id,
        recommendation_id=request.recommendation.plan_id,
        reference_image_path=reference_image_path,
    )

    return GenerateRecommendationImageResponse(
        plan_id=job.plan_id,
        image_url=job.image_url,
        image_status=job.status,
        error=job.error,
        job_id=job.job_id,
    )


def get_recommendation_image(job_id: str) -> GenerateRecommendationImageResponse:
    job = get_image_generation_job(job_id)
    if job is None:
        raise StylingServiceError("Image generation job was not found.")
    return GenerateRecommendationImageResponse(
        plan_id=job.plan_id,
        image_url=job.image_url,
        image_status=job.status,
        error=job.error,
        job_id=job.job_id,
    )


def smoke_test_deepseek() -> dict[str, Any]:
    return DeepSeekStylingService().smoke_test()


def review_outfit(request: ReviewOutfitRequest) -> ReviewOutfitResponse:
    original_image = get_uploaded_image_url_path(request.original_image_id)
    reviewed_image = get_uploaded_image_url_path(request.reviewed_image_id)
    return ReviewOutfitResponse(
        review_id=str(uuid4()),
        original_image_id=request.original_image_id,
        reviewed_image_id=request.reviewed_image_id,
        overall_result="The revised outfit is clearer, with better proportion and focus.",
        improved_points=["The waist line reads more clearly.", "The outfit has a stronger focal point."],
        remaining_issues=["Shoe and bag choices could still be tuned for the exact occasion."],
        comparison_dimensions=[
            {"dimension": "proportion", "result": "improved", "summary": "The lower-body line is cleaner."},
            {"dimension": "color", "result": "improved", "summary": "The palette feels more intentional."},
        ],
        next_recommendation="Next, adjust only one accessory or shoe choice.",
        original_image=original_image,
        reviewed_image=reviewed_image,
    )


def _system_prompt(skill_yaml: str, knowledge_markdown: str) -> str:
    return (
        "You are the backend styling engine for AIDressing. "
        "Return exactly one compact JSON object and no Markdown.\n\n"
        "Core policy:\n"
        "- User hard constraints beat aesthetics.\n"
        "- Keep fixed_item unchanged in every plan.\n"
        "- Do not use unsupported body judgments, aesthetic scores, or absolute body rules.\n"
        "- Prefer practical, wearable, low-change suggestions.\n"
        "- If the outfit is already good, phrase issues as light optimizations.\n"
        "- Keep all user-facing text in Simplified Chinese.\n"
        "- Keep output concise: tags <= 3 per plan, items <= 5 per plan, "
        "item descriptions <= 28 Chinese chars, reasons <= 80 Chinese chars, "
        "image_instruction <= 80 Chinese chars."
    )


def _item_user_prompt(request: RecommendItemRequest, vision_json: dict[str, Any], state: dict[str, Any]) -> str:
    template = _read_prompt("styling_item.md")
    payload = {
        "vision_observation": vision_json,
        "user_profile": request.user_profile or {},
        "session_state": state,
        "current_user_request": {
            "occasion": request.occasion,
            "desired_style": request.desired_style,
            "free_text_constraints": request.free_text_constraints or "",
            "fixed_item": (request.fixed_item.dict() if request.fixed_item else vision_json.get("item")),
        },
    }
    return template + "\n\nInput JSON:\n" + json.dumps(payload, ensure_ascii=False)


def _outfit_user_prompt(
    request: RefineOutfitRequest,
    vision_json: dict[str, Any],
    state: dict[str, Any],
    before_image: str,
) -> str:
    template = _read_prompt("styling_outfit.md")
    payload = {
        "vision_observation": vision_json,
        "session_state": state,
        "current_user_request": {
            "free_text_constraints": request.free_text_constraints or "",
            "before_image": before_image,
        },
    }
    return template + "\n\nInput JSON:\n" + json.dumps(payload, ensure_ascii=False)


def _read_prompt(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def _item_context(request: RecommendItemRequest) -> tuple[ClothingItem, dict[str, Any]]:
    if request.fixed_item is not None:
        return request.fixed_item, {
            "image_id": request.image_id,
            "item": _model_to_dict(request.fixed_item),
            "confidence": 1.0,
        }

    analyzed = analyze_item(request.image_id)
    return analyzed.item, _analysis_to_dict(request.image_id, analyzed)


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _analysis_to_dict(image_id: str, analyzed: Any) -> dict[str, Any]:
    if hasattr(analyzed, "model_dump") or hasattr(analyzed, "dict"):
        return _model_to_dict(analyzed)
    return {
        "image_id": getattr(analyzed, "image_id", image_id),
        "item": _model_to_dict(analyzed.item),
        "confidence": getattr(analyzed, "confidence", 1.0),
    }


def _session_id(state: Optional[dict[str, Any]]) -> str:
    if state and state.get("session_id"):
        return str(state["session_id"])
    return str(uuid4())


def _session_list(state: Optional[dict[str, Any]], key: str) -> list[str]:
    if not state:
        return []
    value = state.get(key, [])
    return value if isinstance(value, list) else []


def _wants_short_top(text: str, available_items: list[str]) -> bool:
    combined = " ".join([text, *available_items])
    return "短上衣" in combined or "短款上衣" in combined or "cropped top" in combined.lower()


def _update_session_state(state: ConversationState, text: str) -> ConversationState:
    if hasattr(state, "model_copy"):
        updated = state.model_copy(deep=True)
    else:
        updated = state.copy(deep=True)
    lowered = text.lower()
    if "no heels" in lowered or "high heel" in lowered or "高跟" in text:
        _append_unique(updated.comfort_constraints, "no high heels")
    if "没有" in text or "only have" in lowered or "只有" in text:
        updated.user_notes = ((updated.user_notes or "") + " " + text).strip()
    if "不要换" in text or "keep" in lowered or "lock" in lowered:
        updated.user_notes = ((updated.user_notes or "") + " " + text).strip()
    return updated


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _build_item_image_prompt(
    recommendation: ItemRecommendation,
    fixed_item: ClothingItem,
    has_reference_image: bool = False,
) -> str:
    item_lines = "\n".join(f"- {item.type}: {item.description}" for item in recommendation.items)
    anchor_lines = "\n".join(
        [
            f"- name: {fixed_item.name}",
            f"- category: {fixed_item.category}",
            f"- primary color: {fixed_item.primary_color}",
            f"- pattern/texture: {fixed_item.pattern}",
            f"- silhouette: {fixed_item.silhouette}",
            f"- rise/waistline: {fixed_item.rise}",
            f"- length: {fixed_item.length}",
            f"- style tags: {', '.join(fixed_item.style_tags[:4])}",
            f"- occasion tags: {', '.join(fixed_item.occasion_tags[:4])}",
        ]
    )
    reference_policy = (
        "A reference image is attached. Use the attached image as the source of truth for the fixed anchor item.\n"
        "Preserve the exact visible garment category, cut, seam structure, neckline/waistline, hem length, drape, material texture, color, pattern, hardware, and styling details of the anchor item.\n"
        "Do not reinterpret the anchor item from the text summary if it conflicts with the image; the image wins.\n"
        "Do not change the anchor item's gender expression or make it more masculine/feminine than the reference.\n"
        "Only add or adjust the complementary outfit pieces described below.\n"
        if has_reference_image
        else
        "No reference image is attached. Follow the fixed anchor item structured description conservatively.\n"
    )
    return (
        "Create a vertical full-body fashion outfit reference photo for a mobile styling app.\n"
        "The image must show a realistic adult fashion model wearing the described outfit.\n"
        "Do not create a question mark, punctuation mark, sculpture, logo, typography, poster, or text.\n"
        "No watermark. No Chinese characters. No floating symbols.\n"
        f"{reference_policy}"
        "The uploaded fixed anchor item is mandatory and must remain visually recognizable.\n"
        "Do not change the fixed anchor item into another garment category, color family, pattern, length, waistline, or silhouette.\n"
        "Preserve the anchor item's visible garment type, main color, pattern/texture, rise/waistline, length, fabric feel, and silhouette as closely as possible from the structured description.\n"
        "Treat the fixed anchor item as the most important visual constraint, more important than styling creativity.\n"
        "If exact details are unknown, choose a conservative plain version instead of inventing decorations, prints, logos, or dramatic cuts.\n"
        "Use a clean lifestyle photography look, natural daylight, simple urban or studio background.\n"
        "The clothing must be the focus and must be clearly visible from head to toe.\n"
        f"Fixed anchor item structured description:\n{anchor_lines}\n"
        f"Outfit plan title: {recommendation.title}.\n"
        f"Occasion: {recommendation.occasion_summary}.\n"
        f"Items to wear:\n{item_lines}\n"
        f"Styling reason: {recommendation.reason}.\n"
        f"Extra image direction: {recommendation.image_instruction}.\n"
        "Output should look like an e-commerce/editorial outfit photo, not abstract art."
    )


def _print_validation_debug(
    *,
    session_id: str,
    metadata: dict[str, Any],
    skill_version: str,
    validation_result: str,
) -> None:
    if not settings.STYLING_DEBUG:
        return
    print(
        "[styling-debug] "
        f"session_id={session_id} run_id={metadata.get('run_id')} "
        f"model={metadata.get('model')} prompt_version={settings.STYLING_PROMPT_VERSION} "
        f"skill_version={skill_version} latency_ms={metadata.get('latency_ms')} "
        f"input_tokens={metadata.get('input_tokens')} "
        f"output_tokens={metadata.get('output_tokens')} "
        f"validation={validation_result}"
    )
