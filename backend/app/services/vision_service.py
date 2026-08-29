from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from app import settings
from app.providers.qwen_vision_provider import QwenVisionError, QwenVisionProvider
from app.schemas.item import AnalyzeItemResponse, ClothingItem
from app.schemas.outfit import AnalyzeOutfitResponse, DiagnosisDimension
from app.services.image_service import get_uploaded_image_path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
VISION_ITEM_PROMPT_VERSION = "vision_item_v0.2"
VISION_OUTFIT_PROMPT_VERSION = "vision_outfit_v0.2"


class VisionServiceError(RuntimeError):
    pass


class QwenItemObservation(BaseModel):
    category: str = "unknown"
    name: Optional[str] = None
    primary_color: Optional[str] = "unknown"
    pattern: Optional[str] = "unknown"
    silhouette: Optional[str] = "unknown"
    rise: Optional[str] = "unknown"
    length: Optional[str] = "unknown"
    style_tags: List[str] = Field(default_factory=list)
    occasion_tags: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class QwenOutfitObservation(BaseModel):
    overall_summary: str
    strengths: List[str] = Field(default_factory=list)
    main_issues: List[str] = Field(default_factory=list)
    diagnosis_dimensions: List[DiagnosisDimension] = Field(default_factory=list)
    keep_items: List[str] = Field(default_factory=list)
    confidence: float = 0.0


def analyze_item(image_id: str) -> AnalyzeItemResponse:
    image_path = get_uploaded_image_path(image_id)
    if not settings.is_live_ai_enabled():
        return mock_analyze_item(image_id)

    prompt = _read_prompt("vision_item.md")
    try:
        observation = QwenVisionProvider().analyze_json(
            image_path=image_path,
            prompt=prompt,
            prompt_version=VISION_ITEM_PROMPT_VERSION,
            task_type="item_analysis",
            response_model=QwenItemObservation,
        )
    except QwenVisionError as exc:
        raise VisionServiceError(str(exc)) from exc

    item = ClothingItem(
        category=_translate_term(observation.category),
        name=_normalize_item_name(observation),
        primary_color=_translate_term(observation.primary_color),
        pattern=_translate_term(observation.pattern),
        silhouette=_translate_term(observation.silhouette),
        rise=_translate_term(observation.rise),
        length=_translate_term(observation.length),
        style_tags=_translate_list(observation.style_tags),
        occasion_tags=_translate_list(observation.occasion_tags),
    )
    return AnalyzeItemResponse(
        image_id=image_id,
        item=item,
        confidence=_bounded_confidence(observation.confidence),
    )


def analyze_outfit(image_id: str) -> AnalyzeOutfitResponse:
    image_path = get_uploaded_image_path(image_id)
    if not settings.is_live_ai_enabled():
        return mock_analyze_outfit(image_id)

    prompt = _read_prompt("vision_outfit.md")
    try:
        observation = QwenVisionProvider().analyze_json(
            image_path=image_path,
            prompt=prompt,
            prompt_version=VISION_OUTFIT_PROMPT_VERSION,
            task_type="outfit_analysis",
            response_model=QwenOutfitObservation,
        )
    except QwenVisionError as exc:
        raise VisionServiceError(str(exc)) from exc

    return AnalyzeOutfitResponse(
        image_id=image_id,
        overall_summary=_safe_text(observation.overall_summary),
        strengths=_safe_list(observation.strengths),
        main_issues=_safe_list(observation.main_issues),
        diagnosis_dimensions=observation.diagnosis_dimensions,
        keep_items=_safe_list(observation.keep_items),
    )


def mock_analyze_item(image_id: str) -> AnalyzeItemResponse:
    get_uploaded_image_path(image_id)

    item = ClothingItem(
        category="trousers",
        name="深灰色高腰阔腿西装裤",
        primary_color="深灰",
        pattern="纯色",
        silhouette="阔腿",
        rise="高腰",
        length="长款",
        style_tags=["简约", "通勤"],
        occasion_tags=["通勤", "休闲"],
    )
    return AnalyzeItemResponse(image_id=image_id, item=item, confidence=0.93)


