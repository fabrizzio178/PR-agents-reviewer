"""SUPERVISOR node: routes the diff to whichever specialized agents are relevant.

Not every diff needs every agent — a README-only change triggers none of
them and goes straight to the aggregator. This is what makes the graph
genuinely multi-agent instead of a fixed linear chain: the fan-out below is a
runtime decision, not a constant.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from agent_langgraph.domain.models import GraphState

STATIC_ANALYSIS = "static_analysis"
SECURITY = "security"
CODE_ARCH = "code_arch"
AGGREGATOR = "aggregator"

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".java", ".kt", ".rb",
    ".rs", ".cs", ".php", ".c", ".h", ".cpp", ".swift", ".scala",
}  # fmt: skip
# Config, infrastructure and dependency manifests: no architecture to review,
# but exactly where secrets, permissions and supply-chain changes show up.
SECURITY_EXTENSIONS = CODE_EXTENSIONS | {
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".tf", ".sql", ".sh",
    ".ps1", ".lock", ".gradle", ".xml",
}  # fmt: skip
SECURITY_FILENAMES = {"dockerfile", "makefile", "gemfile", "go.mod", "go.sum"}


def supervisor(state: GraphState) -> dict[str, Any]:
    paths = [PurePosixPath(f.path) for f in state["files"]]
    active = []
    if any(p.suffix == ".py" for p in paths):
        active.append(STATIC_ANALYSIS)
    if any(_is_security_relevant(p) for p in paths):
        active.append(SECURITY)
    if any(p.suffix.lower() in CODE_EXTENSIONS for p in paths):
        active.append(CODE_ARCH)
    disabled = state["repo_config"].disabled_reviewers if "repo_config" in state else []
    return {"active_agents": [name for name in active if name not in disabled]}


def route_from_supervisor(state: GraphState) -> list[str]:
    """Conditional edge: fan out in parallel to every agent the supervisor activated."""
    return state["active_agents"] or [AGGREGATOR]


def _is_security_relevant(path: PurePosixPath) -> bool:
    name = path.name.lower()
    return (
        path.suffix.lower() in SECURITY_EXTENSIONS
        or name in SECURITY_FILENAMES
        or name.startswith((".env", "dockerfile", "requirements"))
    )
