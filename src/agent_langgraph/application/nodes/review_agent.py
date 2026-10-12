"""LLM review agents: one node factory, specialised by name and system prompt.

A failing agent degrades the review instead of aborting the graph: the error
lands in `agent_errors` and the published summary says the review is
incomplete, so a failure can never be mistaken for a clean diff.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.prompts import render_diff
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import Finding, GraphState

logger = logging.getLogger(__name__)


def make_review_agent(
    name: str, system_prompt: str, deps: GraphDeps
) -> Callable[[GraphState], dict[str, Any]]:
    def review_agent(state: GraphState) -> dict[str, Any]:
        try:
            result = deps.llm.review(system_prompt, render_diff(state["files"]))
        except LLMError as exc:
            logger.warning("agent %s failed: %s", name, exc)
            return {"agent_errors": [f"{name}: {exc}"]}

        findings = [
            Finding(
                agent=name,
                file=item.file,
                line=item.line,
                message=item.message,
                severity=item.severity,
            )
            for item in result.items
        ]
        return {"findings": findings, "usage": result.usage}

    return review_agent
