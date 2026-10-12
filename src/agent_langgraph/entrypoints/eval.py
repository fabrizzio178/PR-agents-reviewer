"""Runs the eval dataset against the real model and prints per-agent metrics.

Usage:
    uv run eval                       # report only
    uv run eval --fail-under          # exit 1 if below the SPEC thresholds
    uv run eval --agent security
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_langgraph.application.nodes.supervisor import CODE_ARCH, SECURITY
from agent_langgraph.entrypoints.settings import LLMSettings
from agent_langgraph.entrypoints.wiring import build_llm
from agent_langgraph.evals.scoring import AgentScore, load_cases, run_evals

DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "evals" / "dataset.jsonl"
# Success criteria from docs/SPEC.md §10.
MIN_RECALL = {SECURITY: 0.8, CODE_ARCH: 0.6}


def meets_thresholds(scores: dict[str, AgentScore]) -> bool:
    return all(
        score.recall >= MIN_RECALL.get(agent, 0.0) and score.high_on_clean == 0
        for agent, score in scores.items()
    )


def render_report(scores: dict[str, AgentScore], model: str) -> str:
    lines = [
        f"Model: {model}",
        "",
        "| agent | cases | recall | precision | FP on clean | HIGH on clean | errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for agent, s in sorted(scores.items()):
        lines.append(
            f"| {agent} | {s.cases} | {s.recall:.2f} | {s.precision:.2f} "
            f"| {s.false_positives} | {s.high_on_clean} | {s.errors} |"
        )
    failed = {agent: s.failed_cases for agent, s in scores.items() if s.failed_cases}
    if failed:
        lines.append("")
        lines += [f"Failed cases ({agent}): {', '.join(ids)}" for agent, ids in failed.items()]
    for score in scores.values():
        lines += [f"Error in {message}" for message in score.error_messages]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="eval", description="Evaluate the review agents.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--agent", choices=[SECURITY, CODE_ARCH], help="only this agent")
    parser.add_argument(
        "--delay", type=float, default=4.0, help="seconds between calls (free-tier rate limit)"
    )
    parser.add_argument("--fail-under", action="store_true", help="exit 1 below SPEC thresholds")
    args = parser.parse_args(argv)

    try:
        llm_settings = LLMSettings.from_env(os.environ)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2
    model = f"{llm_settings.provider}/{llm_settings.model}"

    cases = [c for c in load_cases(args.dataset) if args.agent in (None, c.agent)]
    scores = run_evals(cases, build_llm(llm_settings), delay_seconds=args.delay)
    print(render_report(scores, model))

    if args.fail_under and not meets_thresholds(scores):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
