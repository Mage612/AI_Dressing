import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app import settings
from app.services.ai_run_logger import log_ai_run, new_run_id


T = TypeVar("T", bound=BaseModel)
DEBUG_DIR = Path(__file__).resolve().parents[2] / "debug_artifacts" / "styling"


class DeepSeekError(RuntimeError):
    pass


class DeepSeekProvider:
    provider = "deepseek"
    base_url = "https://api.deepseek.com/v1"

    def __init__(self) -> None:
        if settings.STYLING_PROVIDER == "dashscope":
            settings.require_qwen_vision_settings()
            self.provider = "dashscope"
            self.base_url = settings.DASHSCOPE_BASE_URL
            self.api_key = settings.DASHSCOPE_API_KEY
            self.model = settings.STYLING_MODEL or "qwen-plus"
        else:
            settings.require_deepseek_settings()
            self.provider = "deepseek"
            self.base_url = "https://api.deepseek.com/v1"
            self.api_key = settings.DEEPSEEK_API_KEY
            self.model = settings.STYLING_MODEL or settings.DEEPSEEK_MODEL
        self.timeout = settings.MODEL_TIMEOUT_SECONDS

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        task_type: str,
        prompt_version: str,
        skill_version: str,
        response_model: type[T],
        session_id: str,
        recommendation_id: Optional[str] = None,
    ) -> tuple[T, dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                content, metadata = self._request(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    task_type=task_type,
                    prompt_version=prompt_version,
                    skill_version=skill_version,
                    session_id=session_id,
                    recommendation_id=recommendation_id,
                    attempt=attempt + 1,
                )
                payload = self._parse_json(content)
                parsed = response_model(**payload)
                metadata["validation_result"] = "ok"
                return parsed, metadata
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if attempt >= 1:
                    break
                user_prompt = (
                    user_prompt
                    + "\n\nPrevious response failed JSON/schema validation. "
                    + "Return exactly one valid JSON object matching the schema."
                )
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = exc
                if attempt >= 1:
                    break
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code in {408, 429} or exc.response.status_code >= 500:
                    if attempt >= 1:
                        break
                    continue
                raise DeepSeekError(f"DeepSeek HTTP error: {exc.response.status_code}") from exc

        if isinstance(last_error, httpx.TimeoutException):
            raise DeepSeekError("DeepSeek request timed out.") from last_error
        if isinstance(last_error, httpx.RequestError):
            raise DeepSeekError("DeepSeek network request failed.") from last_error
        if isinstance(last_error, httpx.HTTPStatusError):
            raise DeepSeekError(f"DeepSeek HTTP error: {last_error.response.status_code}") from last_error
        raise DeepSeekError(f"DeepSeek returned invalid JSON/schema: {last_error}") from last_error

    def _request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        task_type: str,
        prompt_version: str,
        skill_version: str,
        session_id: str,
        recommendation_id: Optional[str],
        attempt: int,
    ) -> tuple[str, dict[str, Any]]:
        run_id = new_run_id()
        started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        usage: dict[str, Any] = {}
        status = "failed"
        error_type: str | None = None

        try:
            max_tokens = min(settings.MODEL_MAX_TOKENS, 2200) if task_type == "refine_outfit" else settings.MODEL_MAX_TOKENS
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "max_tokens": max_tokens,
                    "temperature": 0.4,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=self.timeout,
                trust_env=False,
            )
            usage = response.json().get("usage", {}) if response.content else {}
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            status = "success"
            self._write_raw_artifact(run_id, task_type, str(content))
            return str(content), {
                "run_id": run_id,
                "model": self.model,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "attempt": attempt,
            }
        except httpx.TimeoutException:
            error_type = "timeout"
            raise
        except httpx.RequestError:
            error_type = "network"
            raise
        except httpx.HTTPStatusError as exc:
            error_type = f"http_{exc.response.status_code}"
            raise
        except KeyError as exc:
            error_type = "response_shape"
            raise DeepSeekError("DeepSeek response missing expected fields.") from exc
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            log_ai_run(
                run_id=run_id,
                provider=self.provider,
                task_type=task_type,
                model_name=self.model,
                prompt_version=prompt_version,
                skill_version=skill_version,
                session_id=session_id,
                recommendation_id=recommendation_id,
                started_at=started_at,
                status=status,
                latency_ms=latency_ms,
                error_type=error_type,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                metadata={"attempt": attempt},
            )
            if settings.STYLING_DEBUG:
                print(
                    "[styling-debug] "
                    f"session_id={session_id} run_id={run_id} model={self.model} "
                    f"prompt_version={prompt_version} skill_version={skill_version} "
                    f"latency_ms={latency_ms} input_tokens={usage.get('prompt_tokens')} "
                    f"output_tokens={usage.get('completion_tokens')} validation=pending"
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

    @staticmethod
    def _write_raw_artifact(run_id: str, task_type: str, content: str) -> None:
        if not settings.STYLING_DEBUG:
            return
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        safe_task = "".join(ch for ch in task_type if ch.isalnum() or ch in {"_", "-"})
        (DEBUG_DIR / f"{safe_task}_{run_id}.json").write_text(content, encoding="utf-8")
