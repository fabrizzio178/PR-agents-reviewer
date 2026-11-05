"""Entrypoint invoked by a GitLab CI merge request pipeline.

Two subcommands map to the pipeline's two jobs:

    analyze   Runs the graph for the MR of the current `merge_request_event`
              pipeline. It writes a dotenv report (`REVIEW_PAUSED`,
              `REVIEW_THREAD`) for the next job and, when it pauses at the
              human gate, leaves the SQLite checkpoint for the pipeline to keep
              as an artifact.
    resume    Runs in a manual job. Pressing "play" is the maintainer's
              approval, so it resumes the saved thread and publishes. If nothing
              is paused it exits cleanly: GitLab creates that job up front,
              before anyone knows whether the review will pause.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

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
from agent_langgraph.entrypoints.settings import GITLAB, Settings
from agent_langgraph.entrypoints.wiring import build_deps

DEFAULT_DOTENV = "review.env"
DEFAULT_REPORT = "review.md"
# dotenv values travel between jobs: keep the thread id to a safe alphabet.
_SAFE_THREAD = re.compile(r"^[A-Za-z0-9-]+$")


def target_from_ci(env: Mapping[str, str]) -> ReviewTarget:
    iid = env.get("CI_MERGE_REQUEST_IID")
    if not iid:
        raise RuntimeError("This entrypoint only runs in merge request pipelines.")
    return ReviewTarget(
        repo=env["CI_PROJECT_PATH"],
        pr_number=int(iid),
        # In a merge request pipeline this is the MR's head commit.
        head_sha=env["CI_COMMIT_SHA"],
    )


def thread_id_for(target: ReviewTarget, env: Mapping[str, str]) -> str:
    pipeline = env.get("CI_PIPELINE_ID") or "local"
    return f"mr{target.pr_number}-{target.head_sha[:8]}-{pipeline}"


def write_job_results(outcome: RunOutcome, dotenv_path: Path, report_path: Path) -> None:
    if not _SAFE_THREAD.match(outcome.thread_id):
        raise RuntimeError(f"unsafe thread id for a dotenv report: {outcome.thread_id!r}")
    dotenv_path.write_text(
        f"REVIEW_PAUSED={'true' if outcome.paused else 'false'}\n"
        f"REVIEW_THREAD={outcome.thread_id}\n",
        encoding="utf-8",
    )
    heading = (
        "## Waiting for approval: this is what will be published"
        if outcome.paused
        else f"## Review finished (posted={outcome.posted})"
    )
    report_path.write_text(f"{heading}\n\n{outcome.body}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="gitlab_ci_entrypoint")
    parser.add_argument("command", choices=["analyze", "resume"])
    parser.add_argument("--thread", help="thread id to resume (default: $REVIEW_THREAD)")
    parser.add_argument("--dotenv", default=DEFAULT_DOTENV, help="dotenv report to write")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="markdown report to write")
    args = parser.parse_args(argv)

    settings = Settings.from_env(os.environ, default_platform=GITLAB)
    deps = build_deps(settings)

    with open_checkpointer(settings.checkpoint_path) as checkpointer:
        graph = build_graph(deps, checkpointer=checkpointer)
        if args.command == "analyze":
            target = target_from_ci(os.environ)
            outcome = start_review(graph, target, thread_id_for(target, os.environ))
        else:
            thread = args.thread or os.environ.get("REVIEW_THREAD")
            if not thread:
                print("No review is waiting for approval.")
                return 0
            try:
                outcome = resume_review(graph, thread, approved=True)
            except NoPausedReviewError:
                print("No review is waiting for approval.")
                return 0

    write_job_results(outcome, Path(args.dotenv), Path(args.report))
    print(outcome.body)
    print(f"\npaused={outcome.paused} posted={outcome.posted} thread={outcome.thread_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
