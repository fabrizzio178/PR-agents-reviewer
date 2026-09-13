from agent_langgraph.application.nodes.aggregator import aggregator
from agent_langgraph.domain.models import Finding, Severity


def test_no_findings_means_no_human_review():
    result = aggregator({"findings": []})
    verdict = result["verdict"]
    assert verdict.requires_human_review is False
    assert verdict.max_severity == Severity.LOW


def test_high_severity_finding_requires_human_review():
    findings = [
        Finding(
            agent="security", file="auth.py", message="hardcoded secret", severity=Severity.HIGH
        ),
        Finding(
            agent="code_arch", file="utils.py", message="unused import", severity=Severity.LOW
        ),
    ]
    result = aggregator({"findings": findings})
    verdict = result["verdict"]
    assert verdict.requires_human_review is True
    assert verdict.max_severity == Severity.HIGH
    assert verdict.findings[0].severity == Severity.HIGH
