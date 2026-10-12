"""GitHub REST adapter: fetches a pull request's changed files (MVP — no MCP yet)."""

from __future__ import annotations

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.domain.models import FileChange, ReviewTarget


class GitHubRestDiffProvider:
    def __init__(self, client: GitHubRestClient) -> None:
        self._client = client

    def get_changed_files(self, target: ReviewTarget) -> list[FileChange]:
        path = f"/repos/{target.repo}/pulls/{target.pr_number}/files"
        return [
            FileChange(
                path=f["filename"],
                # Binary and very large files come back without a patch.
                patch=f.get("patch", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
            )
            for f in self._client.paginate(path)
            if f.get("status") != "removed"
        ]
