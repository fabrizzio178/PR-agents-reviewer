"""NOTIFY PENDING node: tells the PR a review is waiting for human approval.

Kept separate from `human_review` on purpose: LangGraph re-runs the
interrupted node from its first line on resume, so a side effect placed there
would fire twice. This node has already been checkpointed by then.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.rendering import render_pending
from agent_langgraph.domain.models import GraphState


def make_notify_pending_node(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def notify_pending(state: GraphState) -> dict[str, Any]:
        verdict = state["verdict"]
        assert verdict is not None
        deps.publisher.publish_status(state["target"], render_pending(verdict))
        return {}

    return notify_pending
