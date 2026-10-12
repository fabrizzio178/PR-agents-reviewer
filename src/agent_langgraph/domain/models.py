"""Domain models: pure data structures. No framework or IO dependencies."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, TypedDict


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


@dataclass(frozen=True)
class ReviewTarget:
    repo: str
    pr_number: int
    head_sha: str


@dataclass(frozen=True)
class FileChange:
    path: str
    patch: str
    additions: int
    deletions: int
    truncated: bool = False


@dataclass(frozen=True)
class ReviewItem:
    """A finding as returned by an LLM, before it is attributed to an agent."""

    file: str
    message: str
    severity: Severity
    line: int | None = None


@dataclass(frozen=True)
class Finding:
    agent: str
    file: str
    message: str
    severity: Severity
    line: int | None = None


@dataclass(frozen=True)
class InlineComment:
    path: str
    line: int
    body: str


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class LLMResult:
    items: list[ReviewItem]
    usage: TokenUsage


@dataclass(frozen=True)
class RepoConfig:
    """Per-repository review settings, read from `.pr-review.yml` on the base branch."""

    disabled_reviewers: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    gate_severity: Severity | None = None


@dataclass(frozen=True)
class ReviewVerdict:
    findings: list[Finding]
    max_severity: Severity
    requires_human_review: bool


class GraphState(TypedDict, total=False):
    """Shared state threaded through every LangGraph node.

    `findings`, `agent_errors` and `usage` carry reducers so the parallel
    branches can each write to them without clobbering each other's updates
    in the same super-step.
    """

    target: ReviewTarget
    repo_config: RepoConfig
    config_warning: str | None
    files: list[FileChange]
    truncated_files: list[str]
    active_agents: list[str]
    findings: Annotated[list[Finding], operator.add]
    agent_errors: Annotated[list[str], operator.add]
    usage: Annotated[TokenUsage, operator.add]
    verdict: ReviewVerdict | None
    human_approved: bool | None
    comment_body: str | None
    posted: bool
