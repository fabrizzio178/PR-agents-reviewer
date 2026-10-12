"""Entrypoint invoked by the GitHub Actions workflow.

Two subcommands map to the workflow's two jobs:

    analyze   Runs the graph for the PR in the event payload. If it pauses at
              the human gate it sets the job output `paused=true`; the
              workflow then uploads the SQLite checkpoint as an artifact.
    resume    Runs in a job gated by a protected Environment. Reaching it
              means a maintainer approved, so it resumes the saved thread.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from agent_langgraph.application.graph import build_graph
from agent_langgraph.domain.models import ReviewTarget
from agent_langgraph.entrypoints.logging_setup import configure_logging
from agent_langgraph.entrypoints.runner import (
    RunOutcome,
    open_checkpointer,
    resume_review,
    start_review,
)
from agent_langgraph.entrypoints.settings import Settings
from agent_langgraph.entrypoints.wiring import build_deps


def target_from_event(env: Mapping[str, str]) -> ReviewTarget:
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pull = event.get("pull_request")
    if not pull:
        raise RuntimeError("This entrypoint only handles pull_request events.")
    # Not GITHUB_SHA: on pull_request events that is the temporary merge commit.
    return ReviewTarget(
        repo=env["GITHUB_REPOSITORY"],
        pr_number=int(pull["number"]),
        head_sha=str(pull["head"]["sha"]),
    )


def thread_id_for(target: ReviewTarget, env: Mapping[str, str]) -> str:
    run = f"{env.get('GITHUB_RUN_ID', 'local')}.{env.get('GITHUB_RUN_ATTEMPT', '1')}"
    return f"{target.repo}#{target.pr_number}@{target.head_sha[:7]}:{run}"


def write_job_results(outcome: RunOutcome, env: Mapping[str, str]) -> None:
    output_path = env.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(f"paused={'true' if outcome.paused else 'false'}\n")
            fh.write(f"thread_id={outcome.thread_id}\n")
    summary_path = env.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        heading = (
            "## ⏸️ Waiting for approval — this is what will be published"
            if outcome.paused
            else f"## Review finished (posted={outcome.posted})"
        )
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"{heading}\n\n{outcome.body}\n")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="github_action_entrypoint")
    parser.add_argument("command", choices=["analyze", "resume"])
    parser.add_argument("--thread", help="thread id to resume (resume only)")
    args = parser.parse_args(argv)

    settings = Settings.from_env(os.environ)
    deps = build_deps(settings)

    with open_checkpointer(settings.checkpoint_path) as checkpointer:
        graph = build_graph(deps, checkpointer=checkpointer)
        if args.command == "analyze":
            target = target_from_event(os.environ)
            outcome = start_review(graph, target, thread_id_for(target, os.environ))
        else:
            if not args.thread:
                parser.error("resume requires --thread")
            outcome = resume_review(graph, args.thread, approved=True)

    write_job_results(outcome, os.environ)
    print(f"paused={outcome.paused} posted={outcome.posted} thread={outcome.thread_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
