"""SECURITY agent: flags secrets, injection risks, and auth issues in the diff."""

from __future__ import annotations

from collections.abc import Callable

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.nodes.parsing import parse_findings
from agent_langgraph.domain.models import GraphState

SYSTEM_PROMPT = (
    "You are a security-focused code reviewer. Inspect the diff for hardcoded "
    "secrets, injection vulnerabilities, broken auth checks, and unsafe "
    "deserialization. Reply with one finding per line as 'severity|file|message' "
    "(severity is low, medium, or high), or reply 'CLEAN' if nothing is wrong. "
    "Do not add any other text."
)


def make_security_agent(deps: GraphDeps) -> Callable[[GraphState], dict]:
    def security_agent(state: GraphState) -> dict:
        diff_text = _render_diff(state)
        response = deps.llm.complete(SYSTEM_PROMPT, diff_text)
        return {"findings": parse_findings("security", response)}

    return security_agent


def _render_diff(state: GraphState) -> str:
    return "\n".join(f"--- {f.path} ---\n{f.patch}" for f in state["files"])
