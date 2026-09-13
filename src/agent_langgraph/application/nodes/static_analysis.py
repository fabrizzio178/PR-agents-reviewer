"""STATIC ANALYSIS node: runs linters against the changed files. No LLM involved."""

from __future__ import annotations

from collections.abc import Callable

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.models import GraphState


def make_static_analysis_node(deps: GraphDeps) -> Callable[[GraphState], dict]:
    def static_analysis(state: GraphState) -> dict:
        output = deps.static_analyzer.run(state["files"])
        return {"static_analysis_output": output}

    return static_analysis
