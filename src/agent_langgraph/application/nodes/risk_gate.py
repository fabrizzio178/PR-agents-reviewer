"""RISK GATE: conditional edge deciding whether to auto-post or wait for a human.

This is a routing function, not a node with side effects — it reads the
verdict the aggregator already computed and picks the next node.
"""

from __future__ import annotations

from agent_langgraph.domain.models import GraphState


def route_from_risk_gate(state: GraphState) -> str:
    verdict = state["verdict"]
    assert verdict is not None
    return "notify_pending" if verdict.requires_human_review else "post"
