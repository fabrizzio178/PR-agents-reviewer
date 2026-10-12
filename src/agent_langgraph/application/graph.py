r"""Builds the LangGraph StateGraph: wires every node and conditional edge.

                              /-> STATIC_ANALYSIS -\
    INGEST -> SUPERVISOR --(fan-out)-> SECURITY ----+-> AGGREGATOR
                    \         \-> CODE_ARCH -------/        |
                     \---------(docs only)-----------------/|
                                                        RISK_GATE
                                                        /       \
                                           notify_pending        \
                                                  |               \
                                            human_review --------> post -> END
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.instrumentation import timed
from agent_langgraph.application.nodes.aggregator import make_aggregator
from agent_langgraph.application.nodes.human_review import human_review
from agent_langgraph.application.nodes.ingest import make_ingest_node
from agent_langgraph.application.nodes.notify_pending import make_notify_pending_node
from agent_langgraph.application.nodes.post import make_post_node
from agent_langgraph.application.nodes.review_agent import make_review_agent
from agent_langgraph.application.nodes.risk_gate import route_from_risk_gate
from agent_langgraph.application.nodes.static_analysis import make_static_analysis_node
from agent_langgraph.application.nodes.supervisor import (
    AGGREGATOR,
    CODE_ARCH,
    SECURITY,
    STATIC_ANALYSIS,
    route_from_supervisor,
    supervisor,
)
from agent_langgraph.application.prompts import CODE_ARCH_PROMPT, SECURITY_PROMPT
from agent_langgraph.domain.models import GraphState

# GitHub IO is retried at the node level; the publisher is idempotent, so a
# repeated publish node cannot duplicate comments.
_IO_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0)


def build_graph(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("ingest", timed("ingest", make_ingest_node(deps)), retry_policy=_IO_RETRY)
    graph.add_node("supervisor", timed("supervisor", supervisor))
    graph.add_node(STATIC_ANALYSIS, timed(STATIC_ANALYSIS, make_static_analysis_node(deps)))
    graph.add_node(SECURITY, timed(SECURITY, make_review_agent(SECURITY, SECURITY_PROMPT, deps)))
    graph.add_node(
        CODE_ARCH, timed(CODE_ARCH, make_review_agent(CODE_ARCH, CODE_ARCH_PROMPT, deps))
    )
    graph.add_node(AGGREGATOR, timed(AGGREGATOR, make_aggregator(deps)))
    graph.add_node(
        "notify_pending",
        timed("notify_pending", make_notify_pending_node(deps)),
        retry_policy=_IO_RETRY,
    )
    graph.add_node("human_review", human_review)
    graph.add_node("post", timed("post", make_post_node(deps)), retry_policy=_IO_RETRY)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            STATIC_ANALYSIS: STATIC_ANALYSIS,
            SECURITY: SECURITY,
            CODE_ARCH: CODE_ARCH,
            AGGREGATOR: AGGREGATOR,
        },
    )
    graph.add_edge(STATIC_ANALYSIS, AGGREGATOR)
    graph.add_edge(SECURITY, AGGREGATOR)
    graph.add_edge(CODE_ARCH, AGGREGATOR)

    graph.add_conditional_edges(
        AGGREGATOR,
        route_from_risk_gate,
        {"notify_pending": "notify_pending", "post": "post"},
    )
    graph.add_edge("notify_pending", "human_review")
    graph.add_edge("human_review", "post")
    graph.add_edge("post", END)

    return graph.compile(checkpointer=checkpointer)
