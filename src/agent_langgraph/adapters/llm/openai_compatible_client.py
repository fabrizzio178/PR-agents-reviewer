"""OpenAI-compatible adapter: any provider exposing POST {base_url}/chat/completions.

Covers gateways such as OpenCode Zen and OpenRouter, and DeepSeek directly.
These providers differ in how strictly they enforce structured output, so the
schema is also spelled out in the prompt and the reply is always validated
here: a model that answers in the wrong shape yields LLMError, not findings.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import requests

from agent_langgraph.adapters.llm.schema import ReviewSchema, parse_review
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import LLMResult, TokenUsage

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_MAX_DELAY_SECONDS = 30.0
_TIMEOUT_SECONDS = 120

_SCHEMA_INSTRUCTION = (
    "\n\nReply with a single JSON object and nothing else — no prose, no markdown "
    "fences. It must validate against this JSON Schema:\n"
    + json.dumps(ReviewSchema.model_json_schema(), separators=(",", ":"))
)


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._session = session or requests.Session()
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sleep = sleep

    def review(self, system_prompt: str, user_prompt: str) -> LLMResult:
        payload = {
            "model": self._model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt + _SCHEMA_INSTRUCTION},
                {"role": "user", "content": user_prompt},
            ],
        }
        body = self._post(payload)
        try:
            content = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Provider returned a response without a message") from exc

        usage = body.get("usage") or {}
        return LLMResult(
            items=parse_review(_extract_json_object(content)),
            usage=TokenUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        delay = 2.0
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._session.post(
                    self._url, headers=self._headers, json=payload, timeout=_TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise LLMError(f"LLM request failed: {exc}") from exc
            else:
                if response.ok:
                    try:
                        parsed: dict[str, Any] = response.json()
                    except ValueError as exc:
                        raise LLMError("Provider returned a non-JSON response") from exc
                    return parsed
                if response.status_code not in _RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS:
                    raise LLMError(
                        f"LLM request failed: HTTP {response.status_code} {response.text[:200]}"
                    )
                delay = max(delay, _retry_after(response))
            self._sleep(min(delay, _MAX_DELAY_SECONDS))
            delay *= 2
        raise AssertionError("unreachable")


def _retry_after(response: requests.Response) -> float:
    try:
        return float(response.headers.get("Retry-After", 0))
    except ValueError:
        return 0.0


def _extract_json_object(content: str) -> str:
    """Drop anything around the JSON object (code fences, reasoning preambles).

    Only trims; the result still has to pass schema validation.
    """
    start, end = content.find("{"), content.rfind("}")
    return content[start : end + 1] if start != -1 and end > start else content
