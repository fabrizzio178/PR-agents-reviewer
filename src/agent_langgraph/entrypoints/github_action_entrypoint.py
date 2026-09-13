"""Entrypoint invoked by the GitHub Actions workflow on every push.

Reads GitHub's default `GITHUB_REPOSITORY` / `GITHUB_SHA` env vars, so no
workflow-specific wiring is needed beyond passing GROQ_API_KEY as a secret.
"""

from __future__ import annotations

import os
import sys

from langgraph.checkpoint.sqlite import SqliteSaver

from agent_langgraph.application.graph import build_graph
from agent_langgraph.entrypoints.wiring import build_deps_from_env


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]

    deps = build_deps_from_env()

    with SqliteSaver.from_conn_string("agent_langgraph.sqlite") as checkpointer:
        graph = build_graph(deps, checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": f"{repo}@{sha}"}}
        result = graph.invoke({"repo": repo, "commit_sha": sha}, config=thread_config)

        if "__interrupt__" in result:
            # MVP: no async approval channel yet, so a high-severity finding
            # simply doesn't get auto-posted — it waits for a manual `review` run.
            print("Paused for human review — run `uv run review` locally to approve.")
            return

        print(f"posted={result.get('posted')}")


if __name__ == "__main__":
    sys.exit(main())
