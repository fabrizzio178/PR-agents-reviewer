"""Domain models: pure data structures. No framework or IO dependencies."""

from __future__ import annotations

import operator
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, TypedDict


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class FileChange:
    path: str
    patch: str
    additions: int
    deletions: int


@dataclass(frozen=True)
class Finding:
    agent: str
    file: str
    message: str
    severity: Severity


@dataclass(frozen=True)
class ReviewVerdict:
    findings: list[Finding]
    max_severity: Severity
    requires_human_review: bool
    summary: str


class GraphState(TypedDict, total=False):
    """Shared state threaded through every LangGraph node.

    `findings` uses operator.add as its reducer so the parallel security/
    code_arch branches can each append to the same list without clobbering
    each other's writes in the same super-step.
    """

    repo: str
    commit_sha: str
    files: list[FileChange]
    static_analysis_output: str
    active_agents: list[str]
    findings: Annotated[list[Finding], operator.add]
    verdict: ReviewVerdict | None
    human_approved: bool | None
    comment_body: str | None
    posted: bool
