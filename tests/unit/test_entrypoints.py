from __future__ import annotations

import json
import logging

import pytest

from agent_langgraph.adapters.llm.openai_compatible_client import OpenAICompatibleLLMClient
from agent_langgraph.domain.models import ReviewTarget, Severity
from agent_langgraph.entrypoints import cli
from agent_langgraph.entrypoints.github_action_entrypoint import (
    target_from_event,
    thread_id_for,
    write_job_results,
)
from agent_langgraph.entrypoints.logging_setup import JsonFormatter
from agent_langgraph.entrypoints.runner import RunOutcome
from agent_langgraph.entrypoints.settings import Settings
from agent_langgraph.entrypoints.wiring import build_llm

BASE_ENV = {"GITHUB_TOKEN": "t", "GEMINI_API_KEY": "k"}


def test_settings_defaults():
    settings = Settings.from_env(BASE_ENV)
    assert (settings.llm.provider, settings.llm.model) == ("gemini", "gemini-2.5-flash")
    assert settings.checkpoint_path == "agent_langgraph.sqlite"
    assert settings.review.gate_severity == Severity.HIGH
    assert settings.review.max_total_chars == 120_000


def test_settings_overrides():
    settings = Settings.from_env(
        BASE_ENV | {"REVIEW_GATE_SEVERITY": "Medium", "REVIEW_MAX_FILE_CHARS": "500"}
    )
    assert settings.review.gate_severity == Severity.MEDIUM
    assert settings.review.max_file_chars == 500


def test_openai_compatible_provider_settings():
    env = {
        "GITHUB_TOKEN": "t",
        "LLM_PROVIDER": "OpenAI-Compatible",
        "LLM_API_KEY": "zen-key",
        "LLM_BASE_URL": "https://opencode.ai/zen/v1",
        "LLM_MODEL": "some-free-model",
    }
    llm = Settings.from_env(env).llm
    assert (llm.provider, llm.api_key, llm.model) == (
        "openai-compatible",
        "zen-key",
        "some-free-model",
    )
    assert llm.base_url == "https://opencode.ai/zen/v1"
    assert isinstance(build_llm(llm), OpenAICompatibleLLMClient)


@pytest.mark.parametrize(
    "env",
    [
        {"GEMINI_API_KEY": "k"},
        {"GITHUB_TOKEN": "t"},
        BASE_ENV | {"REVIEW_MAX_FILE_CHARS": "lots"},
        BASE_ENV | {"REVIEW_MAX_TOTAL_CHARS": "0"},
        BASE_ENV | {"REVIEW_GATE_SEVERITY": "critical"},
        BASE_ENV | {"LLM_PROVIDER": "openai-compatible", "LLM_API_KEY": "k"},
        BASE_ENV | {"LLM_PROVIDER": "something-else"},
    ],
)
def test_settings_reject_missing_or_invalid_values(env):
    with pytest.raises(RuntimeError):
        Settings.from_env(env)


def test_target_comes_from_the_pull_request_event_not_github_sha(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 12, "head": {"sha": "feedface"}}}))
    env = {
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": "acme/shop",
        "GITHUB_SHA": "merge-commit-sha",
        "GITHUB_RUN_ID": "555",
        "GITHUB_RUN_ATTEMPT": "2",
    }
    target = target_from_event(env)

    assert target == ReviewTarget(repo="acme/shop", pr_number=12, head_sha="feedface")
    assert thread_id_for(target, env) == "acme/shop#12@feedfac:555.2"


def test_non_pull_request_event_is_rejected(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"ref": "refs/heads/main"}))
    with pytest.raises(RuntimeError):
        target_from_event({"GITHUB_EVENT_PATH": str(event), "GITHUB_REPOSITORY": "a/b"})


def test_job_results_expose_pause_state_to_the_workflow(tmp_path):
    output, summary = tmp_path / "out", tmp_path / "summary"
    outcome = RunOutcome(
        thread_id="acme/shop#12@feedfac:555.1", paused=True, posted=False, body="B"
    )

    write_job_results(outcome, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)})

    assert output.read_text().splitlines() == [
        "paused=true",
        "thread_id=acme/shop#12@feedfac:555.1",
    ]
    assert "Waiting for approval" in summary.read_text(encoding="utf-8")


def test_cli_parser_shapes():
    parser = cli.build_parser()
    run = parser.parse_args(["run", "--repo", "a/b", "--pr", "3"])
    assert (run.repo, run.pr, run.sha) == ("a/b", 3, None)
    resume = parser.parse_args(["resume", "--thread", "x", "--reject"])
    assert resume.approve is False and resume.reject is True
    with pytest.raises(SystemExit):
        parser.parse_args(["resume", "--thread", "x"])


def test_json_log_lines_carry_extra_fields():
    record = logging.LogRecord(
        "agent_langgraph.graph", logging.INFO, "f", 1, "node finished", (), None
    )
    record.node = "ingest"
    record.duration_ms = 12.5
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "node finished"
    assert payload["node"] == "ingest" and payload["duration_ms"] == 12.5
