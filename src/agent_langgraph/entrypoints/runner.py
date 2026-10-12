"""Shared run/resume logic for every entrypoint (local CLI and GitHub Actions).

A review is one LangGraph thread. `start_review` runs it until it finishes or
pauses at the human gate; `resume_review` continues a paused thread — possibly
from another process, which is why the checkpointer is a SQLite file.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agent_langgraph.domain import models
from agent_langgraph.domain.models import ReviewTarget

# The checkpoint may come back from another job as a downloaded artifact, so
# only these domain types are allowed to be rebuilt from it.
_CHECKPOINT_TYPES = (
    models.ReviewTarget,
    models.FileChange,
    models.Finding,
    models.Severity,
    models.TokenUsage,
    models.ReviewVerdict,
    models.RepoConfig,
)


@dataclass(frozen=True)
class RunOutcome:
    thread_id: str
    paused: bool
    posted: bool
    # While paused: the full review awaiting approval. Otherwise: what was published.
    body: str


class NoPausedReviewError(RuntimeError):
    pass


@contextmanager
def open_checkpointer(path: str) -> Iterator[SqliteSaver]:
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[(t.__module__, t.__name__) for t in _CHECKPOINT_TYPES]
    )
    with closing(sqlite3.connect(path, check_same_thread=False)) as conn:
        yield SqliteSaver(conn, serde=serde)


def start_review(graph: CompiledStateGraph, target: ReviewTarget, thread_id: str) -> RunOutcome:
    result = graph.invoke({"target": target}, config=_config(thread_id))
    return _outcome(thread_id, result)


def resume_review(graph: CompiledStateGraph, thread_id: str, approved: bool) -> RunOutcome:
    config = _config(thread_id)
    if "human_review" not in graph.get_state(config).next:
        raise NoPausedReviewError(f"Thread {thread_id!r} has no review waiting for approval.")
    result = graph.invoke(Command(resume={"approved": approved}), config=config)
    return _outcome(thread_id, result)


def _config(thread_id: str) -> Any:
    return {"configurable": {"thread_id": thread_id}}


def _outcome(thread_id: str, result: dict[str, Any]) -> RunOutcome:
    interrupts = result.get("__interrupt__")
    if interrupts:
        return RunOutcome(
            thread_id=thread_id, paused=True, posted=False, body=interrupts[0].value["review"]
        )
    return RunOutcome(
        thread_id=thread_id,
        paused=False,
        posted=bool(result.get("posted")),
        body=result.get("comment_body") or "",
    )
