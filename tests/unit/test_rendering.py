from agent_langgraph.application.rendering import render_inline, render_review, sanitize
from agent_langgraph.domain.models import Finding, ReviewVerdict, Severity, TokenUsage
from fakes import PY_FILE, TARGET


def _state(findings, **extra):
    verdict = ReviewVerdict(
        findings=findings,
        max_severity=findings[0].severity if findings else Severity.LOW,
        requires_human_review=False,
    )
    return {"target": TARGET, "files": [PY_FILE], "verdict": verdict, **extra}


def test_sanitize_neutralizes_mentions_and_collapses_whitespace():
    cleaned = sanitize("ping @octocat\n\n# Heading\tnow")
    assert "@octocat" not in cleaned
    assert "\n" not in cleaned
    assert cleaned.endswith("# Heading now")


def test_sanitize_bounds_length_and_blocks_html_comments():
    assert len(sanitize("a" * 2000)) == 500
    assert "<!--" not in sanitize("<!-- pr-review-agent:status -->")


def test_review_groups_findings_by_severity_with_locations():
    findings = [
        Finding("security", "a.py", "Leaked key.", Severity.HIGH, line=3),
        Finding("code_arch", "b.py", "Dead code.", Severity.LOW),
    ]
    body = render_review(_state(findings, active_agents=["security", "code_arch"]))

    assert "Found 1 high, 1 low." in body
    assert body.index("High") < body.index("Low")
    assert "- `a.py:3` — Leaked key. _(security)_" in body
    assert "- `b.py` — Dead code. _(code_arch)_" in body
    assert "Reviewed `abc1234`" in body


def test_review_with_errors_and_no_findings_is_not_clean():
    body = render_review(_state([], agent_errors=["security: boom"]))
    assert "No issues found" not in body
    assert "Incomplete review" in body and "security: boom" in body


def test_review_lists_truncated_files_and_token_usage():
    body = render_review(_state([], truncated_files=["big.py"], usage=TokenUsage(1200, 80)))
    assert "`big.py`" in body
    assert "tokens: 1200 in / 80 out" in body


def test_inline_comment_carries_severity_and_agent():
    body = render_inline(Finding("ruff", "a.py", "F401: unused import", Severity.MEDIUM, line=1))
    assert "Medium" in body and "`ruff`" in body and "F401" in body
