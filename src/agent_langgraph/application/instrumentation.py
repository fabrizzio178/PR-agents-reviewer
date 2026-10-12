"""Node instrumentation: one structured log line per node execution."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from agent_langgraph.domain.models import GraphState

logger = logging.getLogger("agent_langgraph.graph")


class Node(Protocol):
    def __call__(self, state: GraphState) -> dict[str, Any]: ...


def timed(name: str, node: Callable[[GraphState], dict[str, Any]]) -> Node:
    def wrapper(state: GraphState) -> dict[str, Any]:
        started = time.perf_counter()
        outcome = "ok"
        try:
            return node(state)
        except Exception as exc:
            # interrupt() surfaces as an exception too; the class name tells them apart.
            outcome = type(exc).__name__
            raise
        finally:
            logger.info(
                "node finished",
                extra={
                    "node": name,
                    "outcome": outcome,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )

    return wrapper
