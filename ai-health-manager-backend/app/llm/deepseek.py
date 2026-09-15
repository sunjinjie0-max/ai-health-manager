import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.deadline import child_deadline, require_remaining
from app.llm.usage import build_usage_record, record_llm_usage

logger = logging.getLogger(__name__)

T = TypeVar("T")

_TRUNCATED_FINISH_REASONS = {"length", "max_tokens"}
_FILTERED_FINISH_REASONS = {"content_filter", "safety"}
_CODE_FENCE_ONLY = re.compile(r"^```[\w+-]*\s*```$", re.DOTALL)


class LLMResponseError(RuntimeError):
    """A provider response that cannot be safely used by an agent."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        finish_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.finish_reason = finish_reason


def llm_error_code(error: Exception) -> str:
    """Return a stable public error code without exposing provider details."""
    if isinstance(error, LLMResponseError):
        return error.code
    if isinstance(error, TimeoutError):
        return "timeout"
    return "provider_error"


def mark_llm_degraded(state: dict, *, stage: str, error: Exception) -> None:
    """Attach consistent degradation metadata to an agent state."""
    event = {"stage": stage, "code": llm_error_code(error)}
    events = list(state.get("degradation_events") or [])
    events.append(event)
    state["degraded"] = True
    state["degradation_reason"] = event["code"]
    state["degradation_events"] = events


def _response_finish_reason(response: Any) -> str | None:
    for attribute in ("response_metadata", "generation_info", "additional_kwargs"):
        metadata = getattr(response, attribute, None)
        if not isinstance(metadata, dict):
            continue
        finish_reason = metadata.get("finish_reason")
        if finish_reason:
            return str(finish_reason).lower()
    return None


def _response_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "".join(parts).strip()
    return str(content or "").strip()


def _validate_text_response(
    content: str,
    *,
    finish_reason: str | None,
    min_content_chars: int,
) -> str:
    if finish_reason in _FILTERED_FINISH_REASONS:
        raise LLMResponseError(
            "content_filtered",
            f"LLM response was filtered (finish_reason={finish_reason})",
            finish_reason=finish_reason,
        )
    if finish_reason in _TRUNCATED_FINISH_REASONS:
        raise LLMResponseError(
            "truncated_response",
            f"LLM response was truncated (finish_reason={finish_reason})",
            finish_reason=finish_reason,
        )
    if not content or _CODE_FENCE_ONLY.fullmatch(content):
        raise LLMResponseError("empty_response", "LLM returned no usable content")
    if len(content) < min_content_chars:
        raise LLMResponseError(
            "response_too_short",
            f"LLM response contained fewer than {min_content_chars} characters",
            finish_reason=finish_reason,
        )
    return content


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_response(text: str) -> Any:
    stripped = _strip_code_fence(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(
            "invalid_json",
            f"LLM returned invalid JSON at position {exc.pos}",
        ) from exc


class DeepSeekClient:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.deepseek_model,
            openai_api_key=settings.deepseek_api_key,
            openai_api_base=settings.deepseek_base_url,
            temperature=0.7,
            max_tokens=2048,
            request_timeout=settings.deepseek_request_timeout,
        )

    async def _request(
        self,
        system_prompt: str,
        user_message: str,
        *,
        stage: str,
        parser: Callable[[str], T],
        min_content_chars: int,
        max_attempts: int,
        deadline_monotonic: float | None,
        timeout_seconds: float | None,
    ) -> T:
        """Invoke the provider with one bounded retry and strict validation."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        call_deadline = child_deadline(
            deadline_monotonic,
            timeout_seconds or settings.deepseek_request_timeout,
        )
        bounded_attempts = min(max(1, max_attempts), 2)
        last_error: Exception | None = None
        for attempt in range(1, bounded_attempts + 1):
            started_at = time.perf_counter()
            logger.info(
                "[DeepSeek] request start model=%s stage=%s attempt=%d/%d "
                "timeout=%ss system_chars=%d user_chars=%d",
                settings.deepseek_model,
                stage,
                attempt,
                bounded_attempts,
                settings.deepseek_request_timeout,
                len(system_prompt),
                len(user_message),
            )
            try:
                attempt_timeout = require_remaining(
                    call_deadline,
                    settings.llm_attempt_timeout_seconds,
                )
                response = await asyncio.wait_for(
                    self.llm.ainvoke(messages),
                    timeout=attempt_timeout,
                )
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                content = _response_text(response)
                usage_record = build_usage_record(
                    response=response,
                    provider="deepseek",
                    model=settings.deepseek_model,
                    stage=stage,
                    prompt_chars=len(system_prompt) + len(user_message),
                    completion_chars=len(content),
                    latency_ms=elapsed_ms,
                )
                record_llm_usage(usage_record)
                finish_reason = _response_finish_reason(response)
                content = _validate_text_response(
                    content,
                    finish_reason=finish_reason,
                    min_content_chars=min_content_chars,
                )
                parsed = parser(content)
                logger.info(
                    "[DeepSeek] request finished in %.2fs stage=%s attempt=%d "
                    "response_chars=%d finish_reason=%s tokens=%d estimated=%s",
                    elapsed_ms / 1000,
                    stage,
                    attempt,
                    len(content),
                    finish_reason or "unknown",
                    usage_record.total_tokens,
                    usage_record.estimated,
                )
                return parsed
            except Exception as exc:
                last_error = exc
                error_code = getattr(exc, "code", exc.__class__.__name__)
                logger.warning(
                    "[DeepSeek] request rejected stage=%s attempt=%d/%d code=%s "
                    "elapsed=%.2fs",
                    stage,
                    attempt,
                    bounded_attempts,
                    error_code,
                    time.perf_counter() - started_at,
                    exc_info=attempt == bounded_attempts,
                )
                if attempt == bounded_attempts:
                    raise

        raise RuntimeError("DeepSeek request failed without an error") from last_error

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        *,
        stage: str = "deepseek.chat",
        min_content_chars: int = 2,
        max_attempts: int = 2,
        deadline_monotonic: float | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        """Send a chat message and return validated text."""
        return await self._request(
            system_prompt,
            user_message,
            stage=stage,
            parser=lambda text: text,
            min_content_chars=min_content_chars,
            max_attempts=max_attempts,
            deadline_monotonic=deadline_monotonic,
            timeout_seconds=timeout_seconds,
        )

    async def json_chat(
        self,
        system_prompt: str,
        user_message: str,
        *,
        stage: str = "deepseek.json_chat",
        max_attempts: int = 2,
        deadline_monotonic: float | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Send a chat message and return validated, parsed JSON."""
        return await self._request(
            system_prompt,
            user_message,
            stage=stage,
            parser=_parse_json_response,
            min_content_chars=2,
            max_attempts=max_attempts,
            deadline_monotonic=deadline_monotonic,
            timeout_seconds=timeout_seconds,
        )


deepseek_client = DeepSeekClient()
