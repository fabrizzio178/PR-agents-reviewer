r"""Builds the LangGraph StateGraph: wires every node and conditional edge.

    INGEST -> STATIC_ANALYSIS -> SUPERVISOR --(fan-out)--> SECURITY   -\
                                                        \-> CODE_ARCH -+-> AGGREGATOR
                                                                            |
                                                                       RISK_GATE
                                                                       /       \
                                                           human_review         post
                                                                |                |
                                                                v                v
                                                              post ----------> END
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.nodes.aggregator import aggregator
from agent_langgraph.application.nodes.code_arch_agent import make_code_arch_agent
from agent_langgraph.application.nodes.human_review import human_review
from agent_langgraph.application.nodes.ingest import make_ingest_node
from agent_langgraph.application.nodes.post import make_post_node
from agent_langgraph.application.nodes.risk_gate import route_from_risk_gate
from agent_langgraph.application.nodes.security_agent import make_security_agent
from agent_langgraph.application.nodes.static_analysis import make_static_analysis_node
from agent_langgraph.application.nodes.supervisor import route_from_supervisor, supervisor
from agent_langgraph.domain.models import GraphState


def build_graph(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("ingest", make_ingest_node(deps))
    graph.add_node("static_analysis", make_static_analysis_node(deps))
    graph.add_node("supervisor", supervisor)
    graph.add_node("security", make_security_agent(deps))
    graph.add_node("code_arch", make_code_arch_agent(deps))
    graph.add_node("aggregator", aggregator)
    graph.add_node("human_review", human_review)
    graph.add_node("post", make_post_node(deps))

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "static_analysis")
    graph.add_edge("static_analysis", "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"security": "security", "code_arch": "code_arch"},
    )
    graph.add_edge("security", "aggregator")
    graph.add_edge("code_arch", "aggregator")

    graph.add_conditional_edges(
        "aggregator",
        route_from_risk_gate,
        {"human_review": "human_review", "post": "post"},
    )
    graph.add_edge("human_review", "post")
    graph.add_edge("post", END)

    return graph.compile(checkpointer=checkpointer)
