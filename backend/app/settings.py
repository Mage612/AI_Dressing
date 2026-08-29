import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(ENV_PATH)

UPLOAD_DIR = BACKEND_DIR / "uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
AI_RUN_LOG_PATH = BACKEND_DIR / "ai_runs.jsonl"

AI_MODE = os.getenv("AI_MODE", "mock").strip().lower()
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "").rstrip("/")
QWEN_VISION_MODEL = os.getenv("QWEN_VISION_MODEL", "qwen3.7-plus")
QWEN_IMAGE_MODEL = os.getenv("QWEN_IMAGE_MODEL", "qwen-image-3.0-pro")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
AI_STYLING_MODE = os.getenv("AI_STYLING_MODE", "mock").strip().lower()
AI_IMAGE_MODE = os.getenv("AI_IMAGE_MODE", "mock").strip().lower()
STYLING_PROMPT_VERSION = os.getenv("STYLING_PROMPT_VERSION", "v0.1")
STYLING_SKILL_VERSION = os.getenv("STYLING_SKILL_VERSION", "v0.1")
STYLING_DEBUG = os.getenv("STYLING_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}
QWEN_IMAGE_SIZE = os.getenv("QWEN_IMAGE_SIZE", "928*1664")
QWEN_IMAGE_PLAN_LIMIT = int(os.getenv("QWEN_IMAGE_PLAN_LIMIT", "1"))
MODEL_TIMEOUT_SECONDS = float(os.getenv("MODEL_TIMEOUT_SECONDS", "30"))

def _split_csv_env(name: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or defaults


DEV_ORIGINS = _split_csv_env(
    "CORS_ORIGINS",
    [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
)


def is_live_ai_enabled() -> bool:
    return AI_MODE == "live"


def require_qwen_vision_settings() -> None:
    missing = []
    if not DASHSCOPE_API_KEY:
        missing.append("DASHSCOPE_API_KEY")
    if not DASHSCOPE_BASE_URL:
        missing.append("DASHSCOPE_BASE_URL")
    if not QWEN_VISION_MODEL:
        missing.append("QWEN_VISION_MODEL")

    if missing:
        raise RuntimeError(
            "Missing required Qwen Vision environment variables: "
            + ", ".join(missing)
        )


def is_live_styling_enabled() -> bool:
    return AI_STYLING_MODE == "live"


def require_deepseek_settings() -> None:
    missing = []
    if not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")
    if not DEEPSEEK_MODEL:
        missing.append("DEEPSEEK_MODEL")

    if missing:
        raise RuntimeError(
            "Missing required DeepSeek environment variables: " + ", ".join(missing)
        )


def is_live_image_enabled() -> bool:
    return AI_IMAGE_MODE == "live"


def require_qwen_image_settings() -> None:
    missing = []
    if not DASHSCOPE_API_KEY:
        missing.append("DASHSCOPE_API_KEY")
    if not DASHSCOPE_BASE_URL:
        missing.append("DASHSCOPE_BASE_URL")
    if not QWEN_IMAGE_MODEL:
        missing.append("QWEN_IMAGE_MODEL")

    if missing:
        raise RuntimeError(
            "Missing required Qwen Image environment variables: " + ", ".join(missing)
        )
