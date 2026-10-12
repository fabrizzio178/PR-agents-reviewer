"""HUMAN-IN-THE-LOOP node: pauses the graph until a human approves posting.

Uses LangGraph's `interrupt()` — the graph run genuinely suspends here and
resumes later (in a different process/invocation) once a Command(resume=...)
is sent, which is why this only works with a checkpointer configured.

This node must stay free of external side effects: on resume it runs again
from the top.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent_langgraph.application.rendering import render_review
from agent_langgraph.domain.models import GraphState


def human_review(state: GraphState) -> dict[str, Any]:
    verdict = state["verdict"]
    assert verdict is not None
    decision = interrupt(
        {
            "question": (
                f"{verdict.max_severity.value.capitalize()}-severity findings detected. "
                "Approve posting this review?"
            ),
            "review": render_review(state),
        }
    )
    approved = decision.get("approved", False) if isinstance(decision, dict) else False
    return {"human_approved": bool(approved)}
