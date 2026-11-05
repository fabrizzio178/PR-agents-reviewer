"""Entrypoint for the incident job of a GitLab pipeline (`when: on_failure`).

Investigates the current pipeline (`CI_PIPELINE_ID`), writes the report to a
markdown file the job keeps as an artifact, and opens or updates an issue with
it. `--dry-run` skips the issue.

Environment: CI_PROJECT_PATH, CI_PIPELINE_ID, GITLAB_TOKEN, CI_API_V4_URL (or
GITLAB_API_URL) and the same LLM variables as the reviewer.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agent_langgraph.adapters.gitlab.incident_publisher import GitLabIssuePublisher
from agent_langgraph.adapters.gitlab.incident_source import GitLabIncidentSource
from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient
from agent_langgraph.entrypoints.logging_setup import configure_logging
from agent_langgraph.entrypoints.settings import GITLAB, LLMSettings, PlatformSettings
from agent_langgraph.entrypoints.wiring import build_llm
from agent_langgraph.incidents.graph import IncidentDeps, build_incident_graph
from agent_langgraph.incidents.incident_map import DEFAULT_PATH, load_incident_map

DEFAULT_REPORT = "incident.md"


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="gitlab_incident_entrypoint")
    parser.add_argument("--config", default=DEFAULT_PATH, help="service map and runbook")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="markdown report to write")
    parser.add_argument("--pipeline", type=int, help="pipeline id (default: $CI_PIPELINE_ID)")
    parser.add_argument("--dry-run", action="store_true", help="do not open an issue")
    args = parser.parse_args(argv)

    env = os.environ
    project = env.get("CI_PROJECT_PATH")
    pipeline_id = args.pipeline or int(env.get("CI_PIPELINE_ID") or 0)
    if not project or not pipeline_id:
        raise RuntimeError("CI_PROJECT_PATH and CI_PIPELINE_ID (or --pipeline) are required")

    platform = PlatformSettings.from_env({**env, "REVIEW_PLATFORM": GITLAB}, GITLAB)
    client = GitLabRestClient(platform.token, platform.api_url)
    incident_map, map_warning = load_incident_map(Path(args.config))
    deps = IncidentDeps(
        source=GitLabIncidentSource(client),
        llm=build_llm(LLMSettings.from_env(env)),
        publisher=None if args.dry_run else GitLabIssuePublisher(client),
    )

    result = build_incident_graph(deps).invoke(
        {
            "project": project,
            "pipeline_id": pipeline_id,
            "incident_map": incident_map,
            "map_warning": map_warning,
        }
    )
    Path(args.report).write_text(result["report"] + "\n", encoding="utf-8")
    print(result["report"])
    if result.get("issue_url"):
        print(f"\nIssue: {result['issue_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
