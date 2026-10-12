"""POST node: publishes the review — a summary comment plus inline comments.

A finding goes inline only when its line is inside a diff hunk (GitHub
rejects comments anywhere else); every finding is in the summary regardless.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.rendering import render_inline, render_review, render_withheld
from agent_langgraph.domain.diff import commentable_lines
from agent_langgraph.domain.models import GraphState, InlineComment


def make_post_node(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def post(state: GraphState) -> dict[str, Any]:
        target = state["target"]
        verdict = state["verdict"]
        assert verdict is not None

        if state.get("human_approved") is False:
            body = render_withheld(verdict)
            deps.publisher.publish_status(target, body)
            return {"comment_body": body, "posted": False}

        body = render_review(state)
        deps.publisher.publish_status(target, body)
        inline = _inline_comments(state)
        if inline:
            deps.publisher.publish_inline(target, inline)
        return {"comment_body": body, "posted": True}

    return post


def _inline_comments(state: GraphState) -> list[InlineComment]:
    verdict = state["verdict"]
    assert verdict is not None
    lines_by_path = {f.path: commentable_lines(f.patch) for f in state["files"]}
    return [
        InlineComment(path=f.file, line=f.line, body=render_inline(f))
        for f in verdict.findings
        if f.line is not None and f.line in lines_by_path.get(f.file, set())
    ]
