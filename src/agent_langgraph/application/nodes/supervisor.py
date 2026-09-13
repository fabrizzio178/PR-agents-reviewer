"""SUPERVISOR node: routes the diff to whichever specialized agents are relevant.

Not every diff needs every agent — a README-only change shouldn't trigger the
security agent. This is what makes the graph genuinely multi-agent instead of
a fixed linear chain: the fan-out below is a runtime decision, not a constant.
"""

from __future__ import annotations

from agent_langgraph.domain.models import GraphState

SECURITY_TRIGGERS = {".py", ".ts", ".tsx", ".js", ".jsx", ".env", ".yml", ".yaml"}
CODE_ARCH_TRIGGERS = {".py", ".ts", ".tsx", ".js", ".jsx"}


def supervisor(state: GraphState) -> dict:
    extensions = {_extension(f.path) for f in state["files"]}
    active = []
    if extensions & SECURITY_TRIGGERS:
        active.append("security")
    if extensions & CODE_ARCH_TRIGGERS:
        active.append("code_arch")
    if not active:
        active.append("code_arch")
    return {"active_agents": active}


def route_from_supervisor(state: GraphState) -> list[str]:
    """Conditional edge: fan out in parallel to every agent the supervisor activated."""
    return state["active_agents"]


def _extension(path: str) -> str:
    return path[path.rfind(".") :] if "." in path else ""
