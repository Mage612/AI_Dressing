from pathlib import Path
import time
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import settings
from app.settings import MAX_UPLOAD_BYTES
from app.api import upload as upload_api
from app.services import image_service


client = TestClient(app)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def use_temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(image_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "AI_MODE", "mock")
    yield tmp_path


def _cleanup_uploaded_file(image_url: str) -> None:
    filename = Path(urlparse(image_url).path).name
    output_path = upload_api.UPLOAD_DIR / filename
    if output_path.exists():
        output_path.unlink()


def _upload_test_image() -> dict:
    response = client.post(
        "/api/upload",
        files={"file": ("pants.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    return response.json()


def test_health_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_valid_image_success() -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("裤子.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["image_id"]
    assert data["image_url"].startswith("/uploads/")
    assert data["image_url"].endswith(".png")

    filename = Path(urlparse(data["image_url"]).path).name
    assert filename.startswith(data["image_id"])
    assert (upload_api.UPLOAD_DIR / filename).exists()

    _cleanup_uploaded_file(data["image_url"])


def test_upload_invalid_file_type_fails() -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_too_large_fails() -> None:
    too_large_png = PNG_BYTES + b"0" * (MAX_UPLOAD_BYTES + 1)

    response = client.post(
        "/api/upload",
        files={"file": ("large.png", too_large_png, "image/png")},
    )

    assert response.status_code == 413


def test_analyze_item_returns_schema() -> None:
    uploaded = _upload_test_image()

    try:
        response = client.post(
            "/api/analyze-item",
            json={"image_id": uploaded["image_id"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["image_id"] == uploaded["image_id"]
        assert data["confidence"] == 0.93
        assert data["item"]["category"] == "trousers"
        assert data["item"]["name"] == "深灰色高腰阔腿西装裤"
        assert data["item"]["style_tags"] == ["简约", "通勤"]
    finally:
        _cleanup_uploaded_file(uploaded["image_url"])


def test_recommend_item_returns_three_recommendations() -> None:
    uploaded = _upload_test_image()

    try:
        response = client.post(
            "/api/recommend-item",
            json={
                "image_id": uploaded["image_id"],
                "occasion": "通勤",
                "desired_style": "AI 推荐",
                "free_text_constraints": "不穿高跟鞋",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"]
        assert data["user_constraints"]["occasion"] == "通勤"
        assert len(data["recommendations"]) == 3
        assert {item["strategy"] for item in data["recommendations"]} == {
            "safe",
            "recommended",
            "expressive",
        }
        assert all(item["items"] for item in data["recommendations"])
        assert all(item["image_url"] for item in data["recommendations"])
    finally:
        _cleanup_uploaded_file(uploaded["image_url"])


def test_analyze_item_invalid_image_id_fails() -> None:
    response = client.post("/api/analyze-item", json={"image_id": "not-a-valid-image-id"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image_id."


def test_analyze_outfit_returns_schema() -> None:
    uploaded = _upload_test_image()

    try:
        response = client.post(
            "/api/analyze-outfit",
            json={"image_id": uploaded["image_id"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["overall_summary"]
        assert data["strengths"]
        assert data["main_issues"]
        assert data["diagnosis_dimensions"]
        assert data["keep_items"]
    finally:
        _cleanup_uploaded_file(uploaded["image_url"])


def test_outfit_analysis_job_completes() -> None:
    uploaded = _upload_test_image()

    try:
        started = client.post(
            "/api/analyze-outfit-job",
            json={"image_id": uploaded["image_id"]},
        )
        assert started.status_code == 200
        job_id = started.json()["job_id"]

        result = None
        for _ in range(20):
            response = client.get(f"/api/analyze-outfit-job/{job_id}")
            assert response.status_code == 200
            if response.json()["status"] != "pending":
                result = response.json()
                break
            time.sleep(0.01)

        assert result is not None
        assert result["status"] == "completed"
        assert result["result"]["overall_summary"]
    finally:
        _cleanup_uploaded_file(uploaded["image_url"])


def test_refine_outfit_returns_three_plan_types() -> None:
    uploaded = _upload_test_image()

    try:
        diagnosis = client.post(
            "/api/analyze-outfit",
            json={"image_id": uploaded["image_id"]},
        ).json()
        response = client.post(
            "/api/refine-outfit",
            json={
                "image_id": uploaded["image_id"],
                "occasion": "面试会议",
                "change_intensity": "recommended",
                "conversation_state": {
                    "locked_items": ["上衣"],
                    "rejected_items": ["高跟鞋"],
                    "user_notes": "想更显高",
                },
                "vision_observation": diagnosis,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["plans"]) == 3
        assert {plan["plan_type"] for plan in data["plans"]} == {
            "recommended",
            "minimal",
            "expressive",
        }
        assert all(plan["change_budget"] for plan in data["plans"])
        assert all("from" in plan["changes"][0] for plan in data["plans"])
        assert data["occasion"] == "面试会议"
        assert data["occasion_assessment"]
        assert data["score"]["total"] == sum(
            item["score"] for item in data["score"]["dimensions"]
        )
        assert len(data["score"]["dimensions"]) == 5
        assert all(plan["after_image"] == plan["before_image"] for plan in data["plans"])
        assert all(plan["image_status"] == "awaiting_generation" for plan in data["plans"])

        image_response = client.post(
            "/api/outfit-refinement-image",
            json={
                "session_id": data["session_id"],
                "image_id": uploaded["image_id"],
                "occasion": data["occasion"],
                "plan": next(
                    plan for plan in data["plans"] if plan["plan_type"] == "recommended"
                ),
                "visitor_id": "test-visitor",
            },
        )
        assert image_response.status_code == 200
        assert image_response.json()["image_status"] == "failed"
        assert image_response.json()["plan_id"] == "outfit-recommended-001"
    finally:
        _cleanup_uploaded_file(uploaded["image_url"])


def test_refine_outfit_request_accepts_existing_vision_observation() -> None:
    from app.schemas.outfit import RefineOutfitRequest

    request = RefineOutfitRequest(
        image_id="11111111-1111-4111-8111-111111111111",
        vision_observation={
            "image_id": "11111111-1111-4111-8111-111111111111",
            "overall_summary": "整体简洁。",
            "strengths": ["配色统一。"],
            "main_issues": ["层次稍少。"],
            "diagnosis_dimensions": [],
            "keep_items": ["上衣"],
        },
    )

    assert request.vision_observation is not None
    assert request.vision_observation.overall_summary == "整体简洁。"


def test_outfit_refinement_job_completes() -> None:
    uploaded = _upload_test_image()

    try:
        diagnosis = client.post(
            "/api/analyze-outfit",
            json={"image_id": uploaded["image_id"]},
        ).json()
        started = client.post(
            "/api/refine-outfit-job",
            json={
                "image_id": uploaded["image_id"],
                "occasion": "日常休闲",
                "vision_observation": diagnosis,
            },
        )
        assert started.status_code == 200
        job_id = started.json()["job_id"]

        result = None
        for _ in range(20):
            response = client.get(f"/api/refine-outfit-job/{job_id}")
            assert response.status_code == 200
            if response.json()["status"] != "pending":
                result = response.json()
                break
            time.sleep(0.01)

        assert result is not None
        assert result["status"] == "completed"
        assert len(result["result"]["plans"]) == 3
    finally:
        _cleanup_uploaded_file(uploaded["image_url"])


def test_review_outfit_returns_comparison_report() -> None:
    original = _upload_test_image()
    reviewed = _upload_test_image()

    try:
        response = client.post(
            "/api/review-outfit",
            json={
                "original_image_id": original["image_id"],
                "reviewed_image_id": reviewed["image_id"],
                "plan_id": "outfit-recommended-001",
                "free_text_feedback": "按推荐调整后拍的试穿图",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["review_id"]
        assert data["original_image_id"] == original["image_id"]
        assert data["reviewed_image_id"] == reviewed["image_id"]
        assert data["overall_result"]
        assert data["improved_points"]
        assert data["remaining_issues"]
        assert data["comparison_dimensions"]
        assert data["next_recommendation"]
    finally:
        _cleanup_uploaded_file(original["image_url"])
        _cleanup_uploaded_file(reviewed["image_url"])
