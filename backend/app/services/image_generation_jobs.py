import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from app import settings
from app.providers.qwen_image_provider import QwenImageError, QwenImageProvider


STATE_PATH = settings.UPLOAD_DIR / ".image_generation_state.json"


class ImageGenerationLimitError(RuntimeError):
    pass


@dataclass
class ImageGenerationJob:
    job_id: str
    plan_id: str
    fallback_image_url: str
    status: str = "pending"
    image_url: str = ""
    error: str = ""
    external_task_id: str = ""
    cache_key: str = ""
    visitor_id: str = ""
    usage_date: str = ""
    cached: bool = False
    remaining_daily_generations: Optional[int] = None


_jobs: dict[str, ImageGenerationJob] = {}
_jobs_by_cache_key: dict[str, str] = {}
_lock = Lock()


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _empty_state() -> dict:
    return {"cache": {}, "usage": {}}


def _load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    data.setdefault("cache", {})
    data.setdefault("usage", {})
    return data


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(STATE_PATH)


def _usage_for_today(state: dict) -> dict:
    today = _today()
    usage = state["usage"].get(today)
    if not isinstance(usage, dict):
        usage = {"global": 0, "visitors": {}}
        state["usage"] = {today: usage}
    usage.setdefault("global", 0)
    usage.setdefault("visitors", {})
    return usage


def _remaining(usage: dict, visitor_id: str) -> Optional[int]:
    limit = settings.IMAGE_VISITOR_DAILY_LIMIT
    if limit <= 0:
        return None
    used = int(usage["visitors"].get(visitor_id, 0))
    return max(0, limit - used)


def _cached_image_exists(image_url: str) -> bool:
    if not image_url.startswith("/uploads/"):
        return bool(image_url)
    return (settings.UPLOAD_DIR / Path(image_url).name).is_file()


def _reserve_generation(state: dict, visitor_id: str) -> Optional[int]:
    usage = _usage_for_today(state)
    visitor_used = int(usage["visitors"].get(visitor_id, 0))
    if (
        settings.IMAGE_VISITOR_DAILY_LIMIT > 0
        and visitor_used >= settings.IMAGE_VISITOR_DAILY_LIMIT
    ):
        raise ImageGenerationLimitError("今天的效果图体验次数已用完，明天再来看看吧。")
    if (
        settings.IMAGE_GLOBAL_DAILY_LIMIT > 0
        and int(usage["global"]) >= settings.IMAGE_GLOBAL_DAILY_LIMIT
    ):
        raise ImageGenerationLimitError("今天的全站效果图额度已用完，请明天再试。")
    usage["global"] = int(usage["global"]) + 1
    usage["visitors"][visitor_id] = visitor_used + 1
    return _remaining(usage, visitor_id)


def _release_generation(state: dict, visitor_id: str, usage_date: str) -> None:
    usage = state["usage"].get(usage_date)
    if not isinstance(usage, dict):
        return
    usage["global"] = max(0, int(usage.get("global", 0)) - 1)
    visitors = usage.setdefault("visitors", {})
    visitors[visitor_id] = max(0, int(visitors.get(visitor_id, 0)) - 1)


def start_image_generation_job(
    *,
    plan_id: str,
    fallback_image_url: str,
    prompt: str,
    task_type: str,
    prompt_version: str,
    session_id: str,
    recommendation_id: Optional[str] = None,
    reference_image_path: Optional[Path] = None,
    cache_key: str = "",
    visitor_id: str = "",
) -> ImageGenerationJob:
    del task_type, prompt_version, recommendation_id
    visitor_id = visitor_id or session_id
    usage_date = _today()

    with _lock:
        state = _load_state()
        cached_url = state["cache"].get(cache_key) if cache_key else None
        if cached_url and _cached_image_exists(cached_url):
            usage = _usage_for_today(state)
            return ImageGenerationJob(
                job_id=f"cached-{cache_key[:16]}",
                plan_id=plan_id,
                fallback_image_url=fallback_image_url,
                status="generated",
                image_url=cached_url,
                cache_key=cache_key,
                visitor_id=visitor_id,
                usage_date=usage_date,
                cached=True,
                remaining_daily_generations=_remaining(usage, visitor_id),
            )

        existing_job_id = _jobs_by_cache_key.get(cache_key) if cache_key else None
        if existing_job_id and existing_job_id in _jobs:
            return _jobs[existing_job_id]

        remaining = _reserve_generation(state, visitor_id)
        _save_state(state)
        job = ImageGenerationJob(
            job_id=str(uuid4()),
            plan_id=plan_id,
            fallback_image_url=fallback_image_url,
            image_url=fallback_image_url,
            cache_key=cache_key,
            visitor_id=visitor_id,
            usage_date=usage_date,
            remaining_daily_generations=remaining,
        )
        _jobs[job.job_id] = job
        if cache_key:
            _jobs_by_cache_key[cache_key] = job.job_id

    try:
        job.external_task_id = QwenImageProvider().start_image_task(
            prompt=prompt,
            reference_image_path=reference_image_path,
        )
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        with _lock:
            state = _load_state()
            _release_generation(state, visitor_id, usage_date)
            _save_state(state)
            if cache_key:
                _jobs_by_cache_key.pop(cache_key, None)
            job.remaining_daily_generations = _remaining(
                _usage_for_today(state), visitor_id
            )

    return job


def get_image_generation_job(job_id: str) -> Optional[ImageGenerationJob]:
    with _lock:
        job = _jobs.get(job_id)
    if job is None or job.status != "pending" or not job.external_task_id:
        return job

    try:
        image_url = QwenImageProvider().poll_image_task(job.external_task_id)
        if image_url:
            _update_job(job_id, status="generated", image_url=image_url, error="")
    except QwenImageError as exc:
        _update_job(job_id, status="failed", error=str(exc), release_usage=True)

    with _lock:
        return _jobs.get(job_id)


def _update_job(
    job_id: str,
    *,
    status: str,
    image_url: str = "",
    error: str = "",
    release_usage: bool = False,
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = status
        if image_url:
            job.image_url = image_url
        job.error = error

        state = _load_state()
        if status == "generated" and image_url and job.cache_key:
            state["cache"][job.cache_key] = image_url
        if release_usage:
            _release_generation(state, job.visitor_id, job.usage_date)
            if job.cache_key:
                _jobs_by_cache_key.pop(job.cache_key, None)
            job.remaining_daily_generations = _remaining(
                _usage_for_today(state), job.visitor_id
            )
        _save_state(state)
