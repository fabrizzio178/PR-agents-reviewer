"""GitLab adapters against a mocked HTTP layer."""

from __future__ import annotations

import base64
import json

import pytest
import responses

from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient
from agent_langgraph.adapters.gitlab.rest_config_provider import GitLabRestConfigProvider
from agent_langgraph.adapters.gitlab.rest_diff_provider import GitLabRestDiffProvider
from agent_langgraph.adapters.gitlab.rest_review_publisher import (
    STATUS_MARKER,
    GitLabRestReviewPublisher,
)
from agent_langgraph.domain.errors import ConfigError
from agent_langgraph.domain.models import InlineComment, RepoConfig, Severity
from fakes import TARGET

API = "https://gitlab.example.com/api/v4"
PROJECT = f"{API}/projects/acme%2Fshop"
MR = f"{PROJECT}/merge_requests/7"
REFS = {"base_sha": "base000", "start_sha": "start00", "head_sha": "head000"}
# Line 1 is context (old 1), line 2 is added, line 3 is context (old 2).
PATCH = "@@ -1,2 +1,3 @@\n keep\n+added\n tail"


@pytest.fixture
def client() -> GitLabRestClient:
    return GitLabRestClient("glpat-test", f"{API}/")


@responses.activate
def test_paginates_diffs_counts_lines_and_skips_deleted(client):
    page2 = f"{MR}/diffs?per_page=100&page=2"
    responses.get(
        f"{MR}/diffs",
        json=[{"new_path": "a.py", "old_path": "a.py", "diff": "@@ -1 +1,2 @@\n-x\n+y\n+z"}],
        headers={"Link": f'<{page2}>; rel="next"'},
        match=[responses.matchers.query_param_matcher({"per_page": "100"})],
    )
    responses.get(
        page2,
        json=[
            {"new_path": "logo.png", "old_path": "logo.png", "diff": ""},
            {
                "new_path": "gone.py",
                "old_path": "gone.py",
                "diff": "@@ -1 +0,0 @@\n-x",
                "deleted_file": True,
            },
        ],
        match=[responses.matchers.query_param_matcher({"per_page": "100", "page": "2"})],
    )

    files = GitLabRestDiffProvider(client).get_changed_files(TARGET)

    assert [f.path for f in files] == ["a.py", "logo.png"]
    assert (files[0].additions, files[0].deletions) == (2, 1)
    assert files[1].patch == ""
    assert responses.calls[0].request.headers["PRIVATE-TOKEN"] == "glpat-test"


@responses.activate
def test_config_is_read_from_the_target_branch_commit(client):
    responses.get(MR, json={"diff_refs": REFS, "target_branch": "main"})
    content = base64.b64encode(b"gate_severity: medium\n").decode()
    responses.get(
        f"{PROJECT}/repository/files/.pr-review.yml",
        json={"encoding": "base64", "content": content},
        match=[responses.matchers.query_param_matcher({"ref": "start00"})],
    )

    config = GitLabRestConfigProvider(client).load(TARGET)

    assert config.gate_severity == Severity.MEDIUM


@responses.activate
def test_missing_config_means_defaults(client):
    responses.get(MR, json={"diff_refs": None, "target_branch": "main"})
    responses.get(
        f"{PROJECT}/repository/files/.pr-review.yml",
        status=404,
        match=[responses.matchers.query_param_matcher({"ref": "main"})],
    )

    assert GitLabRestConfigProvider(client).load(TARGET) == RepoConfig()


@responses.activate
def test_invalid_config_raises_config_error(client):
    responses.get(MR, json={"diff_refs": REFS, "target_branch": "main"})
    content = base64.b64encode(b"unknown_key: 1\n").decode()
    responses.get(
        f"{PROJECT}/repository/files/.pr-review.yml",
        json={"encoding": "base64", "content": content},
    )

    with pytest.raises(ConfigError):
        GitLabRestConfigProvider(client).load(TARGET)


