"""Per-repo `.pr-review.yml`: parsing, loading from the base branch, and its effects."""

from __future__ import annotations

import base64

import pytest
import responses
from langgraph.checkpoint.memory import InMemorySaver

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.adapters.github.rest_config_provider import (
    GitHubRestConfigProvider,
    parse_config,
)
from agent_langgraph.application.graph import build_graph
from agent_langgraph.application.nodes.ingest import is_ignored
from agent_langgraph.domain.errors import ConfigError
from agent_langgraph.domain.models import FileChange, RepoConfig, Severity
from agent_langgraph.entrypoints.runner import start_review
from fakes import MEDIUM_BUG, PY_FILE, TARGET, FakeLLM, make_harness

API = "https://api.github.com/repos/acme/shop"
FULL = """
reviewers:
  code_arch: false
ignore:
  - "migrations/"
  - "*.lock"
gate_severity: medium
rules:
  - "Never log   email addresses."
"""


def _run(harness):
    graph = build_graph(harness.deps, checkpointer=InMemorySaver())
    return start_review(graph, TARGET, "t")


# --- parsing --------------------------------------------------------------


def test_parses_a_full_config():
    config = parse_config(FULL)
    assert config == RepoConfig(
        disabled_reviewers=["code_arch"],
        ignore=["migrations/", "*.lock"],
        rules=["Never log email addresses."],
        gate_severity=Severity.MEDIUM,
    )


def test_empty_file_means_defaults():
    assert parse_config("") == RepoConfig()


@pytest.mark.parametrize(
    "text",
    [
        "reviewers: {secruity: false}",
        "unknown_key: 1",
        "gate_severity: critical",
        "rules: not-a-list",
        "rules: ['" + "x" * 301 + "']",
        "reviewers: [unclosed",
        "- just\n- a list",
    ],
)
def test_invalid_config_is_rejected_not_guessed(text):
    with pytest.raises(ConfigError):
        parse_config(text)


# --- loading from GitHub --------------------------------------------------


@responses.activate
def test_config_is_read_from_the_base_commit_not_the_pr_head():
    responses.get(f"{API}/pulls/7", json={"base": {"sha": "base123"}, "head": {"sha": "evil"}})
    content = responses.get(
        f"{API}/contents/.pr-review.yml",
        json={"encoding": "base64", "content": base64.b64encode(FULL.encode()).decode()},
        match=[responses.matchers.query_param_matcher({"ref": "base123"})],
    )

    config = GitHubRestConfigProvider(GitHubRestClient("t")).load(TARGET)

    assert config.disabled_reviewers == ["code_arch"]
    assert content.call_count == 1


@responses.activate
def test_missing_config_file_means_defaults():
    responses.get(f"{API}/pulls/7", json={"base": {"sha": "base123"}})
    responses.get(f"{API}/contents/.pr-review.yml", status=404)

    assert GitHubRestConfigProvider(GitHubRestClient("t")).load(TARGET) == RepoConfig()


# --- effects on the review ------------------------------------------------


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        ("migrations/0001_init.py", True),
        ("app/migrations/0001.py", False),
        ("uv.lock", True),
        ("deps/poetry.lock", True),
        ("app/main.py", False),
    ],
)
def test_ignore_patterns(path, ignored):
    assert is_ignored(path, ["migrations/", "*.lock"]) is ignored


def test_ignored_files_never_reach_a_reviewer():
    migration = FileChange("migrations/0001.py", PY_FILE.patch, 3, 0)
    h = make_harness(files=[migration], repo_config=RepoConfig(ignore=["migrations/"]))
    outcome = _run(h)

    assert h.llm.prompts == [] and h.analyzer.calls == 0
    assert "No issues found" in outcome.body


def test_disabled_reviewer_is_not_run():
    h = make_harness(repo_config=RepoConfig(disabled_reviewers=["code_arch", "static_analysis"]))
    outcome = _run(h)

    assert len(h.llm.prompts) == 1 and h.analyzer.calls == 0
    assert "agents: security" in outcome.body


def test_repo_rules_reach_the_llm_system_prompt_only():
    h = make_harness(repo_config=RepoConfig(rules=["Never log email addresses."]))
    _run(h)

    for system_prompt, user_prompt in h.llm.prompts:
        assert "- Never log email addresses." in system_prompt
        assert "Never log email" not in user_prompt


def test_repo_gate_severity_overrides_the_default():
    h = make_harness(
        llm=FakeLLM(security=[MEDIUM_BUG]), repo_config=RepoConfig(gate_severity=Severity.MEDIUM)
    )
    assert _run(h).paused is True


def test_invalid_config_falls_back_to_defaults_and_says_so():
    h = make_harness(repo_config=ConfigError("reviewers.secruity: Extra inputs are not permitted"))
    outcome = _run(h)

    assert outcome.posted is True
    assert len(h.llm.prompts) == 2, "defaults apply: every reviewer still runs"
    assert "`.pr-review.yml` is invalid and was ignored" in outcome.body
    assert "reviewers.secruity" in outcome.body
