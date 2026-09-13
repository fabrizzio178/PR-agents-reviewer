"""Ports: interfaces the application layer depends on. Adapters implement these.

Keeping these as Protocols (structural typing) means the application layer
never imports a concrete adapter (requests, groq, subprocess) directly, so
swapping the GitHub REST adapter for an MCP-based one later is a one-file change.
"""

from __future__ import annotations

from typing import Protocol

from agent_langgraph.domain.models import FileChange


class DiffProvider(Protocol):
    def get_changed_files(self, repo: str, ref: str) -> list[FileChange]: ...


class CommentPoster(Protocol):
    def post_comment(self, repo: str, ref: str, body: str) -> None: ...


class StaticAnalyzer(Protocol):
    def run(self, files: list[FileChange]) -> str: ...


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...
