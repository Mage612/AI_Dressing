import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.settings import AI_RUN_LOG_PATH


def new_run_id() -> str:
    return str(uuid4())


def log_ai_run(
    *,
    run_id: str,
    provider: str,
    task_type: str,
    model_name: str,
    prompt_version: str,
    started_at: datetime,
    status: str,
    latency_ms: int,
    skill_version: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    recommendation_id: Optional[str] = None,
    error_type: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    log_path: Path = AI_RUN_LOG_PATH,
) -> None:
    record = {
        "run_id": run_id,
        "provider": provider,
        "task_type": task_type,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "skill_version": skill_version,
        "user_id": user_id,
        "session_id": session_id,
        "recommendation_id": recommendation_id,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "status": status,
        "error_type": error_type,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": None,
        "metadata": metadata or {},
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
