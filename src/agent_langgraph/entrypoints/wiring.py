"""Composition root: builds GraphDeps from resolved settings.

The only place in the codebase allowed to know about concrete adapter
classes — everything else depends on ports.
"""

from __future__ import annotations

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.adapters.github.rest_config_provider import GitHubRestConfigProvider
from agent_langgraph.adapters.github.rest_diff_provider import GitHubRestDiffProvider
from agent_langgraph.adapters.github.rest_review_publisher import GitHubRestReviewPublisher
from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient, merge_request_path
from agent_langgraph.adapters.gitlab.rest_config_provider import GitLabRestConfigProvider
from agent_langgraph.adapters.gitlab.rest_diff_provider import GitLabRestDiffProvider
from agent_langgraph.adapters.gitlab.rest_review_publisher import GitLabRestReviewPublisher
from agent_langgraph.adapters.llm.gemini_client import GeminiLLMClient
from agent_langgraph.adapters.llm.openai_compatible_client import OpenAICompatibleLLMClient
from agent_langgraph.adapters.static_analysis.ruff_runner import RuffStaticAnalyzer
from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.ports import (
    DiffProvider,
    LLMClient,
    RepoConfigProvider,
    ReviewPublisher,
)
from agent_langgraph.entrypoints.settings import (
    GITLAB,
    OPENAI_COMPATIBLE,
    LLMSettings,
    PlatformSettings,
    Settings,
)


def build_llm(settings: LLMSettings) -> LLMClient:
    if settings.provider == OPENAI_COMPATIBLE:
        assert settings.base_url is not None
        return OpenAICompatibleLLMClient(settings.api_key, settings.base_url, settings.model)
    return GeminiLLMClient(settings.api_key, settings.model)


def build_platform(
    settings: PlatformSettings,
) -> tuple[DiffProvider, RepoConfigProvider, ReviewPublisher]:
    if settings.name == GITLAB:
        gitlab = GitLabRestClient(settings.token, settings.api_url)
        return (
            GitLabRestDiffProvider(gitlab),
            GitLabRestConfigProvider(gitlab),
            GitLabRestReviewPublisher(gitlab),
        )
    github = GitHubRestClient(settings.token, settings.api_url)
    return (
        GitHubRestDiffProvider(github),
        GitHubRestConfigProvider(github),
        GitHubRestReviewPublisher(github),
    )


def build_deps(settings: Settings) -> GraphDeps:
    diff_provider, config_provider, publisher = build_platform(settings.platform)
    return GraphDeps(
        diff_provider=diff_provider,
        config_provider=config_provider,
        publisher=publisher,
        static_analyzer=RuffStaticAnalyzer(),
        llm=build_llm(settings.llm),
        config=settings.review,
    )


def resolve_head_sha(settings: Settings, repo: str, pr_number: int) -> str:
    """Look up the PR/MR's current head commit, for runs that only know its number."""
    platform = settings.platform
    if platform.name == GITLAB:
        client = GitLabRestClient(platform.token, platform.api_url)
        return str(client.get(merge_request_path(repo, pr_number))["sha"])
    pull = GitHubRestClient(platform.token, platform.api_url).get(
        f"/repos/{repo}/pulls/{pr_number}"
    )
    return str(pull["head"]["sha"])
