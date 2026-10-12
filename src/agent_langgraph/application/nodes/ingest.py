"""INGEST node: fetches the PR's diff and caps it to the configured budget."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.diff import apply_budget
from agent_langgraph.domain.models import GraphState


def make_ingest_node(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def ingest(state: GraphState) -> dict[str, Any]:
        files = deps.diff_provider.get_changed_files(state["target"])
        budgeted, truncated = apply_budget(
            files, deps.config.max_file_chars, deps.config.max_total_chars
        )
        return {"files": budgeted, "truncated_files": truncated}

    return ingest
