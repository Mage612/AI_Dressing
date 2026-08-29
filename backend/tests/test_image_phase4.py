from app.providers.qwen_image_provider import QwenImageProvider


def test_qwen_image_endpoint_uses_dashscope_native_generation_path() -> None:
    endpoint = QwenImageProvider._image_endpoint(
        "https://example.com/compatible-mode/v1"
    )

    assert endpoint == "https://example.com/api/v1/services/aigc/multimodal-generation/generation"


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
