import httpx
import pytest
from pydantic import BaseModel

from app.providers.deepseek_provider import DeepSeekError, DeepSeekProvider
from app.schemas.item import ClothingItem, ItemRecommendation, RecommendationItem
from app.schemas.outfit import ConversationState, RefinePlan
from app.services.styling_constraint_validator import (
    ConstraintValidationError,
    validate_item_recommendations,
    validate_refine_plans,
)
from app.services.styling_context_loader import load_styling_context
from app.services.styling_service import MockStylingService


def _fixed_item() -> ClothingItem:
    return ClothingItem(
        category="pants",
        name="dark gray wide-leg trousers",
        primary_color="dark gray",
        pattern="solid",
        silhouette="wide-leg",
        rise="high-rise",
        length="long",
    )


def _recommendation(strategy: str, shoe: str = "black flat shoes") -> ItemRecommendation:
    return ItemRecommendation(
        plan_id=f"item-{strategy}-001",
        strategy=strategy,
        strategy_label=strategy,
        title=f"{strategy} plan",
        occasion_summary="commute",
        tags=[strategy],
        items=[
            RecommendationItem(type="fixed item", description="Keep dark gray wide-leg trousers."),
            RecommendationItem(type="shoes", description=shoe),
        ],
        reason="The dark gray wide-leg trousers remain the anchor.",
        image_url="placeholder",
        image_instruction="placeholder",
    )


def test_styling_context_loader_reads_skill_and_knowledge() -> None:
    context = load_styling_context()

    assert context.skill_yaml
    assert context.knowledge_markdown
    assert context.skill_version.startswith("v")


def test_recommend_item_validator_accepts_three_valid_plans() -> None:
    plans = [_recommendation("safe"), _recommendation("recommended"), _recommendation("expressive")]

    validate_item_recommendations(plans, fixed_item=_fixed_item())

    assert all(plan.constraint_check["passed"] for plan in plans)


def test_fixed_item_cannot_be_replaced_or_omitted() -> None:
    plans = [_recommendation("safe"), _recommendation("recommended"), _recommendation("expressive")]
    plans[1].items[0].description = "Replace with a skirt."
    plans[1].reason = "Use a skirt instead."

    with pytest.raises(ConstraintValidationError):
        validate_item_recommendations(plans, fixed_item=_fixed_item())


def test_no_high_heel_constraint_is_validated() -> None:
    plans = [_recommendation("safe"), _recommendation("recommended", "high heels"), _recommendation("expressive")]

    with pytest.raises(ConstraintValidationError):
        validate_item_recommendations(
            plans,
            fixed_item=_fixed_item(),
            free_text_constraints="no high heels",
        )


def test_unavailable_item_is_validated() -> None:
    plans = [_recommendation("safe"), _recommendation("recommended"), _recommendation("expressive")]
    plans[2].items.append(RecommendationItem(type="bag", description="burgundy bag"))

    with pytest.raises(ConstraintValidationError):
        validate_item_recommendations(
            plans,
            fixed_item=_fixed_item(),
            unavailable_items=["burgundy bag"],
        )


def _plan(plan_type: str, changes: list[dict]) -> RefinePlan:
    return RefinePlan(
        plan_id=f"outfit-{plan_type}-001",
        plan_type=plan_type,
        title=plan_type,
        summary="summary",
        change_budget="budget",
        changes=changes,
        before_image="before",
        after_image="after",
    )


def test_refine_outfit_validator_accepts_three_plan_types() -> None:
    plans = [
        _plan("recommended", [{"target": "top", "action": "replace", "from": "old", "to": "new", "reason": "why"}]),
        _plan("minimal", [{"target": "top", "action": "adjust", "from": "old", "to": "new", "reason": "why"}]),
        _plan("expressive", [{"target": "top", "action": "replace", "from": "old", "to": "blue", "reason": "why"}]),
    ]

    validate_refine_plans(plans, state=ConversationState())

    assert all(plan.constraint_check["passed"] for plan in plans)


