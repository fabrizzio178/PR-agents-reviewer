"""Gemini adapter with a stand-in SDK client: no network, no API key."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import errors

from agent_langgraph.adapters.llm.gemini_client import GeminiLLMClient
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import Severity


class StubSdk:
    def __init__(self, text: str | None = None, error: Exception | None = None) -> None:
        self._text, self._error = text, error
        self.calls: list[dict] = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        usage = SimpleNamespace(prompt_token_count=120, candidates_token_count=None)
        return SimpleNamespace(text=self._text, usage_metadata=usage)


def _client(sdk: StubSdk) -> GeminiLLMClient:
    return GeminiLLMClient(api_key="unused", model="test-model", client=sdk)  # type: ignore[arg-type]


def test_parses_structured_findings_and_usage():
    sdk = StubSdk(
        '{"findings": [{"severity": "high", "file": "a.py", "line": 3, "message": "Leak."},'
        ' {"severity": "low", "file": "b.py", "line": 0, "message": "Nit."}]}'
    )
    result = _client(sdk).review("system", "user")

    assert [(i.file, i.line, i.severity) for i in result.items] == [
        ("a.py", 3, Severity.HIGH),
        ("b.py", None, Severity.LOW),
    ]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 0)
    config = sdk.calls[0]["config"]
    assert sdk.calls[0]["model"] == "test-model"
    assert config.system_instruction == "system"
    assert config.response_mime_type == "application/json"


def test_empty_findings_list_is_a_valid_clean_result():
    assert _client(StubSdk('{"findings": []}')).review("s", "u").items == []


@pytest.mark.parametrize(
    "text",
    [
        "CLEAN",
        "",
        None,
        '{"findings": [{"severity": "critical", "file": "a.py", "message": "x"}]}',
        '{"something_else": []}',
    ],
)
def test_output_that_violates_the_schema_is_an_error_not_clean(text):
    with pytest.raises(LLMError):
        _client(StubSdk(text)).review("s", "u")


def test_api_errors_become_llm_errors():
    sdk = StubSdk(error=errors.APIError(429, {"error": {"message": "quota"}}))
    with pytest.raises(LLMError, match="Gemini request failed"):
        _client(sdk).review("s", "u")
