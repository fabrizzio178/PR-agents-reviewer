"""GitLab REST adapter: loads `.pr-review.yml` from the merge request's target branch.

Never from the MR head: a merge request must not be able to switch off its own
reviewers or rewrite the rules it is checked against. The file is read at
`diff_refs.start_sha`, the target branch commit the MR diff was computed
against, so a config merged into the target branch applies to open MRs.
"""

from __future__ import annotations

from urllib.parse import quote

import requests

from agent_langgraph.adapters.gitlab.rest_client import (
    GitLabRestClient,
    merge_request_path,
    project_path,
)
from agent_langgraph.adapters.repo_config import CONFIG_PATH, decode_base64_entry, parse_config
from agent_langgraph.domain.models import RepoConfig, ReviewTarget


class GitLabRestConfigProvider:
    def __init__(self, client: GitLabRestClient) -> None:
        self._client = client

    def load(self, target: ReviewTarget) -> RepoConfig:
        merge_request = self._client.get(merge_request_path(target.repo, target.pr_number))
        refs = merge_request.get("diff_refs") or {}
        ref = refs.get("start_sha") or merge_request["target_branch"]
        file_path = f"{project_path(target.repo)}/repository/files/{quote(CONFIG_PATH, safe='')}"
        try:
            entry = self._client.get(file_path, params={"ref": ref})
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return RepoConfig()
            raise
        return parse_config(decode_base64_entry(entry))
