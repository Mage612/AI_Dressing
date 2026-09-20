import pytest

from app import settings
from app.providers.qwen_image_provider import QwenImageProvider
from app.schemas.item import (
    ClothingItem,
    GenerateRecommendationImageRequest,
    ItemRecommendation,
    RecommendationItem,
)
from app.schemas.outfit import GenerateOutfitImageRequest, RefinePlan
from app.services.styling_service import (
    _build_item_image_prompt,
    _build_outfit_refinement_image_prompt,
    _image_generation_cache_key,
    _outfit_refinement_cache_key,
)
from app.services import image_generation_jobs


@pytest.fixture(autouse=True)
def isolated_image_generation_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        image_generation_jobs,
        "STATE_PATH",
        tmp_path / "image-generation-state.json",
    )
    monkeypatch.setattr(settings, "IMAGE_VISITOR_DAILY_LIMIT", 2)
    monkeypatch.setattr(settings, "IMAGE_GLOBAL_DAILY_LIMIT", 60)
    image_generation_jobs._jobs.clear()
    image_generation_jobs._jobs_by_cache_key.clear()


def test_qwen_image_endpoint_uses_dashscope_native_generation_path() -> None:
    endpoint = QwenImageProvider._image_endpoint(
        "https://example.com/compatible-mode/v1"
    )

    assert endpoint == "https://example.com/api/v1/services/aigc/image-generation/generation"


def test_qwen_image_async_endpoint_uses_dashscope_native_task_path() -> None:
    endpoint = QwenImageProvider._async_image_endpoint(
        "https://example.com/compatible-mode/v1"
    )

    assert endpoint == "https://example.com/api/v1/services/aigc/text2image/image-synthesis"


def test_qwen_image_task_endpoint_uses_dashscope_native_task_path() -> None:
    endpoint = QwenImageProvider._task_endpoint(
        "https://example.com/compatible-mode/v1",
        "task-1",
    )

    assert endpoint == "https://example.com/api/v1/tasks/task-1"


def test_qwen_image_extracts_multimodal_image_url() -> None:
    data = {
        "output": {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"image": "https://temporary.example.com/result.png"}
                        ]
                    }
                }
            ]
        }
    }

    assert QwenImageProvider._extract_image_url(data) == "https://temporary.example.com/result.png"


def test_image_generation_job_completes(monkeypatch) -> None:
    def fake_start_image_task(self, **kwargs):
        return "task-1"

    def fake_poll_image_task(self, task_id):
        assert task_id == "task-1"
        return "/uploads/generated-test.png"

    monkeypatch.setattr(QwenImageProvider, "start_image_task", fake_start_image_task)
    monkeypatch.setattr(QwenImageProvider, "poll_image_task", fake_poll_image_task)

    job = image_generation_jobs.start_image_generation_job(
        plan_id="plan-1",
        fallback_image_url="/uploads/fallback.png",
        prompt="prompt",
        task_type="test",
        prompt_version="v0.1",
        session_id="session-1",
        recommendation_id="plan-1",
    )

    current = image_generation_jobs.get_image_generation_job(job.job_id)
    assert current is not None
    assert current.status == "generated"
    assert current.image_url == "/uploads/generated-test.png"


def test_image_generation_job_passes_reference_image(monkeypatch, tmp_path) -> None:
    reference_image = tmp_path / "anchor.png"
    reference_image.write_bytes(b"reference")
    captured = {}

    def fake_start_image_task(self, **kwargs):
        captured.update(kwargs)
        return "task-1"

    monkeypatch.setattr(QwenImageProvider, "start_image_task", fake_start_image_task)

    job = image_generation_jobs.start_image_generation_job(
        plan_id="plan-1",
        fallback_image_url="/uploads/fallback.png",
        prompt="prompt",
        task_type="test",
        prompt_version="v0.1",
        session_id="session-1",
        recommendation_id="plan-1",
        reference_image_path=reference_image,
    )

    assert job.external_task_id == "task-1"
    assert captured["reference_image_path"] == reference_image


