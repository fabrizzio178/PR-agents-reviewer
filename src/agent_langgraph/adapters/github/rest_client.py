"""Thin GitHub REST client shared by the GitHub adapters: auth, retries, pagination."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GITHUB_API = "https://api.github.com"
_TIMEOUT_SECONDS = 30


class GitHubRestClient:
    def __init__(self, token: str, base_url: str = GITHUB_API) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
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

    def get(self, path: str) -> Any:
        return self._request("GET", self._base_url + path).json()

    def paginate(self, path: str, per_page: int = 100) -> Iterator[Any]:
        """Yield every item of a list endpoint, following `Link: rel="next"`."""
        url: str | None = f"{self._base_url}{path}?per_page={per_page}"
        while url:
            response = self._request("GET", url)
            yield from response.json()
            url = response.links.get("next", {}).get("url")

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", self._base_url + path, json=payload).json()

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PATCH", self._base_url + path, json=payload).json()

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self._session.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        response.raise_for_status()
        return response
