import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import httpx

from app import settings
from app.services.ai_run_logger import log_ai_run, new_run_id


class QwenImageError(RuntimeError):
    pass


class QwenImageProvider:
    provider = "dashscope"

    def __init__(self) -> None:
        settings.require_qwen_image_settings()
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.QWEN_IMAGE_MODEL
        self.timeout = max(settings.MODEL_TIMEOUT_SECONDS, 120)
        self.endpoint = self._image_endpoint(settings.DASHSCOPE_BASE_URL)

    def generate_image(
        self,
        *,
        prompt: str,
        task_type: str,
        prompt_version: str,
        session_id: str,
        recommendation_id: Optional[str] = None,
    ) -> str:
        run_id = new_run_id()
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        status = "failed"
        error_type: Optional[str] = None

        try:
            response = httpx.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                    "parameters": {
                        "size": settings.QWEN_IMAGE_SIZE,
                        "n": 1,
                        "prompt_extend": True,
                        "watermark": False,
                    },
                },
                timeout=self.timeout,
                trust_env=False,
            )
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage", {}) or {}
            image_url = self._extract_image_url(data)
            local_url = self._download_image(image_url)
            status = "success"
            return local_url
        except httpx.TimeoutException as exc:
            error_type = "timeout"
            raise QwenImageError("Qwen Image request timed out.") from exc
        except httpx.RequestError as exc:
            error_type = "network"
            raise QwenImageError("Qwen Image network request failed.") from exc
        except httpx.HTTPStatusError as exc:
            error_type = f"http_{exc.response.status_code}"
            raise QwenImageError(f"Qwen Image HTTP error: {exc.response.status_code}") from exc
        except (KeyError, ValueError, TypeError) as exc:
            error_type = "response_shape"
            raise QwenImageError("Qwen Image response missing image URL.") from exc
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            log_ai_run(
                run_id=run_id,
                provider=self.provider,
                task_type=task_type,
                model_name=self.model,
                prompt_version=prompt_version,
                session_id=session_id,
                recommendation_id=recommendation_id,
                started_at=started_at,
                status=status,
                latency_ms=latency_ms,
                error_type=error_type,
                input_tokens=usage.get("input_tokens") or usage.get("prompt_tokens"),
                output_tokens=usage.get("output_tokens") or usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                metadata={"image_size": settings.QWEN_IMAGE_SIZE},
            )
            if settings.STYLING_DEBUG:
                print(
                    "[image-debug] "
                    f"session_id={session_id} run_id={run_id} model={self.model} "
                    f"prompt_version={prompt_version} latency_ms={latency_ms} status={status}"
                )

    @staticmethod
    def _image_endpoint(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/compatible-mode/v1"):
            return base[: -len("/compatible-mode/v1")] + "/api/v1/services/aigc/multimodal-generation/generation"
        return base + "/services/aigc/multimodal-generation/generation"

    @staticmethod
    def _extract_image_url(data: dict[str, Any]) -> str:
        output = data.get("output", {})
        choices = output.get("choices") or []
        for choice in choices:
            message = choice.get("message", {})
            content = message.get("content") or []
            for part in content:
                image = part.get("image") if isinstance(part, dict) else None
                if image:
                    return str(image)
                image_url = part.get("image_url") if isinstance(part, dict) else None
                if image_url:
                    return str(image_url)
        results = output.get("results") or []
        for result in results:
            url = result.get("url") if isinstance(result, dict) else None
            if url:
                return str(url)
        raise ValueError("No image URL in response.")

    @staticmethod
    def _download_image(image_url: str) -> str:
        response = httpx.get(image_url, timeout=settings.MODEL_TIMEOUT_SECONDS, trust_env=False)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        extension = "png"
        if "jpeg" in content_type or "jpg" in content_type:
            extension = "jpg"
        elif "webp" in content_type:
            extension = "webp"

        filename = f"generated-{uuid4()}.{extension}"
        output_path = Path(settings.UPLOAD_DIR) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return f"/uploads/{filename}"