def test_image_generation_cache_reuses_completed_result(monkeypatch) -> None:
    starts = []

    def fake_start_image_task(self, **kwargs):
        starts.append(kwargs)
        return "task-1"

    monkeypatch.setattr(QwenImageProvider, "start_image_task", fake_start_image_task)
    monkeypatch.setattr(
        QwenImageProvider,
        "poll_image_task",
        lambda self, task_id: "https://example.com/generated.png",
    )

    first = image_generation_jobs.start_image_generation_job(
        plan_id="plan-1",
        fallback_image_url="/uploads/fallback.png",
        prompt="prompt",
        task_type="test",
        prompt_version="v0.1",
        session_id="session-1",
        cache_key="same-plan",
        visitor_id="visitor-1",
    )
    image_generation_jobs.get_image_generation_job(first.job_id)
    second = image_generation_jobs.start_image_generation_job(
        plan_id="plan-1",
        fallback_image_url="/uploads/fallback.png",
        prompt="prompt",
        task_type="test",
        prompt_version="v0.1",
        session_id="session-2",
        cache_key="same-plan",
        visitor_id="visitor-1",
    )

    assert len(starts) == 1
    assert second.status == "generated"
    assert second.cached is True
    assert second.image_url == "https://example.com/generated.png"


def test_image_generation_enforces_visitor_daily_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "IMAGE_VISITOR_DAILY_LIMIT", 1)
    monkeypatch.setattr(
        QwenImageProvider,
        "start_image_task",
        lambda self, **kwargs: "task-1",
    )

    image_generation_jobs.start_image_generation_job(
        plan_id="plan-1",
        fallback_image_url="/uploads/fallback.png",
        prompt="prompt",
        task_type="test",
        prompt_version="v0.1",
        session_id="session-1",
        cache_key="plan-1",
        visitor_id="visitor-1",
    )

    with pytest.raises(image_generation_jobs.ImageGenerationLimitError):
        image_generation_jobs.start_image_generation_job(
            plan_id="plan-2",
            fallback_image_url="/uploads/fallback.png",
            prompt="another prompt",
            task_type="test",
            prompt_version="v0.1",
            session_id="session-1",
            cache_key="plan-2",
            visitor_id="visitor-1",
        )


def test_qwen_image_message_content_includes_reference_image(tmp_path) -> None:
    reference_image = tmp_path / "anchor.png"
    reference_image.write_bytes(b"abc")

    content = QwenImageProvider._message_content(
        prompt="keep this item",
        reference_image_path=reference_image,
    )

    assert content[0]["image"].startswith("data:image/png;base64,")
    assert content[1] == {"text": "keep this item"}


def test_item_image_prompt_includes_fixed_item_visual_attributes() -> None:
    fixed_item = ClothingItem(
        category="裤子",
        name="黑色高腰阔腿裤",
        primary_color="黑色",
        pattern="纯色",
        silhouette="阔腿",
        rise="高腰",
        length="九分",
        style_tags=["通勤", "简约"],
        occasion_tags=["办公"],
    )
    recommendation = ItemRecommendation(
        plan_id="safe",
        strategy="safe",
        strategy_label="稳妥",
        title="黑白通勤",
        occasion_summary="办公室",
        items=[
            RecommendationItem(type="固定单品", description="黑色高腰阔腿裤"),
            RecommendationItem(type="上衣", description="白色衬衫"),
        ],
        reason="保持简洁。",
        image_url="https://example.com/safe.png",
        image_instruction="完整展示裤装比例。",
    )

    prompt = _build_item_image_prompt(recommendation, fixed_item)

    assert "黑色高腰阔腿裤" in prompt
    assert "黑色" in prompt
    assert "阔腿" in prompt
    assert "高腰" in prompt
    assert "九分" in prompt
    assert "must remain visually recognizable" in prompt
    assert "Outfit plan title" not in prompt
    assert "Styling reason" not in prompt
    assert recommendation.image_instruction not in prompt


