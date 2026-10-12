"""Unit tests for individual nodes, driven with a hand-built state."""

from __future__ import annotations

import pytest

from agent_langgraph.application.deps import ReviewConfig
from agent_langgraph.application.nodes.aggregator import make_aggregator
from agent_langgraph.application.nodes.ingest import make_ingest_node
from agent_langgraph.application.nodes.notify_pending import make_notify_pending_node
from agent_langgraph.application.nodes.post import make_post_node
from agent_langgraph.application.nodes.review_agent import make_review_agent
from agent_langgraph.application.nodes.risk_gate import route_from_risk_gate
from agent_langgraph.application.nodes.supervisor import route_from_supervisor, supervisor
from agent_langgraph.application.prompts import SECURITY_PROMPT, render_diff
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import FileChange, Finding, ReviewVerdict, Severity
from fakes import HIGH_SECRET, MEDIUM_BUG, PY_FILE, TARGET, FakeLLM, make_harness


def _files(*paths: str) -> dict:
    return {"files": [FileChange(path=p, patch="", additions=1, deletions=0) for p in paths]}


def _finding(severity: Severity, line: int | None = 2, message: str = "issue") -> Finding:
    return Finding(
        agent="security", file="app/config.py", line=line, message=message, severity=severity
    )


# --- supervisor -----------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/main.py", ["static_analysis", "security", "code_arch"]),
        ("web/app.tsx", ["security", "code_arch"]),
        ("Dockerfile", ["security"]),
        ("deploy/Dockerfile.prod", ["security"]),
        ("config/.env.production", ["security"]),
        ("requirements.txt", ["security"]),
        ("package.json", ["security"]),
        (".github/workflows/ci.yml", ["security"]),
        ("infra/main.tf", ["security"]),
        ("README.md", []),
        ("docs/logo.png", []),
    ],
)
def test_supervisor_routing(path, expected):
    assert supervisor(_files(path))["active_agents"] == expected


def test_docs_only_routes_straight_to_aggregator():
    assert route_from_supervisor({"active_agents": []}) == ["aggregator"]
    assert route_from_supervisor({"active_agents": ["security"]}) == ["security"]


# --- ingest ---------------------------------------------------------------


def test_ingest_applies_the_diff_budget():
    h = make_harness(config=ReviewConfig(max_file_chars=30, max_total_chars=30))
    result = make_ingest_node(h.deps)({"target": TARGET})
    assert result["truncated_files"] == ["app/config.py"]
    assert len(result["files"][0].patch) <= 30


# --- review agent ---------------------------------------------------------


def test_review_agent_attributes_findings_and_reports_usage():
    h = make_harness(llm=FakeLLM(security=[HIGH_SECRET]))
    result = make_review_agent("security", SECURITY_PROMPT, h.deps)({"files": [PY_FILE]})

    [finding] = result["findings"]
    assert (finding.agent, finding.line, finding.severity) == ("security", 2, Severity.HIGH)
    assert result["usage"].input_tokens == 100


def test_review_agent_turns_llm_failure_into_an_agent_error():
    h = make_harness(llm=FakeLLM(security=LLMError("schema mismatch")))
    result = make_review_agent("security", SECURITY_PROMPT, h.deps)({"files": [PY_FILE]})
    assert result == {"agent_errors": ["security: schema mismatch"]}


def test_diff_reaches_the_llm_delimited_and_numbered():
    rendered = render_diff([PY_FILE, FileChange("logo.png", "", 0, 0)])
    assert rendered.startswith("<diff>") and rendered.endswith("</diff>")
    assert '<file path="app/config.py">' in rendered
    assert '    2 +API_KEY = "hunter2"' in rendered
    assert "logo.png" not in rendered


# --- aggregator and risk gate ---------------------------------------------


def test_aggregator_ranks_by_severity_and_gates_on_high():
    h = make_harness()
    state = {"findings": [_finding(Severity.LOW, 3), _finding(Severity.HIGH, 2)]}
    verdict = make_aggregator(h.deps)(state)["verdict"]

    assert [f.severity for f in verdict.findings] == [Severity.HIGH, Severity.LOW]
    assert verdict.max_severity == Severity.HIGH
    assert verdict.requires_human_review is True
    assert route_from_risk_gate({"verdict": verdict}) == "notify_pending"


def test_aggregator_without_findings_never_gates():
    h = make_harness(config=ReviewConfig(gate_severity=Severity.LOW))
    verdict = make_aggregator(h.deps)({})["verdict"]

    assert verdict.findings == [] and verdict.requires_human_review is False
    assert route_from_risk_gate({"verdict": verdict}) == "post"


def test_aggregator_dedupes_keeping_the_higher_severity():
    h = make_harness()
    state = {"findings": [_finding(Severity.LOW), _finding(Severity.MEDIUM, message="Issue ")]}
    verdict = make_aggregator(h.deps)(state)["verdict"]
    assert [f.severity for f in verdict.findings] == [Severity.MEDIUM]


# --- publishing nodes -----------------------------------------------------


def _state(findings: list[Finding], **extra) -> dict:
    verdict = ReviewVerdict(
        findings=findings,
        max_severity=findings[0].severity if findings else Severity.LOW,
        requires_human_review=False,
    )
    return {"target": TARGET, "files": [PY_FILE], "verdict": verdict, **extra}


def test_post_puts_only_in_diff_findings_inline():
    h = make_harness()
    findings = [
        _finding(Severity.MEDIUM, line=2),
        _finding(Severity.MEDIUM, line=50, message="outside the diff"),
        _finding(Severity.LOW, line=None, message="file-level"),
        Finding("security", "other.py", "unknown file", Severity.LOW, line=2),
    ]
    result = make_post_node(h.deps)(_state(findings))

    assert result["posted"] is True
    assert [(c.path, c.line) for c in h.publisher.inline[0]] == [("app/config.py", 2)]
    assert "outside the diff" in result["comment_body"]
    assert "file-level" in result["comment_body"]


def test_post_withholds_findings_when_rejected():
    h = make_harness()
    state = _state([_finding(Severity.HIGH, message="the secret detail")], human_approved=False)
    result = make_post_node(h.deps)(state)

    assert result["posted"] is False
    assert "the secret detail" not in h.publisher.statuses[0]
    assert h.publisher.inline == []


def test_notify_pending_publishes_a_placeholder_without_details():
    h = make_harness()
    make_notify_pending_node(h.deps)(_state([_finding(Severity.HIGH, message="the detail")]))

    [status] = h.publisher.statuses
    assert "1 high" in status and "the detail" not in status


def test_medium_bug_fixture_is_inside_the_diff():
    # Guards the fixtures the integration tests rely on.
    assert MEDIUM_BUG.line == 4
