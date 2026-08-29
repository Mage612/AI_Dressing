import os

import pytest

from app.providers.qwen_image_provider import QwenImageProvider


@pytest.mark.skipif(
    os.getenv("RUN_QWEN_IMAGE_INTEGRATION") != "1",
    reason="Set RUN_QWEN_IMAGE_INTEGRATION=1 to call the real Qwen Image API.",
)
def test_qwen_image_generation_smoke_test() -> None:
    url = QwenImageProvider().generate_image(
        prompt=(
            "生成一张竖版手机卡片用的女装通勤穿搭参考图，"
            "深灰色高腰直筒长裙，黑色修身无袖上衣，黑色平底鞋，"
            "自然光，干净背景，无文字无水印。"
        ),
        task_type="qwen_image_integration_test",
        prompt_version="phase4_v0.1",
        session_id="integration-test",
    )

    assert url.startswith("/uploads/generated-")
