import base64
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
        reference_image_path: Optional[Path] = None,
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
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": self._message_content(
                                    prompt=prompt,
                                    reference_image_path=reference_image_path,
                                ),
                            }
                        ]
                    },
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
            raise QwenImageError(self._http_error_message(exc, "image request")) from exc
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
                metadata={
                    "image_size": settings.QWEN_IMAGE_SIZE,
                    "has_reference_image": reference_image_path is not None,
                },
            )
            if settings.STYLING_DEBUG:
                print(
                    "[image-debug] "
                    f"session_id={session_id} run_id={run_id} model={self.model} "
                    f"prompt_version={prompt_version} latency_ms={latency_ms} status={status}"
                )

    def start_image_task(
        self,
        *,
        prompt: str,
        reference_image_path: Optional[Path] = None,
    ) -> str:
        if reference_image_path is not None:
            return self._start_multimodal_image_task(
                prompt=prompt,
                reference_image_path=reference_image_path,
            )

        try:
            response = httpx.post(
                self._async_image_endpoint(settings.DASHSCOPE_BASE_URL),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": settings.QWEN_IMAGE_ASYNC_MODEL,
                    "input": {"prompt": prompt},
                    "parameters": {
                        "size": settings.QWEN_IMAGE_SIZE,
                        "n": 1,
                        "prompt_extend": True,
                        "watermark": False,
                    },
                },
                timeout=min(self.timeout, 25),
                trust_env=False,
            )
            response.raise_for_status()
            data = response.json()
            task_id = data.get("output", {}).get("task_id") or data.get("task_id")
            if not task_id:
                raise QwenImageError("Qwen Image task response missing task ID.")
            return str(task_id)
        except httpx.TimeoutException as exc:
            raise QwenImageError("Qwen Image task submission timed out.") from exc
        except httpx.RequestError as exc:
            raise QwenImageError("Qwen Image task submission request failed.") from exc
        except httpx.HTTPStatusError as exc:
            raise QwenImageError(self._http_error_message(exc, "task submission")) from exc

    def _start_multimodal_image_task(
        self,
        *,
        prompt: str,
        reference_image_path: Path,
    ) -> str:
        try:
            response = httpx.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": self.model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": self._message_content(
                                    prompt=prompt,
                                    reference_image_path=reference_image_path,
                                ),
                            }
                        ]
                    },
                    "parameters": {
                        "size": settings.QWEN_IMAGE_SIZE,
                        "n": 1,
                        "prompt_extend": False,
                        "watermark": False,
                    },
                },
                timeout=min(self.timeout, 25),
                trust_env=False,
            )
            response.raise_for_status()
            data = response.json()
            task_id = data.get("output", {}).get("task_id") or data.get("task_id")
            if not task_id:
                raise QwenImageError("Qwen Image reference task response missing task ID.")
            return str(task_id)
        except httpx.TimeoutException as exc:
            raise QwenImageError("Qwen Image reference task submission timed out.") from exc
        except httpx.RequestError as exc:
            raise QwenImageError("Qwen Image reference task submission request failed.") from exc
        except httpx.HTTPStatusError as exc:
            raise QwenImageError(self._http_error_message(exc, "reference task submission")) from exc

    def poll_image_task(self, task_id: str) -> Optional[str]:
        try:
            response = httpx.get(
                self._task_endpoint(settings.DASHSCOPE_BASE_URL, task_id),
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=min(settings.MODEL_TIMEOUT_SECONDS, 25),
                trust_env=False,
            )
            response.raise_for_status()
            data = response.json()
            output = data.get("output", {}) or {}
            task_status = str(output.get("task_status") or data.get("task_status") or "").upper()
            if task_status in {"PENDING", "RUNNING", "SUSPENDED", ""}:
                return None
            if task_status != "SUCCEEDED":
                message = output.get("message") or data.get("message") or task_status
                raise QwenImageError(f"Qwen Image task failed: {message}")

            image_url = self._extract_image_url(data)
            return self._download_image(image_url)
        except httpx.TimeoutException as exc:
            raise QwenImageError("Qwen Image task polling timed out.") from exc
        except httpx.RequestError as exc:
            raise QwenImageError("Qwen Image task polling request failed.") from exc
        except httpx.HTTPStatusError as exc:
            raise QwenImageError(self._http_error_message(exc, "task polling")) from exc
        except (KeyError, ValueError, TypeError) as exc:
            raise QwenImageError("Qwen Image task response missing image URL.") from exc

    @staticmethod
    def _image_endpoint(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/compatible-mode/v1"):
            return base[: -len("/compatible-mode/v1")] + "/api/v1/services/aigc/image-generation/generation"
        return base + "/services/aigc/image-generation/generation"

    @staticmethod
    def _async_image_endpoint(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/compatible-mode/v1"):
            return base[: -len("/compatible-mode/v1")] + "/api/v1/services/aigc/text2image/image-synthesis"
        return base + "/services/aigc/text2image/image-synthesis"

    @staticmethod
    def _task_endpoint(base_url: str, task_id: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/compatible-mode/v1"):
            return base[: -len("/compatible-mode/v1")] + f"/api/v1/tasks/{task_id}"
        return base + f"/tasks/{task_id}"

    @classmethod
    def _message_content(
        cls,
        *,
        prompt: str,
        reference_image_path: Optional[Path] = None,
    ) -> list[dict[str, str]]:
        content: list[dict[str, str]] = []
        if reference_image_path is not None:
            content.append({"image": cls._image_data_url(reference_image_path)})
        content.append({"text": prompt})
        return content

    @staticmethod
    def _image_data_url(image_path: Path) -> str:
        suffix = image_path.suffix.lower().lstrip(".")
        mime_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(suffix, "image/jpeg")
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{image_b64}"

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
    def _http_error_message(exc: httpx.HTTPStatusError, operation: str) -> str:
        response = exc.response
        provider_code = ""
        provider_message = ""
        request_id = response.headers.get("x-request-id", "")
        try:
            payload = response.json()
            provider_code = str(payload.get("code") or payload.get("error", {}).get("code") or "")
            provider_message = str(
                payload.get("message")
                or payload.get("error", {}).get("message")
                or ""
            )
            request_id = str(payload.get("request_id") or request_id)
        except (TypeError, ValueError):
            provider_message = response.text.strip()[:240]

        details = ": ".join(part for part in (provider_code, provider_message) if part)
        suffix = f" ({details})" if details else ""
        request_suffix = f" [request_id={request_id}]" if request_id else ""
        return f"Qwen Image {operation} HTTP {response.status_code}{suffix}{request_suffix}"

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
