"""GitHub REST adapter: publishes the review on a pull request, idempotently.

The summary is one "sticky" issue comment found again by a hidden marker and
edited in place; inline comments are skipped when an identical one already
sits on the same line. Re-running the publish step never duplicates anything.
"""

from __future__ import annotations

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.domain.models import InlineComment, ReviewTarget

STATUS_MARKER = "<!-- pr-review-agent:status -->"


class GitHubRestReviewPublisher:
    def __init__(self, client: GitHubRestClient) -> None:
        self._client = client

    def publish_status(self, target: ReviewTarget, body: str) -> None:
        marked_body = f"{STATUS_MARKER}\n{body}"
        comments_path = f"/repos/{target.repo}/issues/{target.pr_number}/comments"
        for comment in self._client.paginate(comments_path):
            if (comment.get("body") or "").startswith(STATUS_MARKER):
                self._client.patch(
                    f"/repos/{target.repo}/issues/comments/{comment['id']}",
                    {"body": marked_body},
                )
                return
        self._client.post(comments_path, {"body": marked_body})

    def publish_inline(self, target: ReviewTarget, comments: list[InlineComment]) -> None:
        pulls_path = f"/repos/{target.repo}/pulls/{target.pr_number}"
        existing = {
            (c.get("path"), c.get("line"), c.get("body"))
            for c in self._client.paginate(f"{pulls_path}/comments")
        }
        new = [c for c in comments if (c.path, c.line, c.body) not in existing]
        if not new:
            return
        self._client.post(
            f"{pulls_path}/reviews",
            {
                "commit_id": target.head_sha,
                "event": "COMMENT",
                "comments": [
                    {"path": c.path, "line": c.line, "side": "RIGHT", "body": c.body} for c in new
                ],
            },
        )
