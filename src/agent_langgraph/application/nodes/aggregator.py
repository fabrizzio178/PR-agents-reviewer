"""AGGREGATOR node: merges findings from every branch, dedupes and ranks by severity."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.models import Finding, GraphState, ReviewVerdict, Severity


def make_aggregator(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def aggregator(state: GraphState) -> dict[str, Any]:
        ranked = sorted(
            _dedupe(state.get("findings", [])),
            key=lambda f: (-f.severity.rank, f.file, f.line or 0),
        )
        max_severity = ranked[0].severity if ranked else Severity.LOW
        verdict = ReviewVerdict(
            findings=ranked,
            max_severity=max_severity,
            requires_human_review=bool(ranked)
            and max_severity.rank >= deps.config.gate_severity.rank,
        )
        return {"verdict": verdict}

    return aggregator


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse the same issue reported by two agents, keeping the higher severity."""
    best: dict[tuple[str, int | None, str], Finding] = {}
    for finding in findings:
        key = (finding.file, finding.line, finding.message.strip().lower())
        current = best.get(key)
        if current is None or finding.severity.rank > current.severity.rank:
            best[key] = finding
    return list(best.values())
