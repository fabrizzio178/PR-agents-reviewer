"""Composition root: builds GraphDeps from environment variables.

The only place in the codebase allowed to know about env vars and concrete
adapter classes at once — everything else depends on ports.
"""

from __future__ import annotations

import os

from agent_langgraph.adapters.github.rest_comment_poster import GitHubRestCommentPoster
from agent_langgraph.adapters.github.rest_diff_provider import GitHubRestDiffProvider
from agent_langgraph.adapters.llm.gemini_client import GeminiLLMClient
from agent_langgraph.adapters.static_analysis.ruff_runner import RuffStaticAnalyzer
from agent_langgraph.application.deps import GraphDeps


def build_deps_from_env() -> GraphDeps:
    github_token = _require_env("GITHUB_TOKEN")
    gemini_api_key = _require_env("GEMINI_API_KEY")

    return GraphDeps(
        diff_provider=GitHubRestDiffProvider(github_token),
        comment_poster=GitHubRestCommentPoster(github_token),
        static_analyzer=RuffStaticAnalyzer(),
        llm=GeminiLLMClient(gemini_api_key),
    )


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
