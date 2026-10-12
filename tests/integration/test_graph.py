"""End-to-end graph runs over fake ports: every path in docs/SPEC.md §6."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent_langgraph.application.graph import build_graph
from agent_langgraph.domain.errors import LLMError, StaticAnalysisError
from agent_langgraph.domain.models import Finding, ReviewItem, Severity
from agent_langgraph.entrypoints.runner import (
    NoPausedReviewError,
    open_checkpointer,
    resume_review,
    start_review,
)
from fakes import (
    HIGH_SECRET,
    MEDIUM_BUG,
    PY_FILE,
    README_FILE,
    TARGET,
    FakeAnalyzer,
    FakeDiffProvider,
    FakeLLM,
    make_harness,
)


def run(harness, thread_id="t1", checkpointer=None):
    graph = build_graph(harness.deps, checkpointer=checkpointer or InMemorySaver())
    return graph, start_review(graph, TARGET, thread_id)


def test_clean_python_change_posts_no_issues():
    h = make_harness()
    _, outcome = run(h)

    assert outcome.paused is False and outcome.posted is True
    assert len(h.llm.prompts) == 2
    assert h.analyzer.calls == 1
    assert len(h.publisher.statuses) == 1
    assert "No issues found" in h.publisher.statuses[0]
    assert h.publisher.inline == []


def test_docs_only_change_calls_no_reviewer():
    h = make_harness(files=[README_FILE])
    _, outcome = run(h)

    assert outcome.posted is True
    assert h.llm.prompts == []
    assert h.analyzer.calls == 0
    assert "No issues found" in outcome.body
    assert "none (no reviewable changes)" in outcome.body


def test_medium_findings_post_without_human_gate():
    off_diff = ReviewItem(
        file="app/config.py", line=99, message="Module is too large.", severity=Severity.LOW
    )
    h = make_harness(llm=FakeLLM(security=[MEDIUM_BUG], code_arch=[off_diff]))
    _, outcome = run(h)

    assert outcome.paused is False and outcome.posted is True
    assert "Prints a secret" in outcome.body and "Module is too large" in outcome.body
    # Only the finding whose line is inside the diff becomes an inline comment.
    [inline] = h.publisher.inline
    assert [(c.path, c.line) for c in inline] == [("app/config.py", 4)]
    assert "tokens: 200 in / 20 out" in outcome.body


def test_high_finding_pauses_then_publishes_on_approval():
    h = make_harness(llm=FakeLLM(security=[HIGH_SECRET]))
    graph, outcome = run(h)

    assert outcome.paused is True and outcome.posted is False
    assert "Hardcoded API key" in outcome.body
    # The PR only sees a placeholder until a human approves.
    assert len(h.publisher.statuses) == 1
    assert "withheld until a maintainer approves" in h.publisher.statuses[0]
    assert "Hardcoded API key" not in h.publisher.statuses[0]
    assert h.publisher.inline == []

    resumed = resume_review(graph, "t1", approved=True)

    assert resumed.paused is False and resumed.posted is True
    assert len(h.publisher.statuses) == 2
    assert "Hardcoded API key" in h.publisher.statuses[1]
    assert len(h.publisher.inline) == 1
    assert len(h.llm.prompts) == 2, "resuming must not call the LLM again"


def test_high_finding_rejected_is_withheld():
    h = make_harness(llm=FakeLLM(security=[HIGH_SECRET]))
    graph, _ = run(h)

    resumed = resume_review(graph, "t1", approved=False)

    assert resumed.posted is False
    assert "chose not to publish" in h.publisher.statuses[-1]
    assert "Hardcoded API key" not in h.publisher.statuses[-1]
    assert h.publisher.inline == []


def test_gate_severity_is_configurable():
    from agent_langgraph.application.deps import ReviewConfig

    h = make_harness(
        llm=FakeLLM(security=[MEDIUM_BUG]), config=ReviewConfig(gate_severity=Severity.MEDIUM)
    )
    _, outcome = run(h)
    assert outcome.paused is True


def test_failed_agent_is_reported_never_clean():
    h = make_harness(llm=FakeLLM(security=LLMError("quota exhausted")))
    _, outcome = run(h)

    assert outcome.posted is True
    assert "No issues found" not in outcome.body
    assert "Incomplete review" in outcome.body
    assert "security: quota exhausted" in outcome.body


def test_failed_static_analysis_degrades():
    h = make_harness(analyzer=FakeAnalyzer(error=StaticAnalysisError("ruff missing")))
    _, outcome = run(h)

    assert "static_analysis: ruff missing" in outcome.body


def test_static_findings_are_merged_and_deduplicated():
    lint = Finding(
        agent="ruff",
        file="app/config.py",
        line=4,
        message="Prints a secret to stdout.",
        severity=Severity.LOW,
    )
    h = make_harness(llm=FakeLLM(security=[MEDIUM_BUG]), analyzer=FakeAnalyzer(findings=[lint]))
    _, outcome = run(h)

    assert outcome.body.count("Prints a secret to stdout.") == 1
    assert "Found 1 medium." in outcome.body


def test_second_run_on_same_pr_does_not_accumulate_findings():
    h = make_harness(llm=FakeLLM(security=[MEDIUM_BUG]))
    checkpointer = InMemorySaver()
    _, first = run(h, "run-1", checkpointer)
    _, second = run(h, "run-2", checkpointer)

    assert first.body == second.body
    assert "Found 1 medium." in second.body


def test_transient_ingest_failure_is_retried():
    diff = FakeDiffProvider([PY_FILE], failures_before_success=1)
    h = make_harness(diff=diff)
    _, outcome = run(h)

    assert diff.calls == 2
    assert outcome.posted is True


def test_oversized_diff_is_truncated_and_reported():
    from agent_langgraph.application.deps import ReviewConfig

    h = make_harness(config=ReviewConfig(max_file_chars=30, max_total_chars=30))
    _, outcome = run(h)

    assert "Not fully reviewed" in outcome.body
    assert "`app/config.py`" in outcome.body


def test_resume_in_a_new_process_from_sqlite(tmp_path):
    """The CI flow: `analyze` pauses, a later `approve` job resumes from the file."""
    db = str(tmp_path / "checkpoint.sqlite")

    first = make_harness(llm=FakeLLM(security=[HIGH_SECRET]))
    with open_checkpointer(db) as checkpointer:
        graph = build_graph(first.deps, checkpointer=checkpointer)
        assert start_review(graph, TARGET, "ci-thread").paused is True

    # Brand-new adapters and graph object, as in a separate job. Any attempt
    # to re-fetch the diff or re-ask the LLM would fail loudly.
    second = make_harness(
        diff=FakeDiffProvider([], failures_before_success=99),
        llm=FakeLLM(security=LLMError("must not be called")),
    )
    with open_checkpointer(db) as checkpointer:
        graph = build_graph(second.deps, checkpointer=checkpointer)
        outcome = resume_review(graph, "ci-thread", approved=True)

    assert outcome.posted is True
    assert "Hardcoded API key" in second.publisher.statuses[-1]
    assert [(c.path, c.line) for c in second.publisher.inline[0]] == [("app/config.py", 2)]
    assert second.llm.prompts == [] and second.diff.calls == 0


def test_resume_without_a_paused_review_fails():
    h = make_harness()
    graph, _ = run(h)
    with pytest.raises(NoPausedReviewError):
        resume_review(graph, "t1", approved=True)
    with pytest.raises(NoPausedReviewError):
        resume_review(graph, "unknown-thread", approved=True)
