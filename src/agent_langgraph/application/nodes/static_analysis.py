"""STATIC ANALYSIS node: runs linters against the changed files. No LLM involved.

Runs as one branch of the supervisor's fan-out and feeds the same `findings`
reducer as the LLM agents, so its results are ranked and published with theirs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.errors import StaticAnalysisError
from agent_langgraph.domain.models import GraphState

logger = logging.getLogger(__name__)


def make_static_analysis_node(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def static_analysis(state: GraphState) -> dict[str, Any]:
        try:
            return {"findings": deps.static_analyzer.run(state["files"])}
        except StaticAnalysisError as exc:
            logger.warning("static analysis failed: %s", exc)
            return {"agent_errors": [f"static_analysis: {exc}"]}

    return static_analysis
