"""Ports: interfaces the application layer depends on. Adapters implement these.

Keeping these as Protocols (structural typing) means the application layer
never imports a concrete adapter (requests, google-genai, subprocess)
directly, so swapping the GitHub REST adapter for an MCP-based one later is a
one-file change.
"""

from __future__ import annotations

from typing import Protocol

from agent_langgraph.domain.models import (
    FileChange,
    Finding,
    InlineComment,
    LLMResult,
    RepoConfig,
    ReviewTarget,
)


class DiffProvider(Protocol):
    def get_changed_files(self, target: ReviewTarget) -> list[FileChange]: ...


class RepoConfigProvider(Protocol):
    def load(self, target: ReviewTarget) -> RepoConfig:
        """Return the repo's review config, or defaults if it has none.

        Raises ConfigError if the file exists but is invalid.
        """
        ...


class ReviewPublisher(Protocol):
    def publish_status(self, target: ReviewTarget, body: str) -> None:
        """Create or update the single summary comment for this PR."""
        ...

    def publish_inline(self, target: ReviewTarget, comments: list[InlineComment]) -> None:
        """Post line-level comments, skipping any that are already there."""
        ...


class StaticAnalyzer(Protocol):
    def run(self, files: list[FileChange]) -> list[Finding]:
        """Raises StaticAnalysisError if the analyzer cannot run."""
        ...


class LLMClient(Protocol):
    def review(self, system_prompt: str, user_prompt: str) -> LLMResult:
        """Raises LLMError on transport failure or schema-invalid output."""
        ...
