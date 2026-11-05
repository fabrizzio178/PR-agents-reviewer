"""GitLab REST adapter: fetches a merge request's changed files.

GitLab's `diff` field is the same unified-diff body GitHub returns as `patch`
(it starts at the first `@@` hunk, without file headers), so the domain diff
helpers work on it unchanged. GitLab does not report line counts per file, so
they are counted from the patch.
"""

from __future__ import annotations

from typing import Any

from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient, merge_request_path
from agent_langgraph.domain.models import FileChange, ReviewTarget


class GitLabRestDiffProvider:
    def __init__(self, client: GitLabRestClient) -> None:
        self._client = client

    def get_changed_files(self, target: ReviewTarget) -> list[FileChange]:
        path = f"{merge_request_path(target.repo, target.pr_number)}/diffs"
        return [
            _to_file_change(d) for d in self._client.paginate(path) if not d.get("deleted_file")
        ]


def _to_file_change(entry: dict[str, Any]) -> FileChange:
    # Binary files, and diffs GitLab considers too large, come back with an empty diff.
    patch = entry.get("diff") or ""
    lines = patch.splitlines()
    return FileChange(
        path=entry["new_path"],
        patch=patch,
        additions=sum(1 for line in lines if line.startswith("+")),
        deletions=sum(1 for line in lines if line.startswith("-")),
    )
