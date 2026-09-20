from typing import Iterable

from app.schemas.item import ClothingItem, ItemRecommendation
from app.schemas.outfit import ConversationState, RefinePlan


class ConstraintValidationError(RuntimeError):
    pass


def validate_item_recommendations(
    recommendations: list[ItemRecommendation],
    *,
    fixed_item: ClothingItem,
    unavailable_items: Iterable[str] = (),
    free_text_constraints: str = "",
) -> None:
    if len(recommendations) != 3:
        raise ConstraintValidationError("recommend-item must return exactly 3 plans.")
    strategies = {item.strategy for item in recommendations}
    if strategies != {"safe", "recommended", "expressive"}:
        raise ConstraintValidationError("recommend-item returned unexpected strategies.")

    blocked = _blocked_terms(unavailable_items, free_text_constraints)
    fixed_terms = _item_terms(fixed_item)
    for recommendation in recommendations:
        text = _recommendation_text(recommendation)
        _ensure_no_blocked_terms(text, blocked)
        if fixed_terms and not any(term in text for term in fixed_terms):
            raise ConstraintValidationError("fixed_item is not reflected in every plan.")
        recommendation.constraint_check = {"passed": True, "validator": "backend"}


def validate_refine_plans(plans: list[RefinePlan], *, state: ConversationState) -> None:
    if len(plans) != 3:
        raise ConstraintValidationError("refine-outfit must return exactly 3 plans.")
    plan_types = {plan.plan_type for plan in plans}
    if plan_types != {"recommended", "minimal", "expressive"}:
        raise ConstraintValidationError("refine-outfit returned unexpected plan types.")

    locked = _normalize_terms(state.locked_items)
    blocked = _normalize_terms([*state.unavailable_items])
    for plan in plans:
        text = _plan_text(plan)
        _ensure_no_blocked_terms(text, blocked)
        for locked_item in locked:
            for change in plan.changes:
                if locked_item and locked_item in _text(change.target, change.from_, change.to):
                    raise ConstraintValidationError("locked_item was modified.")
        added_accessories = [
            change for change in plan.changes
            if _contains_any(change.target, ["accessory", "accessories", "bag", "jewelry", "scarf", "hat", "配饰", "包", "首饰", "帽"])
            and _contains_any(change.action, ["add", "increase", "新增", "增加"])
        ]
        replacements = [
            change for change in plan.changes
            if _contains_any(change.action, ["replace", "swap", "换", "替换"])
        ]
        garment_changes = [
            change for change in plan.changes
            if not _contains_any(
                change.target,
                ["accessory", "accessories", "bag", "jewelry", "scarf", "hat", "配饰", "包", "首饰", "帽"],
            )
        ]
        if plan.plan_type == "recommended" and not garment_changes:
            raise ConstraintValidationError(
                "recommended plan must include a visible garment or styling change; an accessory alone is insufficient."
            )
        replacement_limit = 2 if plan.plan_type == "expressive" else 1
        accessory_limit = 0 if plan.plan_type == "minimal" else 1
        if len(replacements) > replacement_limit:
            raise ConstraintValidationError(
                f"{plan.plan_type} plan replaced more than {replacement_limit} item(s)."
            )
        if len(added_accessories) > accessory_limit:
            raise ConstraintValidationError(
                f"{plan.plan_type} plan added more than {accessory_limit} accessory item(s)."
            )
        plan.constraint_check = {"passed": True, "validator": "backend"}


def _item_terms(item: ClothingItem) -> list[str]:
    return _normalize_terms(
        [item.name, item.category, item.primary_color, item.pattern, item.silhouette, item.rise, item.length]
    )


def _blocked_terms(unavailable_items: Iterable[str], free_text_constraints: str) -> list[str]:
    terms = list(unavailable_items)
    text = free_text_constraints.lower()
    if "高跟" in free_text_constraints or "high heel" in text or "heels" in text:
        terms.extend(["高跟", "high heel", "heels", "heeled"])
    return _normalize_terms(terms)


def _normalize_terms(values: Iterable[str]) -> list[str]:
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _ensure_no_blocked_terms(text: str, blocked_terms: list[str]) -> None:
    lowered = text.lower()
    for term in blocked_terms:
        if term and term in lowered:
            raise ConstraintValidationError(f"blocked term appeared in plan: {term}")


def _recommendation_text(recommendation: ItemRecommendation) -> str:
    return _text(
        recommendation.title,
        recommendation.reason,
        recommendation.occasion_summary,
        recommendation.image_instruction,
        *recommendation.tags,
        *(item.type for item in recommendation.items),
        *(item.description for item in recommendation.items),
    )


def _plan_text(plan: RefinePlan) -> str:
    return _text(
        plan.title,
        plan.summary,
        plan.change_budget,
        plan.image_instruction,
        *(change.target for change in plan.changes),
        *(change.action for change in plan.changes),
        *(change.from_ for change in plan.changes),
        *(change.to for change in plan.changes),
        *(change.reason for change in plan.changes),
    )


def _text(*values: object) -> str:
    return " ".join(str(value) for value in values if value is not None)


def _contains_any(value: str, needles: list[str]) -> bool:
    lowered = value.lower()
    return any(needle in lowered for needle in needles)
