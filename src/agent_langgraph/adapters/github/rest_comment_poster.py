"""GitHub REST adapter: posts a review comment on a commit (MVP — no MCP yet)."""

from __future__ import annotations

import requests

GITHUB_API = "https://api.github.com"


class GitHubRestCommentPoster:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def post_comment(self, repo: str, ref: str, body: str) -> None:
        url = f"{GITHUB_API}/repos/{repo}/commits/{ref}/comments"
        response = requests.post(url, headers=self._headers, json={"body": body}, timeout=30)
        response.raise_for_status()
