"""GitHub REST adapter: loads `.pr-review.yml` from the PR's base branch.

Never from the PR head: a pull request must not be able to switch off its own
reviewers or rewrite the rules it is checked against.
"""

from __future__ import annotations

import requests

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.adapters.repo_config import (
    CONFIG_PATH,
    decode_base64_entry,
    parse_config,
)
from agent_langgraph.domain.models import RepoConfig, ReviewTarget

__all__ = ["CONFIG_PATH", "GitHubRestConfigProvider", "parse_config"]


class GitHubRestConfigProvider:
    def __init__(self, client: GitHubRestClient) -> None:
        self._client = client

    def load(self, target: ReviewTarget) -> RepoConfig:
        pull = self._client.get(f"/repos/{target.repo}/pulls/{target.pr_number}")
        base_sha = pull["base"]["sha"]
        try:
            entry = self._client.get(f"/repos/{target.repo}/contents/{CONFIG_PATH}?ref={base_sha}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return RepoConfig()
            raise
        return parse_config(decode_base64_entry(entry))
