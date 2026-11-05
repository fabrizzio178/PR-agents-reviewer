"""GitLab IncidentSource: reads a pipeline, its jobs, failed-job logs and recent commits.

Every call is a GET. "Last good" is the newest successful pipeline on the same
ref older than this one; the commits between the two are what changed.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import requests

from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient, project_path
from agent_langgraph.incidents.models import CommitInfo, IncidentContext, JobRun

# Jobs still in these states say nothing about the failure (the investigation's
# own job is one of them).
_UNFINISHED = {"created", "pending", "running", "waiting_for_resource", "preparing", "scheduled"}
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SECTION = re.compile(r"section_(?:start|end):\d+:[\w.-]+(?:\[[^\]]*\])?")


class GitLabIncidentSource:
    def __init__(self, client: GitLabRestClient, max_log_lines: int = 150) -> None:
        self._client = client
        self._max_log_lines = max_log_lines

    def collect(self, project: str, pipeline_id: int) -> IncidentContext:
        base = project_path(project)
        pipeline = self._client.get(f"{base}/pipelines/{pipeline_id}")
        jobs = [
            self._job(base, raw)
            for raw in self._client.paginate(f"{base}/pipelines/{pipeline_id}/jobs")
            if raw.get("status") not in _UNFINISHED
        ]
        jobs.sort(key=lambda j: (j.started_at or "", j.id))

        last_good = self._last_good(base, pipeline["ref"], pipeline_id)
        commits: list[CommitInfo] = []
        changed: list[str] = []
        if last_good and last_good["sha"] != pipeline["sha"]:
            compare = self._client.get(
                f"{base}/repository/compare",
                params={"from": last_good["sha"], "to": pipeline["sha"]},
            )
            commits = [
                CommitInfo(
                    sha=c["id"],
                    title=c.get("title") or "",
                    author=c.get("author_name") or "",
                    created_at=c.get("created_at") or "",
                )
                for c in compare.get("commits", [])
            ]
            changed = sorted(
                {d.get("new_path") or d.get("old_path") or "" for d in compare.get("diffs", [])}
                - {""}
            )

        return IncidentContext(
            project=project,
            pipeline_id=pipeline_id,
            pipeline_url=pipeline.get("web_url") or "",
            ref=pipeline["ref"],
            sha=pipeline["sha"],
            created_at=pipeline.get("created_at") or "",
            jobs=jobs,
            last_good_pipeline_id=last_good["id"] if last_good else None,
            last_good_sha=last_good["sha"] if last_good else None,
            commits=commits,
            changed_files=changed,
        )

    def _job(self, base: str, raw: dict[str, Any]) -> JobRun:
        job = JobRun(
            id=raw["id"],
            name=raw["name"],
            stage=raw.get("stage") or "",
            status=raw["status"],
            allow_failure=bool(raw.get("allow_failure")),
            web_url=raw.get("web_url") or "",
            started_at=raw.get("started_at"),
            finished_at=raw.get("finished_at"),
        )
        if not job.blocking_failure:
            return job
        try:
            log = self._client.get_text(f"{base}/jobs/{job.id}/trace")
        except requests.HTTPError:
            return job
        return replace(job, log_tail=self._tail(log))

    def _last_good(self, base: str, ref: str, pipeline_id: int) -> dict[str, Any] | None:
        candidates = self._client.get(
            f"{base}/pipelines",
            params={"ref": ref, "status": "success", "per_page": "20"},
        )
        older = [p for p in candidates if p["id"] < pipeline_id]
        return max(older, key=lambda p: p["id"]) if older else None

    def _tail(self, log: str) -> str:
        clean = _SECTION.sub("", _ANSI.sub("", log)).replace("\r", "")
        lines = [line for line in clean.split("\n") if line.strip()]
        return "\n".join(lines[-self._max_log_lines :])