def test_minimal_plan_change_budget_is_validated() -> None:
    plans = [
        _plan("recommended", []),
        _plan("minimal", [
            {"target": "top", "action": "replace", "from": "old", "to": "new", "reason": "why"},
            {"target": "shoes", "action": "replace", "from": "old", "to": "new", "reason": "why"},
        ]),
        _plan("expressive", []),
    ]

    with pytest.raises(ConstraintValidationError):
        validate_refine_plans(plans, state=ConversationState())


def test_recommended_plan_allows_only_one_replacement() -> None:
    plans = [
        _plan("recommended", [
            {"target": "top", "action": "replace", "from": "old", "to": "new", "reason": "why"},
            {"target": "shoes", "action": "replace", "from": "old", "to": "new", "reason": "why"},
        ]),
        _plan("minimal", []),
        _plan("expressive", []),
    ]

    with pytest.raises(ConstraintValidationError):
        validate_refine_plans(plans, state=ConversationState())


def test_locked_item_is_validated() -> None:
    plans = [
        _plan("recommended", [{"target": "pants", "action": "replace", "from": "pants", "to": "skirt", "reason": "why"}]),
        _plan("minimal", []),
        _plan("expressive", []),
    ]

    with pytest.raises(ConstraintValidationError):
        validate_refine_plans(plans, state=ConversationState(locked_items=["pants"]))


class TinyOutput(BaseModel):
    ok: bool


def test_deepseek_json_parse_failure_is_reported(monkeypatch) -> None:
    provider = DeepSeekProvider.__new__(DeepSeekProvider)
    provider.model = "deepseek-v4-flash"

    def fake_request(**kwargs):
        return "not json", {"run_id": "run-1"}

    monkeypatch.setattr(provider, "_request", fake_request)

    with pytest.raises(DeepSeekError):
        provider.generate_json(
            system_prompt="system",
            user_prompt="user",
            task_type="test",
            prompt_version="v0.1",
            skill_version="v0.1",
            response_model=TinyOutput,
            session_id="session-1",
        )


def test_deepseek_timeout_is_reported(monkeypatch) -> None:
    provider = DeepSeekProvider.__new__(DeepSeekProvider)
    provider.model = "deepseek-v4-flash"

    def fake_request(**kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(provider, "_request", fake_request)

    with pytest.raises(DeepSeekError):
        provider.generate_json(
            system_prompt="system",
            user_prompt="user",
            task_type="test",
            prompt_version="v0.1",
            skill_version="v0.1",
            response_model=TinyOutput,
            session_id="session-1",
        )


def test_mock_recommend_item_respects_short_top_constraint(monkeypatch) -> None:
    from app.services import styling_service

    class FakeAnalyze:
        item = _fixed_item()

    monkeypatch.setattr(styling_service, "analyze_item", lambda image_id: FakeAnalyze())

    response = MockStylingService().recommend_item(
        styling_service.RecommendItemRequest(
            image_id="image-1",
            free_text_constraints="我只有短上衣，不想穿高跟鞋",
            session_state={"available_items": ["短上衣"]},
        )
    )

    text = " ".join(
        item.description
        for plan in response.recommendations
        for item in plan.items
        if item.type == "上衣"
    )
    item_text = " ".join(
        item.description
        for plan in response.recommendations
        for item in plan.items
    )
    assert "短" in text
    assert "高跟" not in item_text


def test_mock_recommend_item_uses_provided_fixed_item_without_reanalyzing(monkeypatch) -> None:
    from app.services import styling_service

    def fail_analyze(image_id):
        raise AssertionError("analyze_item should not be called when fixed_item is provided")

    monkeypatch.setattr(styling_service, "analyze_item", fail_analyze)

    response = MockStylingService().recommend_item(
        styling_service.RecommendItemRequest(
            image_id="image-1",
            fixed_item=_fixed_item(),
            free_text_constraints="no high heels",
        )
    )

    assert response.fixed_item == _fixed_item()
    assert len(response.recommendations) == 3
