"""Local entrypoint: run the graph against a real pull request.

Usage:
    uv run review run --repo owner/name --pr 12
    uv run review resume --thread <thread_id> --approve
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from dotenv import load_dotenv

from agent_langgraph.application.graph import build_graph
from agent_langgraph.domain.models import ReviewTarget
from agent_langgraph.entrypoints.logging_setup import configure_logging
from agent_langgraph.entrypoints.runner import (
    NoPausedReviewError,
    RunOutcome,
    open_checkpointer,
    resume_review,
    start_review,
)
from agent_langgraph.entrypoints.settings import Settings
from agent_langgraph.entrypoints.wiring import build_deps, resolve_head_sha


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review", description="PR review agent.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="review a pull request")
    run.add_argument("--repo", required=True, help="owner/name")
    run.add_argument("--pr", required=True, type=int, help="pull request number")
    run.add_argument("--sha", help="head commit SHA (default: the PR's current head)")

    resume = commands.add_parser("resume", help="decide on a review paused for approval")
    resume.add_argument("--thread", required=True, help="thread id printed by the paused run")
    decision = resume.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true", help="publish the findings")
    decision.add_argument("--reject", action="store_true", help="withhold the findings")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_logging()
    args = build_parser().parse_args(argv)
    settings = Settings.from_env(os.environ)
    deps = build_deps(settings)

    with open_checkpointer(settings.checkpoint_path) as checkpointer:
        graph = build_graph(deps, checkpointer=checkpointer)

        if args.command == "resume":
            try:
                outcome = resume_review(graph, args.thread, approved=args.approve)
            except NoPausedReviewError as exc:
                print(exc, file=sys.stderr)
                return 1
            _report(outcome)
            return 0

        sha = args.sha or resolve_head_sha(settings, args.repo, args.pr)
        target = ReviewTarget(repo=args.repo, pr_number=args.pr, head_sha=sha)
        # A fresh thread per run: reusing one would append to its saved findings.
        thread_id = f"{args.repo}#{args.pr}@{sha[:7]}:{uuid.uuid4().hex[:8]}"
        outcome = start_review(graph, target, thread_id)

        if outcome.paused:
            print(outcome.body)
            print(f"\nPaused for approval. thread={outcome.thread_id}")
            if not sys.stdin.isatty():
                print(f"Decide with: review resume --thread '{outcome.thread_id}' --approve")
                return 0
            answer = input("Approve posting this review? [y/N] ").strip().lower()
            outcome = resume_review(graph, thread_id, approved=answer == "y")

        _report(outcome)
    return 0


def _report(outcome: RunOutcome) -> None:
    print(f"posted={outcome.posted}")
    if outcome.body:
        print(outcome.body)


if __name__ == "__main__":
    sys.exit(main())
