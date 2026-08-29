import os

import pytest

from app.services.styling_service import smoke_test_deepseek


@pytest.mark.skipif(
    os.getenv("RUN_DEEPSEEK_INTEGRATION") != "1",
    reason="Set RUN_DEEPSEEK_INTEGRATION=1 to call the real DeepSeek API.",
)
def test_deepseek_connection_smoke_test() -> None:
    result = smoke_test_deepseek()

    assert result["ok"] is True
    assert result["model"]
    assert result["run_id"]
