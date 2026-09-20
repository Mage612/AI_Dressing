from dataclasses import dataclass
from threading import Lock, Thread
from typing import Any, Optional
from uuid import uuid4

from app.schemas.outfit import RefineOutfitRequest


@dataclass
class OutfitWorkflowJob:
    job_id: str
    status: str = "pending"
    result: Optional[dict[str, Any]] = None
    error: str = ""


_jobs: dict[str, OutfitWorkflowJob] = {}
_lock = Lock()


def start_analysis_job(image_id: str) -> OutfitWorkflowJob:
    return _start_job(_run_analysis, image_id)


def start_refinement_job(request: RefineOutfitRequest) -> OutfitWorkflowJob:
    return _start_job(_run_refinement, request)


def get_outfit_workflow_job(job_id: str) -> Optional[OutfitWorkflowJob]:
    with _lock:
        return _jobs.get(job_id)


def _start_job(worker, payload) -> OutfitWorkflowJob:
    job = OutfitWorkflowJob(job_id=str(uuid4()))
    with _lock:
        _jobs[job.job_id] = job
    Thread(target=_execute, args=(job.job_id, worker, payload), daemon=True).start()
    return job


def _execute(job_id: str, worker, payload) -> None:
    try:
        result = worker(payload)
        _update_job(job_id, status="completed", result=result)
    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc))


def _run_analysis(image_id: str) -> dict[str, Any]:
    from app.services.vision_service import analyze_outfit

    result = analyze_outfit(image_id)
    return result.model_dump() if hasattr(result, "model_dump") else result.dict()


def _run_refinement(request: RefineOutfitRequest) -> dict[str, Any]:
    from app.services.styling_service import refine_outfit

    result = refine_outfit(request)
    if hasattr(result, "model_dump"):
        return result.model_dump(by_alias=True)
    return result.dict(by_alias=True)


def _update_job(
    job_id: str,
    *,
    status: str,
    result: Optional[dict[str, Any]] = None,
    error: str = "",
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = status
        job.result = result
        job.error = error
