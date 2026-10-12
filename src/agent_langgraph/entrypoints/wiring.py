"""Composition root: builds GraphDeps from resolved settings.

The only place in the codebase allowed to know about concrete adapter
classes — everything else depends on ports.
"""

from __future__ import annotations

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.adapters.github.rest_diff_provider import GitHubRestDiffProvider
from agent_langgraph.adapters.github.rest_review_publisher import GitHubRestReviewPublisher
from agent_langgraph.adapters.llm.gemini_client import GeminiLLMClient
from agent_langgraph.adapters.llm.openai_compatible_client import OpenAICompatibleLLMClient
from agent_langgraph.adapters.static_analysis.ruff_runner import RuffStaticAnalyzer
from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.ports import LLMClient
from agent_langgraph.entrypoints.settings import OPENAI_COMPATIBLE, LLMSettings, Settings


def build_llm(settings: LLMSettings) -> LLMClient:
    if settings.provider == OPENAI_COMPATIBLE:
        assert settings.base_url is not None
        return OpenAICompatibleLLMClient(settings.api_key, settings.base_url, settings.model)
    return GeminiLLMClient(settings.api_key, settings.model)


def build_deps(settings: Settings) -> GraphDeps:
    github = GitHubRestClient(settings.github_token)
    return GraphDeps(
        diff_provider=GitHubRestDiffProvider(github),
        publisher=GitHubRestReviewPublisher(github),
        static_analyzer=RuffStaticAnalyzer(),
        llm=build_llm(settings.llm),
        config=settings.review,
    )


def resolve_head_sha(settings: Settings, repo: str, pr_number: int) -> str:
    """Look up the PR's current head commit, for runs that only know its number."""
    pull = GitHubRestClient(settings.github_token).get(f"/repos/{repo}/pulls/{pr_number}")
    return str(pull["head"]["sha"])
