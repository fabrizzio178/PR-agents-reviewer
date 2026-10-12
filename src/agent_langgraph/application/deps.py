"""Composition-root container: the concrete adapters injected into the graph's nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_langgraph.domain.models import Severity
from agent_langgraph.domain.ports import DiffProvider, LLMClient, ReviewPublisher, StaticAnalyzer


@dataclass(frozen=True)
class ReviewConfig:
    max_file_chars: int = 20_000
    max_total_chars: int = 120_000
    # Lowest severity that pauses the graph for human approval before posting.
    gate_severity: Severity = Severity.HIGH


@dataclass
class GraphDeps:
    diff_provider: DiffProvider
    publisher: ReviewPublisher
    static_analyzer: StaticAnalyzer
    llm: LLMClient
    config: ReviewConfig = field(default_factory=ReviewConfig)
