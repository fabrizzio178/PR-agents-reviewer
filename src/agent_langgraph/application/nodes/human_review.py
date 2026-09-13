"""HUMAN-IN-THE-LOOP node: pauses the graph until a human approves posting.

Uses LangGraph's `interrupt()` — the graph run genuinely suspends here and
resumes later (in a different process/invocation) once a Command(resume=...)
is sent, which is why this only works with a checkpointer configured.
"""

from __future__ import annotations

from langgraph.types import interrupt

from agent_langgraph.domain.models import GraphState


def human_review(state: GraphState) -> dict:
    verdict = state["verdict"]
    assert verdict is not None
    decision = interrupt(
        {
            "question": "High-severity findings detected. Approve posting this review?",
            "summary": verdict.summary,
        }
    )
    return {"human_approved": bool(decision.get("approved", False))}
