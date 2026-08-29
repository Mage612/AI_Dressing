import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app import settings
from app.services.ai_run_logger import log_ai_run, new_run_id
from app.services.image_preprocessor import preprocess_for_vision


T = TypeVar("T", bound=BaseModel)


class QwenVisionError(RuntimeError):
    pass


class QwenVisionProvider:
    provider = "dashscope"

    def __init__(self) -> None:
        settings.require_qwen_vision_settings()
        self.base_url = settings.DASHSCOPE_BASE_URL
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.QWEN_VISION_MODEL
        self.timeout = settings.MODEL_TIMEOUT_SECONDS

    def analyze_json(
        self,
        *,
        image_path: Path,
        prompt: str,
        prompt_version: str,
        task_type: str,
        response_model: type[T],
    ) -> T:
        processed = preprocess_for_vision(image_path)
        image_b64 = base64.b64encode(processed.content).decode("ascii")
        image_url = f"data:{processed.mime_type};base64,{image_b64}"
        metadata = {
            "original_width": processed.original_width,
            "original_height": processed.original_height,
            "processed_width": processed.processed_width,
            "processed_height": processed.processed_height,
            "original_size_bytes": processed.original_size_bytes,
            "processed_size_bytes": processed.processed_size_bytes,
        }

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                content, usage = self._request_json_content(
                    image_url=image_url,
                    prompt=prompt,
                    task_type=task_type,
                    prompt_version=prompt_version,
                    attempt=attempt + 1,
                    metadata=metadata,
                )
                payload = self._parse_json(content)
                return response_model(**payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if attempt >= 1:
                    break
                continue
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= 1:
                    break
                continue
            except httpx.RequestError as exc:
                last_error = exc
                if attempt >= 1:
                    break
                continue
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if status_code in {408, 429} or status_code >= 500:
                    if attempt >= 1:
                        break
                    continue
                raise QwenVisionError(f"Qwen Vision HTTP error: {status_code}") from exc
            except QwenVisionError:
                raise

        if isinstance(last_error, httpx.TimeoutException):
            message = f"Qwen Vision request timed out: {last_error}"
        elif isinstance(last_error, httpx.RequestError):
            message = f"Qwen Vision network request failed: {last_error}"
        elif isinstance(last_error, httpx.HTTPStatusError):
            message = f"Qwen Vision HTTP error: {last_error.response.status_code}"
        else:
            message = f"Qwen Vision returned invalid JSON/schema: {last_error}"
        raise QwenVisionError(message) from last_error

    def _request_json_content(
        self,
        *,
        image_url: str,
        prompt: str,
        task_type: str,
        prompt_version: str,
        attempt: int,
        metadata: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        run_id = new_run_id()
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        status = "failed"
        error_type: str | None = None

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": prompt,
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Analyze the image and return exactly one valid JSON object "
                                        "matching the requested schema. No Markdown."
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url},
                                },
                            ],
                        },
                    ],
                },
                timeout=self.timeout,
                trust_env=False,
            )
            usage = response.json().get("usage", {}) if response.content else {}

            if response.status_code in {401, 403}:
                error_type = f"http_{response.status_code}"
                raise QwenVisionError("Qwen Vision authentication or permission failed.")
            if 400 <= response.status_code < 500 and response.status_code not in {408, 429}:
                error_type = f"http_{response.status_code}"
                raise QwenVisionError(f"Qwen Vision client error: {response.status_code}")
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            status = "success"
            return str(content), usage
        except httpx.TimeoutException:
            error_type = "timeout"
            raise
        except httpx.RequestError:
            error_type = "network"
            raise
        except httpx.HTTPStatusError as exc:
            error_type = f"http_{exc.response.status_code}"
            if exc.response.status_code in {408, 429} or exc.response.status_code >= 500:
                raise
            raise QwenVisionError(f"Qwen Vision HTTP error: {exc.response.status_code}") from exc
        except KeyError as exc:
            error_type = "response_shape"
            raise QwenVisionError("Qwen Vision response missing expected fields.") from exc
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            log_ai_run(
                run_id=run_id,
                provider=self.provider,
                task_type=task_type,
                model_name=self.model,
                prompt_version=prompt_version,
                started_at=started_at,
                status=status,
                latency_ms=latency_ms,
                error_type=error_type,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                metadata={**metadata, "attempt": attempt},
            )

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
