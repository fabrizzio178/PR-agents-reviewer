"""CODE & ARCHITECTURE agent: style, complexity, breaking changes, coupling."""

from __future__ import annotations

from collections.abc import Callable

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.nodes.parsing import parse_findings
from agent_langgraph.domain.models import GraphState

SYSTEM_PROMPT = (
    "You are a senior reviewer focused on code quality and architecture. "
    "Inspect the diff for style issues, excessive complexity, dead code, "
    "breaking API changes, and unwanted coupling between modules. Reply with "
    "one finding per line as 'severity|file|message' (severity is low, medium, "
    "or high), or reply 'CLEAN' if nothing is wrong. Do not add any other text."
)


def make_code_arch_agent(deps: GraphDeps) -> Callable[[GraphState], dict]:
    def code_arch_agent(state: GraphState) -> dict:
        diff_text = _render_diff(state)
        response = deps.llm.complete(SYSTEM_PROMPT, diff_text)
        return {"findings": parse_findings("code_arch", response)}

    return code_arch_agent


def _render_diff(state: GraphState) -> str:
    return "\n".join(f"--- {f.path} ---\n{f.patch}" for f in state["files"])
