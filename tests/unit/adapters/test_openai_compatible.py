"""OpenAI-compatible adapter against a mocked HTTP layer."""

from __future__ import annotations

import json

import pytest
import responses

from agent_langgraph.adapters.llm.openai_compatible_client import OpenAICompatibleLLMClient
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import Severity

URL = "https://llm.example/v1/chat/completions"
FINDINGS = '{"findings": [{"severity": "high", "file": "a.py", "line": 3, "message": "Leak."}]}'


def _client(sleeps: list[float] | None = None) -> OpenAICompatibleLLMClient:
    record = sleeps if sleeps is not None else []
    return OpenAICompatibleLLMClient(
        api_key="k", base_url="https://llm.example/v1/", model="m", sleep=record.append
    )


def _completion(content: str | None) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 7},
    }


@responses.activate
def test_sends_schema_in_prompt_and_parses_findings():
    call = responses.post(URL, json=_completion(FINDINGS))

    result = _client().review("system rules", "the diff")

    assert [(i.file, i.line, i.severity) for i in result.items] == [("a.py", 3, Severity.HIGH)]
    assert (result.usage.input_tokens, result.usage.output_tokens) == (50, 7)
    request = call.calls[0].request
    assert request.headers["Authorization"] == "Bearer k"
    payload = json.loads(request.body)
    assert payload["model"] == "m"
    assert payload["response_format"] == {"type": "json_object"}
    system, user = payload["messages"]
    assert system["content"].startswith("system rules") and '"findings"' in system["content"]
    assert user == {"role": "user", "content": "the diff"}


@responses.activate
@pytest.mark.parametrize(
    "content",
    [
        f"```json\n{FINDINGS}\n```",
        f"<think>let me look</think>\n{FINDINGS}",
    ],
)
def test_tolerates_wrappers_around_the_json_object(content):
    responses.post(URL, json=_completion(content))
    assert len(_client().review("s", "u").items) == 1


@responses.activate
@pytest.mark.parametrize(
    "content",
    ["Looks good to me!", "", None, '{"findings": [{"severity": "critical"}]}', "[]"],
)
def test_wrong_shape_is_an_error_not_a_clean_review(content):
    responses.post(URL, json=_completion(content))
    with pytest.raises(LLMError):
        _client().review("s", "u")


@responses.activate
def test_retries_rate_limits_then_succeeds():
    responses.post(URL, status=429, headers={"Retry-After": "7"})
    responses.post(URL, status=503)
    responses.post(URL, json=_completion('{"findings": []}'))
    sleeps: list[float] = []

    assert _client(sleeps).review("s", "u").items == []
    assert sleeps[0] == 7 and len(sleeps) == 2


@responses.activate
def test_gives_up_after_repeated_rate_limits():
    responses.post(URL, status=429, body="quota exceeded")
    with pytest.raises(LLMError, match="HTTP 429"):
        _client().review("s", "u")
    assert len(responses.calls) == 4


@responses.activate
def test_client_errors_are_not_retried():
    responses.post(URL, status=401, body="bad key")
    with pytest.raises(LLMError, match="HTTP 401"):
        _client().review("s", "u")
    assert len(responses.calls) == 1


@responses.activate
def test_response_without_choices_is_an_error():
    responses.post(URL, json={"error": "nope"})
    with pytest.raises(LLMError):
        _client().review("s", "u")
