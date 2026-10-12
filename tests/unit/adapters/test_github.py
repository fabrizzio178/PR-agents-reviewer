"""GitHub adapters against a mocked HTTP layer."""

from __future__ import annotations

import json

import pytest
import responses

from agent_langgraph.adapters.github.rest_client import GitHubRestClient
from agent_langgraph.adapters.github.rest_diff_provider import GitHubRestDiffProvider
from agent_langgraph.adapters.github.rest_review_publisher import (
    STATUS_MARKER,
    GitHubRestReviewPublisher,
)
from agent_langgraph.domain.models import InlineComment
from fakes import TARGET

API = "https://api.github.com/repos/acme/shop"


@pytest.fixture
def client() -> GitHubRestClient:
    return GitHubRestClient("test-token")


@responses.activate
def test_paginates_changed_files_and_skips_removed(client):
    page2 = f"{API}/pulls/7/files?per_page=100&page=2"
    responses.get(
        f"{API}/pulls/7/files",
        json=[{"filename": "a.py", "patch": "@@ -1 +1 @@\n+x", "additions": 1, "deletions": 0}],
        headers={"Link": f'<{page2}>; rel="next"'},
        match=[responses.matchers.query_param_matcher({"per_page": "100"})],
    )
    responses.get(
        page2,
        json=[
            {"filename": "logo.png", "additions": 0, "deletions": 0},
            {"filename": "gone.py", "status": "removed", "patch": "@@ -1 +0,0 @@\n-x"},
        ],
        match=[responses.matchers.query_param_matcher({"per_page": "100", "page": "2"})],
    )

    files = GitHubRestDiffProvider(client).get_changed_files(TARGET)

    assert [f.path for f in files] == ["a.py", "logo.png"]
    assert files[1].patch == ""
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"


@responses.activate
def test_status_comment_is_created_when_absent(client):
    responses.get(f"{API}/issues/7/comments", json=[{"id": 1, "body": "unrelated"}])
    created = responses.post(f"{API}/issues/7/comments", json={"id": 2})

    GitHubRestReviewPublisher(client).publish_status(TARGET, "hello")

    body = json.loads(created.calls[0].request.body)["body"]
    assert body == f"{STATUS_MARKER}\nhello"


@responses.activate
def test_status_comment_is_updated_in_place_when_present(client):
    responses.get(
        f"{API}/issues/7/comments",
        json=[{"id": 1, "body": "unrelated"}, {"id": 42, "body": f"{STATUS_MARKER}\nold"}],
    )
    patched = responses.patch(f"{API}/issues/comments/42", json={"id": 42})

    GitHubRestReviewPublisher(client).publish_status(TARGET, "new")

    assert json.loads(patched.calls[0].request.body)["body"].endswith("\nnew")
    assert len(responses.calls) == 2, "must not create a second comment"


@responses.activate
def test_inline_comments_skip_ones_already_posted(client):
    responses.get(
        f"{API}/pulls/7/comments", json=[{"path": "a.py", "line": 3, "body": "already there"}]
    )
    review = responses.post(f"{API}/pulls/7/reviews", json={"id": 9})

    GitHubRestReviewPublisher(client).publish_inline(
        TARGET,
        [InlineComment("a.py", 3, "already there"), InlineComment("a.py", 5, "new one")],
    )

    payload = json.loads(review.calls[0].request.body)
    assert payload["commit_id"] == TARGET.head_sha
    assert payload["event"] == "COMMENT"
    assert payload["comments"] == [{"path": "a.py", "line": 5, "side": "RIGHT", "body": "new one"}]


@responses.activate
def test_no_review_is_created_when_nothing_is_new(client):
    responses.get(f"{API}/pulls/7/comments", json=[{"path": "a.py", "line": 3, "body": "same"}])

    GitHubRestReviewPublisher(client).publish_inline(TARGET, [InlineComment("a.py", 3, "same")])

    assert len(responses.calls) == 1
