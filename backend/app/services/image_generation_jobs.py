from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import uuid4

from app.providers.qwen_image_provider import QwenImageError, QwenImageProvider


@dataclass
class ImageGenerationJob:
    job_id: str
    plan_id: str
    fallback_image_url: str
    status: str = "pending"
    image_url: str = ""
    error: str = ""
    external_task_id: str = ""


_jobs: dict[str, ImageGenerationJob] = {}
_lock = Lock()


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
) -> ImageGenerationJob:
    job = ImageGenerationJob(
        job_id=str(uuid4()),
        plan_id=plan_id,
        fallback_image_url=fallback_image_url,
        image_url=fallback_image_url,
    )
    try:
        job.external_task_id = QwenImageProvider().start_image_task(
            prompt=prompt,
            reference_image_path=reference_image_path,
        )
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)

    with _lock:
        _jobs[job.job_id] = job

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
        _update_job(job_id, status="failed", error=str(exc))

    with _lock:
        return _jobs.get(job_id)


def _update_job(job_id: str, *, status: str, image_url: str = "", error: str = "") -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = status
        if image_url:
            job.image_url = image_url
        job.error = error