def test_item_image_prompt_prioritizes_reference_image() -> None:
    fixed_item = ClothingItem(
        category="裤子",
        name="黑色高腰阔腿裤",
        primary_color="黑色",
        pattern="纯色",
        silhouette="阔腿",
        rise="高腰",
        length="九分",
        style_tags=["通勤", "简约"],
        occasion_tags=["办公"],
    )
    recommendation = ItemRecommendation(
        plan_id="safe",
        strategy="safe",
        strategy_label="稳妥",
        title="黑白通勤",
        occasion_summary="办公室",
        items=[
            RecommendationItem(type="固定单品", description="黑色高腰阔腿裤"),
            RecommendationItem(type="上衣", description="白色衬衫"),
        ],
        reason="保持简洁。",
        image_url="https://example.com/safe.png",
        image_instruction="完整展示裤装比例。",
    )

    prompt = _build_item_image_prompt(
        recommendation,
        fixed_item,
        has_reference_image=True,
    )

    assert "A reference image is attached" in prompt
    assert "the image wins" in prompt
    assert "seam structure" in prompt
    assert "material texture" in prompt
    assert "never switch to a different gender presentation" in prompt
    assert "Show exactly one realistic adult fashion model" in prompt
    assert "Do not create an infographic" in prompt
    assert "outfit breakdown" in prompt
    assert "Do not add any cards, panels" in prompt
    assert "Do not add any new letters, numbers, words" in prompt
    assert "preserve only the authentic graphics" in prompt
    assert "complete outfit clearly visible from head to toe" in prompt
    assert "not a graphic design" in prompt
    assert "no written explanation" in prompt


def test_image_cache_key_changes_when_image_prompt_changes(tmp_path) -> None:
    reference_image = tmp_path / "anchor.png"
    reference_image.write_bytes(b"same-reference")
    fixed_item = ClothingItem(
        category="上衣",
        name="白色印花短袖T恤",
        primary_color="白色",
        pattern="数字印花",
        silhouette="修身",
        rise="未知",
        length="常规",
    )
    recommendation = ItemRecommendation(
        plan_id="recommended",
        strategy="recommended",
        strategy_label="推荐",
        title="街头休闲",
        occasion_summary="日常",
        items=[RecommendationItem(type="下装", description="黑色工装短裤")],
        reason="比例协调",
        image_url="/uploads/fallback.png",
        image_instruction="生成海报",
    )
    request = GenerateRecommendationImageRequest(
        session_id="session-1",
        image_id="image-1",
        fixed_item=fixed_item,
        recommendation=recommendation,
    )

    first_key = _image_generation_cache_key(request, reference_image, "prompt-v1")
    second_key = _image_generation_cache_key(request, reference_image, "prompt-v2")

    assert first_key != second_key


def test_outfit_refinement_prompt_preserves_person_and_only_applies_plan() -> None:
    plan = RefinePlan(
        plan_id="outfit-recommended-001",
        plan_type="recommended",
        title="推荐调整",
        summary="只调整最关键的一处",
        change_budget="替换一件",
        changes=[
            {
                "target": "上衣版型",
                "action": "调整",
                "from": "宽松长上衣",
                "to": "合身短上衣",
                "reason": "露出腰线",
            }
        ],
        before_image="/uploads/original.png",
        after_image="/uploads/original.png",
    )

    prompt = _build_outfit_refinement_image_prompt(plan, "面试会议")

    assert "restrained but clearly visible wardrobe improvements" in prompt
    assert "same person, face, hair, body proportions" in prompt
    assert "Preserve every original garment that is not explicitly changed" in prompt
    assert "Apply every listed change accurately" in prompt
    assert "visibly distinguishable" in prompt
    assert "上衣版型" in prompt
    assert "面试会议" in prompt
    assert "Do not add text" in prompt
    assert "outfit breakdowns" in prompt
    assert "Return only the clean edited fashion photograph" in prompt


def test_outfit_refinement_cache_changes_with_prompt(tmp_path) -> None:
    reference_image = tmp_path / "look.png"
    reference_image.write_bytes(b"same-look")
    plan = RefinePlan(
        plan_id="outfit-recommended-001",
        plan_type="recommended",
        title="推荐调整",
        summary="少量调整",
        change_budget="替换一件",
        changes=[],
        before_image="/uploads/original.png",
        after_image="/uploads/original.png",
    )
    request = GenerateOutfitImageRequest(
        session_id="session-1",
        image_id="image-1",
        occasion="日常休闲",
        plan=plan,
    )

    first_key = _outfit_refinement_cache_key(request, reference_image, "prompt-v1")
    second_key = _outfit_refinement_cache_key(request, reference_image, "prompt-v2")

    assert first_key != second_key
