from app.providers.qwen_image_provider import QwenImageProvider
from app.schemas.item import ClothingItem, ItemRecommendation, RecommendationItem
from app.services.styling_service import _build_item_image_prompt
from app.services import image_generation_jobs


def test_qwen_image_endpoint_uses_dashscope_native_generation_path() -> None:
    endpoint = QwenImageProvider._image_endpoint(
        "https://example.com/compatible-mode/v1"
    )

    assert endpoint == "https://example.com/api/v1/services/aigc/multimodal-generation/generation"


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

    assert "Fixed anchor item structured description" in prompt
    assert "黑色高腰阔腿裤" in prompt
    assert "primary color: 黑色" in prompt
    assert "silhouette: 阔腿" in prompt
    assert "rise/waistline: 高腰" in prompt
    assert "length: 九分" in prompt
    assert "must remain visually recognizable" in prompt


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
