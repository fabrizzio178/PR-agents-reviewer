"""AGGREGATOR node: merges findings from every agent branch and ranks by severity."""

from __future__ import annotations

from agent_langgraph.domain.models import GraphState, ReviewVerdict, Severity

_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def aggregator(state: GraphState) -> dict:
    findings = state.get("findings", [])
    if not findings:
        verdict = ReviewVerdict(
            findings=[],
            max_severity=Severity.LOW,
            requires_human_review=False,
            summary="No issues found.",
        )
        return {"verdict": verdict}

    ranked = sorted(findings, key=lambda f: _ORDER[f.severity], reverse=True)
    max_severity = ranked[0].severity
    summary = "\n".join(f"- [{f.severity.value.upper()}] {f.file}: {f.message}" for f in ranked)
    verdict = ReviewVerdict(
        findings=ranked,
        max_severity=max_severity,
        requires_human_review=max_severity == Severity.HIGH,
        summary=summary,
    )
    return {"verdict": verdict}
