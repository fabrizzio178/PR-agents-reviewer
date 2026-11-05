"""GitLab REST adapter: publishes the review on a merge request, idempotently.

The summary is one "sticky" MR note found again by a hidden marker and edited
in place. Each inline finding is its own diff discussion (GitLab has no
batched review like GitHub's), skipped when an identical one already sits on
the same line. Re-running the publish step never duplicates anything.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient, merge_request_path
from agent_langgraph.domain.diff import line_positions
from agent_langgraph.domain.models import InlineComment, ReviewTarget

STATUS_MARKER = "<!-- pr-review-agent:status -->"

log = logging.getLogger(__name__)


class GitLabRestReviewPublisher:
    def __init__(self, client: GitLabRestClient) -> None:
        self._client = client

    def publish_status(self, target: ReviewTarget, body: str) -> None:
        marked_body = f"{STATUS_MARKER}\n{body}"
        notes_path = f"{merge_request_path(target.repo, target.pr_number)}/notes"
        for note in self._client.paginate(notes_path):
            if (note.get("body") or "").startswith(STATUS_MARKER):
                self._client.put(f"{notes_path}/{note['id']}", {"body": marked_body})
                return
        self._client.post(notes_path, {"body": marked_body})

    def publish_inline(self, target: ReviewTarget, comments: list[InlineComment]) -> None:
        mr_path = merge_request_path(target.repo, target.pr_number)
        existing = {
            (pos.get("new_path"), pos.get("new_line"), note.get("body"))
            for discussion in self._client.paginate(f"{mr_path}/discussions")
            for note in discussion.get("notes", [])
            if (pos := note.get("position") or {})
        }
        new = [c for c in comments if (c.path, c.line, c.body) not in existing]
        if not new:
            return

        refs = self._client.get(mr_path)["diff_refs"]
        files = {d["new_path"]: d for d in self._client.paginate(f"{mr_path}/diffs")}
        for comment in new:
            position = _position(comment, files.get(comment.path), refs)
            if position is None:
                log.warning(
                    "skipping inline comment outside the diff: %s:%s", comment.path, comment.line
                )
                continue
            try:
                self._client.post(
                    f"{mr_path}/discussions", {"body": comment.body, "position": position}
                )
            except requests.HTTPError as exc:
                # GitLab rejects a position it cannot place (400). The finding is still in
                # the summary note, so one misplaced line must not abort the others.
                if exc.response is None or exc.response.status_code != 400:
                    raise
                log.warning("GitLab rejected inline comment on %s:%s", comment.path, comment.line)


def _position(
    comment: InlineComment, diff: dict[str, Any] | None, refs: dict[str, str]
) -> dict[str, Any] | None:
    if diff is None:
        return None
    lines = line_positions(diff.get("diff") or "")
    if comment.line not in lines:
        return None
    position: dict[str, Any] = {
        "position_type": "text",
        "base_sha": refs["base_sha"],
        "start_sha": refs["start_sha"],
        "head_sha": refs["head_sha"],
        "old_path": diff.get("old_path") or comment.path,
        "new_path": comment.path,
        "new_line": comment.line,
    }
    old_line = lines[comment.line]
    if old_line is not None:
        # An unchanged (context) line: GitLab needs both sides to anchor it.
        position["old_line"] = old_line
    return position
