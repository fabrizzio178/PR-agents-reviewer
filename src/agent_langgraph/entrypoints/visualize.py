"""Renders the compiled graph as Mermaid, for the portfolio case study.

Usage:
    uv run visualize-graph
Writes docs/graph.mmd (paste into https://mermaid.live or a markdown/artifact
that renders Mermaid natively — no extra rendering dependency needed).
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.graph import build_graph

OUTPUT_PATH = Path(__file__).resolve().parents[3] / "docs" / "graph.mmd"


def main() -> None:
    # Structure-only: build_graph never calls the adapters, it only wires
    # nodes and edges, so None stand-ins are enough to compile and draw it.
    deps = GraphDeps(diff_provider=None, comment_poster=None, static_analyzer=None, llm=None)  # type: ignore[arg-type]
    graph = build_graph(deps)

    mermaid_source = graph.get_graph().draw_mermaid()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(mermaid_source, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(mermaid_source)


if __name__ == "__main__":
    sys.exit(main())
