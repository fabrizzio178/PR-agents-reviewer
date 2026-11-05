"""Incident-mode ports: where evidence comes from and where the report goes."""

from __future__ import annotations

from typing import Protocol

from agent_langgraph.incidents.models import IncidentContext


class IncidentSource(Protocol):
    def collect(self, project: str, pipeline_id: int) -> IncidentContext:
        """Read-only: the pipeline, its jobs, failed-job logs and recent changes."""
        ...


class IncidentPublisher(Protocol):
    def publish(self, project: str, pipeline_id: int, title: str, body: str) -> str:
        """Create or update the one report for this pipeline. Returns its URL."""
        ...
