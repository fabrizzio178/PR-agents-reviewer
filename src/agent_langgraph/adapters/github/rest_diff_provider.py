"""GitHub REST adapter: fetches a commit's changed files (MVP — no MCP yet)."""

from __future__ import annotations

import requests

from agent_langgraph.domain.models import FileChange

GITHUB_API = "https://api.github.com"


class GitHubRestDiffProvider:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def get_changed_files(self, repo: str, ref: str) -> list[FileChange]:
        url = f"{GITHUB_API}/repos/{repo}/commits/{ref}"
        response = requests.get(url, headers=self._headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return [
            FileChange(
                path=f["filename"],
                patch=f.get("patch", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
            )
            for f in payload.get("files", [])
        ]
