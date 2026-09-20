from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[2] / "index.html"


def test_generated_outfit_images_can_be_previewed_and_downloaded() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="generated-image-modal"' in html
    assert 'id="generated-image-preview"' in html
    assert 'id="download-generated-image"' in html
    assert "data-open-generated-image" in html
    assert "function openGeneratedImagePreview" in html
    assert "async function downloadGeneratedImage" in html
    assert "URL.createObjectURL(blob)" in html
    assert "link.download" in html


def test_only_recommended_plan_is_generated_automatically() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'find((plan) => plan.strategy === "recommended")' in html
    assert "generateRecommendationImage(recommended.plan_id, true)" in html
    assert 'data-generate-look="${escapeAttribute(recommendation.plan_id)}"' in html


def test_outfit_refinement_has_context_score_and_on_demand_image_flow() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="outfit-occasion-group"' in html
    assert 'id="outfit-intensity-group"' in html
    assert 'id="outfit-score-total"' in html
    assert 'id="outfit-score-dimensions"' in html
    assert 'data-generate-outfit-image' in html
    assert 'requestJson("/outfit-refinement-image"' in html
    assert "function pollOutfitRefinementImage" in html
    assert 'requestJson("/analyze-outfit"' in html
    assert "vision_observation: diagnosis" in html
    assert "refinement = refinement || {};" in html
    assert "plan.after_image = imageUrl" in html