def mock_analyze_outfit(image_id: str) -> AnalyzeOutfitResponse:
    get_uploaded_image_path(image_id)

    return AnalyzeOutfitResponse(
        image_id=image_id,
        overall_summary=(
            "这身基础其实不错，上衣偏修身，腰线也能看出来。主要可以优化层次感和视觉重点。"
        ),
        strengths=["上衣贴合度不错", "腰线基本可见", "配色清爽协调"],
        main_issues=["整体层次略少", "基础色较多，视觉重点可以更明确"],
        diagnosis_dimensions=[
            DiagnosisDimension(dimension="配色", status="good", summary="清爽协调"),
            DiagnosisDimension(dimension="场景", status="good", summary="日常合适"),
            DiagnosisDimension(dimension="比例", status="good", summary="腰线基本可见"),
            DiagnosisDimension(dimension="视觉重点", status="warning", summary="略显普通"),
        ],
        keep_items=["上衣", "鞋子"],
    )


def _read_prompt(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def _safe_text(value: object, fallback: str = "unknown") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _safe_list(values: list[str]) -> list[str]:
    cleaned = [_safe_text(value) for value in values if _safe_text(value)]
    return cleaned[:6] or ["unknown"]


TRANSLATION_MAP = {
    "unknown": "未知",
    "none": "未知",
    "null": "未知",
    "shoes": "鞋子",
    "shoe": "鞋子",
    "sneakers": "运动鞋",
    "sneaker": "运动鞋",
    "low-top sneakers": "低帮运动鞋",
    "low top sneakers": "低帮运动鞋",
    "top": "上衣",
    "shirt": "衬衫",
    "t-shirt": "T 恤",
    "trousers": "裤子",
    "pants": "裤子",
    "skirt": "半裙",
    "dress": "连衣裙",
    "jacket": "外套",
    "bag": "包",
    "accessory": "配饰",
    "white": "白色",
    "black": "黑色",
    "pink": "粉色",
    "green": "绿色",
    "blue": "蓝色",
    "gray": "灰色",
    "grey": "灰色",
    "beige": "米色",
    "cream": "米白",
    "pink and white": "粉白色",
    "white and pink": "粉白色",
    "solid": "纯色",
    "stripe": "条纹",
    "striped": "条纹",
    "print": "印花",
    "printed": "印花",
    "plaid": "格纹",
    "colorblock": "拼色",
    "casual": "休闲",
    "daily": "日常",
    "daytime": "日间",
    "street": "街头",
    "streetwear": "街头感",
    "cute": "甜美",
    "playful": "活泼",
    "trendy": "时髦",
    "vintage": "复古",
    "sporty": "运动",
    "asymmetrical": "不对称",
    "fitted": "修身",
    "regular": "常规",
    "low-top": "低帮",
    "high-rise": "高腰",
    "mid-rise": "中腰",
    "low-rise": "低腰",
    "long": "长款",
    "short": "短款",
    "cropped": "短款",
}


def _translate_term(value: object) -> str:
    text = _safe_text(value)
    key = text.lower().replace("_", " ").strip()
    return TRANSLATION_MAP.get(key, text)


def _translate_list(values: list[str]) -> list[str]:
    cleaned = [_translate_term(value) for value in values if _safe_text(value)]
    filtered = [value for value in cleaned if value and value != "未知"]
    return filtered[:6] or ["未知"]


def _normalize_item_name(observation: QwenItemObservation) -> str:
    raw_name = _safe_text(observation.name, "")
    translated_name = _translate_term(raw_name) if raw_name else ""
    if translated_name and translated_name != raw_name:
        color = _translate_term(observation.primary_color)
        if color and color != "未知" and color not in translated_name:
            return f"{color}{translated_name}"
        return translated_name
    if raw_name and not _looks_english(raw_name):
        return raw_name
    return _build_item_name(observation)


def _looks_english(text: str) -> bool:
    compact = text.replace(" ", "").replace("-", "")
    if not compact:
        return False
    letters = sum(1 for char in compact if "a" <= char.lower() <= "z")
    return letters >= len(compact) * 0.5


def _bounded_confidence(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _build_item_name(observation: QwenItemObservation) -> str:
    parts = [
        _translate_term(observation.primary_color),
        _translate_term(observation.rise),
        _translate_term(observation.silhouette),
        _translate_term(observation.category),
    ]
    return "".join(part for part in parts if part and part not in {"unknown", "未知"}) or "识别到的单品"
