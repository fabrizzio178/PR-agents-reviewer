"""INGEST node: fetches the diff for the commit/PR being reviewed."""

from __future__ import annotations

from collections.abc import Callable

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.models import GraphState


def make_ingest_node(deps: GraphDeps) -> Callable[[GraphState], dict]:
    def ingest(state: GraphState) -> dict:
        files = deps.diff_provider.get_changed_files(state["repo"], state["commit_sha"])
        return {"files": files}

    return ingest
