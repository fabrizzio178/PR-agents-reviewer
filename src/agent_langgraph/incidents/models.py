"""Incident-mode domain models: what was collected about a failed pipeline."""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, TypedDict

from agent_langgraph.domain.models import TokenUsage
from agent_langgraph.incidents.schemas import HypothesesSchema, MitigationPlan, RefutationSchema


@dataclass(frozen=True)
class ServiceSpec:
    """One service of the system, as described in `.incident.yml`."""

    name: str
    paths: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class IncidentMap:
    """The service map and runbook: the agent's knowledge of the system."""

    services: list[ServiceSpec] = field(default_factory=list)
    runbook: list[str] = field(default_factory=list)
    language: str = "English"

    def services_touching(self, paths: list[str]) -> list[str]:
        """Services with at least one changed file under one of their paths."""
        return [
            s.name
            for s in self.services
            if any(path.startswith(prefix) for prefix in s.paths for path in paths)
        ]


@dataclass(frozen=True)
class JobRun:
    id: int
    name: str
    stage: str
    status: str
    allow_failure: bool
    web_url: str
    started_at: str | None = None
    finished_at: str | None = None
    # Only kept for failed jobs: the last lines of the job log.
    log_tail: str = ""

    @property
    def blocking_failure(self) -> bool:
        return self.status == "failed" and not self.allow_failure


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    title: str
    author: str
    created_at: str


@dataclass(frozen=True)
class IncidentContext:
    project: str
    pipeline_id: int
    pipeline_url: str
    ref: str
    sha: str
    created_at: str
    jobs: list[JobRun]
    last_good_pipeline_id: int | None = None
    last_good_sha: str | None = None
    # Commits and changed files between the last good pipeline and this one.
    commits: list[CommitInfo] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)

    @property
    def failed_jobs(self) -> list[JobRun]:
        return [j for j in self.jobs if j.blocking_failure]


@dataclass(frozen=True)
class TimelineEvent:
    at: str
    kind: str
    text: str

    @property
    def sort_key(self) -> tuple[int, float | str]:
        try:
            return (0, datetime.fromisoformat(self.at).timestamp())
        except ValueError:
            return (1, self.at)


class IncidentState(TypedDict, total=False):
    project: str
    pipeline_id: int
    incident_map: IncidentMap
    map_warning: str | None
    context: IncidentContext
    changed_services: list[str]
    timeline: list[TimelineEvent]
    hypotheses: HypothesesSchema
    refutation: RefutationSchema
    plan: MitigationPlan
    errors: Annotated[list[str], operator.add]
    usage: Annotated[TokenUsage, operator.add]
    report: str
    issue_url: str | None
