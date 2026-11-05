"""Thin GitLab REST client shared by the GitLab adapters: auth, retries, pagination.

Works against any GitLab instance (gitlab.com or self-managed): the base URL
is the instance's API root, e.g. `https://gitlab.example.com/api/v4`, which in
a CI job is the predefined `CI_API_V4_URL`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_TIMEOUT_SECONDS = 30


def project_path(repo: str) -> str:
    """API prefix for a project given its full path (`group/sub/name`) or numeric id."""
    return f"/projects/{quote(repo, safe='')}"


def merge_request_path(repo: str, iid: int) -> str:
    return f"{project_path(repo)}/merge_requests/{iid}"


class GitLabRestClient:
    def __init__(self, token: str, api_url: str) -> None:
        self._base_url = api_url.rstrip("/")
        self._session = requests.Session()
        # Project and personal access tokens both authenticate with this header.
        self._session.headers.update({"PRIVATE-TOKEN": token})
        # Only idempotent reads are retried at the transport level; writes are
        # retried by the graph's RetryPolicy, where the publisher's own
        # idempotency makes a repeat safe.
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.mount("http://", HTTPAdapter(max_retries=retry))

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        return self._request("GET", self._base_url + path, params=params).json()

    def get_text(self, path: str) -> str:
        """For endpoints that answer plain text, such as a job log."""
        return self._request("GET", self._base_url + path).text

    def paginate(self, path: str, per_page: int = 100) -> Iterator[Any]:
        """Yield every item of a list endpoint, following `Link: rel="next"`."""
        url: str | None = f"{self._base_url}{path}?per_page={per_page}"
        while url:
            response = self._request("GET", url)
            yield from response.json()
            url = response.links.get("next", {}).get("url")

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", self._base_url + path, json=payload).json()

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PUT", self._base_url + path, json=payload).json()

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self._session.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        response.raise_for_status()
        return response
