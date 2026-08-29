from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from app import settings
from app.providers.qwen_vision_provider import QwenVisionProvider
from app.services import image_service, vision_service
from app.services.image_preprocessor import preprocess_for_vision


def _write_test_image(path, size=(2000, 1000)) -> None:
    image = Image.new("RGB", size, (30, 40, 50))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)


@pytest.fixture()
def uploaded_image(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "UPLOAD_DIR", tmp_path)
    image_id = str(uuid4())
    image_path = tmp_path / f"{image_id}.jpg"
    _write_test_image(image_path)
    return image_id, image_path


def test_preprocess_for_vision_transposes_rgb_resizes_and_removes_exif(uploaded_image):
    _, image_path = uploaded_image

    processed = preprocess_for_vision(image_path)

    assert max(processed.processed_width, processed.processed_height) <= 1024
    assert processed.original_width == 1000
    assert processed.original_height == 2000
    assert processed.processed_width == 512
    assert processed.processed_height == 1024

    with Image.open(BytesIO(processed.content)) as output:
        assert output.mode == "RGB"
        assert len(output.getexif()) == 0


def test_get_uploaded_image_path_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "UPLOAD_DIR", tmp_path)

    with pytest.raises(image_service.InvalidImageIdError):
        image_service.get_uploaded_image_path("../outside")


def test_live_analyze_item_uses_qwen_provider(uploaded_image, monkeypatch):
    image_id, _ = uploaded_image
    monkeypatch.setattr(settings, "AI_MODE", "live")

    def fake_analyze_json(self, **kwargs):
        assert kwargs["task_type"] == "item_analysis"
        assert kwargs["prompt_version"] == "vision_item_v0.2"
        return vision_service.QwenItemObservation(
            category="trousers",
            name="黑色直筒牛仔裤",
            primary_color="黑色",
            pattern="纯色",
            silhouette="直筒",
            rise="中腰",
            length="长款",
            style_tags=["休闲", "简约"],
            occasion_tags=["日常"],
            confidence=0.84,
        )

    monkeypatch.setattr(QwenVisionProvider, "analyze_json", fake_analyze_json)
    monkeypatch.setattr(QwenVisionProvider, "__init__", lambda self: None)

    response = vision_service.analyze_item(image_id)

    assert response.confidence == 0.84
    assert response.item.name == "黑色直筒牛仔裤"
    assert response.item.primary_color == "黑色"


def test_live_analyze_item_normalizes_english_qwen_terms(uploaded_image, monkeypatch):
    image_id, _ = uploaded_image
    monkeypatch.setattr(settings, "AI_MODE", "live")

    def fake_analyze_json(self, **kwargs):
        return vision_service.QwenItemObservation(
            category="shoes",
            name="low-top sneakers",
            primary_color="pink and white",
            pattern="print",
            silhouette="unknown",
            rise="unknown",
            length="low-top",
            style_tags=["casual", "streetwear", "cute"],
            occasion_tags=["daily", "street"],
            confidence=0.91,
        )

    monkeypatch.setattr(QwenVisionProvider, "analyze_json", fake_analyze_json)
    monkeypatch.setattr(QwenVisionProvider, "__init__", lambda self: None)

    response = vision_service.analyze_item(image_id)

    assert response.confidence == 0.91
    assert response.item.category == "鞋子"
    assert response.item.name == "粉白色低帮运动鞋"
    assert response.item.primary_color == "粉白色"
    assert response.item.pattern == "印花"
    assert response.item.length == "低帮"
    assert response.item.style_tags == ["休闲", "街头感", "甜美"]
    assert response.item.occasion_tags == ["日常", "街头"]


def test_invalid_image_id_does_not_call_qwen(monkeypatch):
    monkeypatch.setattr(settings, "AI_MODE", "live")

    def fail_init(self):
        raise AssertionError("Qwen provider should not be constructed for invalid image_id")

    monkeypatch.setattr(QwenVisionProvider, "__init__", fail_init)

    with pytest.raises(image_service.InvalidImageIdError):
        vision_service.analyze_item("not-a-valid-id")
