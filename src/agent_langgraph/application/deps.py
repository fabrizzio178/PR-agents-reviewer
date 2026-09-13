"""Composition-root container: the concrete adapters injected into the graph's nodes."""

from __future__ import annotations

from dataclasses import dataclass

from agent_langgraph.domain.ports import CommentPoster, DiffProvider, LLMClient, StaticAnalyzer


@dataclass
class GraphDeps:
    diff_provider: DiffProvider
    comment_poster: CommentPoster
    static_analyzer: StaticAnalyzer
    llm: LLMClient
