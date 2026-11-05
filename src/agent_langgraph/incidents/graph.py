r"""The incident investigation graph.

    COLLECT -> HYPOTHESIZE -> REFUTE -> PLAN -> REPORT -> PUBLISH -> END

COLLECT gathers evidence (read-only) and builds the timeline. The three LLM
steps mirror how an on-call engineer works: list possible causes, try to
disprove each one, then plan only from what survived. A failing LLM step does
not stop the run: the report says which step failed and keeps the evidence, so
a failure still leaves something useful for the human on call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.ports import LLMClient
from agent_langgraph.incidents.models import (
    IncidentContext,
    IncidentMap,
    IncidentState,
    TimelineEvent,
)
from agent_langgraph.incidents.ports import IncidentPublisher, IncidentSource
from agent_langgraph.incidents.prompts import (
    hypothesize_prompt,
    plan_prompt,
    refute_prompt,
    render_conclusion,
    render_hypotheses,
    render_incident,
)
from agent_langgraph.incidents.redaction import redact
from agent_langgraph.incidents.rendering import issue_title, render_report
from agent_langgraph.incidents.schemas import HypothesesSchema, MitigationPlan, RefutationSchema

logger = logging.getLogger(__name__)
_IO_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0)


class _Node(Protocol):
    def __call__(self, state: IncidentState) -> dict[str, Any]: ...


def timed(name: str, node: Callable[[IncidentState], dict[str, Any]]) -> _Node:
    """Same log line as the review graph's nodes. Not shared on purpose: LangGraph reads
    the state type from the wrapper's annotation, and this graph has its own state."""

    def wrapper(state: IncidentState) -> dict[str, Any]:
        started = time.perf_counter()
        outcome = "ok"
        try:
            return node(state)
        except Exception as exc:
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


@dataclass
class IncidentDeps:
    source: IncidentSource
    llm: LLMClient
    publisher: IncidentPublisher | None  # None: dry run, only the local report


def build_incident_graph(deps: IncidentDeps) -> CompiledStateGraph:
    graph = StateGraph(IncidentState)
    graph.add_node("collect", timed("collect", _collect(deps)), retry_policy=_IO_RETRY)
    graph.add_node("hypothesize", timed("hypothesize", _hypothesize(deps)))
    graph.add_node("refute", timed("refute", _refute(deps)))
    graph.add_node("plan", timed("plan", _plan(deps)))
    graph.add_node("report", timed("report", _report))
    graph.add_node("publish", timed("publish", _publish(deps)), retry_policy=_IO_RETRY)

    graph.set_entry_point("collect")
    graph.add_edge("collect", "hypothesize")
    graph.add_edge("hypothesize", "refute")
    graph.add_edge("refute", "plan")
    graph.add_edge("plan", "report")
    graph.add_edge("report", "publish")
    graph.add_edge("publish", END)
    return graph.compile()


def build_timeline(context: IncidentContext) -> list[TimelineEvent]:
    events = []
    if context.last_good_sha and context.last_good_pipeline_id:
        events.append(
            TimelineEvent(
                at="",
                kind="last-good",
                text=f"pipeline #{context.last_good_pipeline_id} passed at "
                f"{context.last_good_sha[:8]}",
            )
        )
    events += [
        TimelineEvent(at=c.created_at, kind="commit", text=f"{c.sha[:8]} {c.title}")
        for c in context.commits
    ]
    events.append(
        TimelineEvent(
            at=context.created_at, kind="pipeline", text=f"#{context.pipeline_id} started"
        )
    )
    for job in context.jobs:
        if job.started_at:
            events.append(TimelineEvent(at=job.started_at, kind="job", text=f"{job.name} started"))
        if job.finished_at:
            note = " (allowed to fail)" if job.status == "failed" and job.allow_failure else ""
            events.append(
                TimelineEvent(at=job.finished_at, kind="job", text=f"{job.name} {job.status}{note}")
            )
    dated = sorted((e for e in events if e.at), key=lambda e: e.sort_key)
    # The last-good marker has no timestamp of its own: it goes first.
    return [e for e in events if not e.at] + dated


