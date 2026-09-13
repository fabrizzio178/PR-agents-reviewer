"""Local entrypoint: run the graph against a real commit for manual testing.

Usage:
    uv run review --repo owner/name --sha <commit_sha>
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agent_langgraph.application.graph import build_graph
from agent_langgraph.entrypoints.wiring import build_deps_from_env


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the PR review agent against a commit.")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. fabrizzio178/Picadito")
    parser.add_argument("--sha", required=True, help="commit SHA to review")
    args = parser.parse_args()

    deps = build_deps_from_env()

    with SqliteSaver.from_conn_string("agent_langgraph.sqlite") as checkpointer:
        graph = build_graph(deps, checkpointer=checkpointer)
        thread_config = {"configurable": {"thread_id": f"{args.repo}@{args.sha}"}}

        result = graph.invoke(
            {"repo": args.repo, "commit_sha": args.sha},
            config=thread_config,
        )

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            print(json.dumps(payload, indent=2))
            answer = input("Approve posting this review? [y/N] ").strip().lower()
            result = graph.invoke(
                Command(resume={"approved": answer == "y"}),
                config=thread_config,
            )

        print(f"posted={result.get('posted')}")
        if result.get("comment_body"):
            print(result["comment_body"])


if __name__ == "__main__":
    sys.exit(main())