@responses.activate
def test_status_note_is_created_when_absent(client):
    responses.get(f"{MR}/notes", json=[{"id": 1, "body": "unrelated"}])
    created = responses.post(f"{MR}/notes", json={"id": 2})

    GitLabRestReviewPublisher(client).publish_status(TARGET, "hello")

    assert json.loads(created.calls[0].request.body)["body"] == f"{STATUS_MARKER}\nhello"


@responses.activate
def test_status_note_is_updated_in_place_when_present(client):
    responses.get(
        f"{MR}/notes",
        json=[{"id": 1, "body": "unrelated"}, {"id": 42, "body": f"{STATUS_MARKER}\nold"}],
    )
    updated = responses.put(f"{MR}/notes/42", json={"id": 42})

    GitLabRestReviewPublisher(client).publish_status(TARGET, "new")

    assert json.loads(updated.calls[0].request.body)["body"].endswith("\nnew")
    assert len(responses.calls) == 2, "must not create a second note"


def _mock_inline_reads(existing_notes: list[dict[str, object]]) -> None:
    responses.get(f"{MR}/discussions", json=[{"notes": existing_notes}])
    responses.get(MR, json={"diff_refs": REFS})
    responses.get(f"{MR}/diffs", json=[{"new_path": "a.py", "old_path": "old_a.py", "diff": PATCH}])


@responses.activate
def test_inline_on_added_line_sends_only_the_new_line(client):
    _mock_inline_reads([])
    created = responses.post(f"{MR}/discussions", json={"id": "d1"})

    GitLabRestReviewPublisher(client).publish_inline(
        TARGET, [InlineComment(path="a.py", line=2, body="bad")]
    )

    payload = json.loads(created.calls[0].request.body)
    assert payload["body"] == "bad"
    assert payload["position"] == {
        "position_type": "text",
        "base_sha": "base000",
        "start_sha": "start00",
        "head_sha": "head000",
        "old_path": "old_a.py",
        "new_path": "a.py",
        "new_line": 2,
    }


@responses.activate
def test_inline_on_context_line_sends_both_lines(client):
    _mock_inline_reads([])
    created = responses.post(f"{MR}/discussions", json={"id": "d1"})

    GitLabRestReviewPublisher(client).publish_inline(
        TARGET, [InlineComment(path="a.py", line=3, body="hmm")]
    )

    position = json.loads(created.calls[0].request.body)["position"]
    assert (position["new_line"], position["old_line"]) == (3, 2)


@responses.activate
def test_inline_skips_comments_already_posted(client):
    responses.get(
        f"{MR}/discussions",
        json=[
            {"notes": [{"body": "general note"}]},
            {"notes": [{"body": "dup", "position": {"new_path": "a.py", "new_line": 2}}]},
        ],
    )

    GitLabRestReviewPublisher(client).publish_inline(
        TARGET, [InlineComment(path="a.py", line=2, body="dup")]
    )

    assert len(responses.calls) == 1, "nothing new: no further reads or writes"


@responses.activate
def test_inline_rejected_position_does_not_abort_the_rest(client):
    _mock_inline_reads([])
    responses.post(f"{MR}/discussions", status=400, json={"message": "line_code invalid"})
    responses.post(f"{MR}/discussions", json={"id": "d2"})

    GitLabRestReviewPublisher(client).publish_inline(
        TARGET,
        [
            InlineComment(path="a.py", line=1, body="first"),
            InlineComment(path="a.py", line=2, body="second"),
            InlineComment(path="other.py", line=9, body="not in the diff"),
        ],
    )

    posted = [c for c in responses.calls if c.request.method == "POST"]
    assert [json.loads(c.request.body)["body"] for c in posted] == ["first", "second"]


@responses.activate
def test_inline_server_error_is_raised(client):
    _mock_inline_reads([])
    responses.post(f"{MR}/discussions", status=403, json={"message": "forbidden"})

    with pytest.raises(Exception, match="403"):
        GitLabRestReviewPublisher(client).publish_inline(
            TARGET, [InlineComment(path="a.py", line=2, body="x")]
        )