def _collect(deps: IncidentDeps) -> Callable[[IncidentState], dict[str, Any]]:
    def collect(state: IncidentState) -> dict[str, Any]:
        context = deps.source.collect(state["project"], state["pipeline_id"])
        # Redact here, not in the adapter: whatever the source, logs never reach
        # the model unredacted.
        context = replace(
            context,
            jobs=[replace(j, log_tail=redact(j.log_tail)) for j in context.jobs],
        )
        incident_map = state.get("incident_map") or IncidentMap()
        return {
            "context": context,
            "changed_services": incident_map.services_touching(context.changed_files),
            "timeline": build_timeline(context),
        }

    return collect


def _hypothesize(deps: IncidentDeps) -> Callable[[IncidentState], dict[str, Any]]:
    def hypothesize(state: IncidentState) -> dict[str, Any]:
        if not state["context"].failed_jobs:
            return {"errors": ["no failed job found in this pipeline: nothing to investigate"]}
        incident_map = state.get("incident_map") or IncidentMap()
        try:
            parsed, usage = deps.llm.generate(
                hypothesize_prompt(incident_map), render_incident(state), HypothesesSchema
            )
        except LLMError as exc:
            logger.warning("hypothesize failed: %s", exc)
            return {"errors": [f"hypothesize: {exc}"]}
        return {"hypotheses": parsed, "usage": usage}

    return hypothesize


def _refute(deps: IncidentDeps) -> Callable[[IncidentState], dict[str, Any]]:
    def refute(state: IncidentState) -> dict[str, Any]:
        hypotheses = state.get("hypotheses")
        if not hypotheses or not hypotheses.hypotheses:
            return {}
        incident_map = state.get("incident_map") or IncidentMap()
        prompt = render_incident(state) + "\n" + render_hypotheses(hypotheses)
        try:
            parsed, usage = deps.llm.generate(refute_prompt(incident_map), prompt, RefutationSchema)
        except LLMError as exc:
            logger.warning("refute failed: %s", exc)
            return {"errors": [f"refute: {exc}"]}
        known = {h.id for h in hypotheses.hypotheses}
        supported = {c.id for c in parsed.checks if c.verdict == "supported"}
        if parsed.root_cause_id is not None and (
            parsed.root_cause_id not in known or parsed.root_cause_id not in supported
        ):
            # A root cause must be a hypothesis that survived its own check.
            parsed = parsed.model_copy(update={"root_cause_id": None, "confidence": "low"})
        return {"refutation": parsed, "usage": usage}

    return refute


def _plan(deps: IncidentDeps) -> Callable[[IncidentState], dict[str, Any]]:
    def plan(state: IncidentState) -> dict[str, Any]:
        hypotheses = state.get("hypotheses")
        refutation = state.get("refutation")
        if not hypotheses or not refutation:
            return {}
        incident_map = state.get("incident_map") or IncidentMap()
        prompt = (
            render_incident(state)
            + "\n"
            + render_hypotheses(hypotheses)
            + "\n"
            + render_conclusion(hypotheses, refutation)
        )
        try:
            parsed, usage = deps.llm.generate(plan_prompt(incident_map), prompt, MitigationPlan)
        except LLMError as exc:
            logger.warning("plan failed: %s", exc)
            return {"errors": [f"plan: {exc}"]}
        return {"plan": parsed, "usage": usage}

    return plan


def _report(state: IncidentState) -> dict[str, Any]:
    return {"report": render_report(state)}


def _publish(deps: IncidentDeps) -> Callable[[IncidentState], dict[str, Any]]:
    def publish(state: IncidentState) -> dict[str, Any]:
        if deps.publisher is None:
            return {"issue_url": None}
        url = deps.publisher.publish(
            state["project"], state["pipeline_id"], issue_title(state), state["report"]
        )
        return {"issue_url": url}

    return publish
