"""POST node: publishes the review as a comment on the commit."""

from __future__ import annotations

from collections.abc import Callable

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.models import GraphState


def make_post_node(deps: GraphDeps) -> Callable[[GraphState], dict]:
    def post(state: GraphState) -> dict:
        if state.get("human_approved") is False:
            return {"posted": False}

        body = _render_comment(state)
        deps.comment_poster.post_comment(state["repo"], state["commit_sha"], body)
        return {"comment_body": body, "posted": True}

    return post


def _render_comment(state: GraphState) -> str:
    verdict = state["verdict"]
    assert verdict is not None
    if not verdict.findings:
        return "**PR Review Agent** — no issues found."
    header = f"**PR Review Agent** — {verdict.max_severity.value.upper()} severity findings:\n\n"
    return header + verdict.summary
