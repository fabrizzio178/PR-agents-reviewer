"""GitLab incident adapters against a mocked HTTP layer."""

from __future__ import annotations

import json

import pytest
import responses

from agent_langgraph.adapters.gitlab.incident_publisher import (
    LABEL,
    GitLabIssuePublisher,
    marker,
)
from agent_langgraph.adapters.gitlab.incident_source import GitLabIncidentSource
from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient

API = "https://gitlab.example.com/api/v4"
PROJECT = f"{API}/projects/acme%2Fshop"


@pytest.fixture
def client() -> GitLabRestClient:
    return GitLabRestClient("glpat-test", API)


def _job(id_: int, name: str, status: str, allow_failure: bool = False) -> dict:
    return {
        "id": id_,
        "name": name,
        "stage": "testing",
        "status": status,
        "allow_failure": allow_failure,
        "web_url": f"https://gitlab.example.com/jobs/{id_}",
        "started_at": f"2026-11-05T10:0{id_}:00Z",
        "finished_at": f"2026-11-05T10:0{id_}:30Z",
    }


@responses.activate
def test_source_reads_failed_logs_and_changes_since_last_good(client):
    responses.get(
        f"{PROJECT}/pipelines/200",
        json={
            "id": 200,
            "ref": "main",
            "sha": "new000",
            "web_url": "https://gitlab.example.com/p/200",
            "created_at": "2026-11-05T10:00:00Z",
        },
    )
    responses.get(
        f"{PROJECT}/pipelines/200/jobs",
        json=[
            _job(1, "build", "success"),
            _job(2, "sast", "failed", allow_failure=True),
            _job(3, "desplegar-testing", "failed"),
            _job(4, "investigar-incidente", "running"),
        ],
    )
    log = "\x1b[0Ksection_start:1:step_script\r\x1b[0K" + "\n".join(f"line {n}" for n in range(300))
    responses.get(f"{PROJECT}/jobs/3/trace", body=log)
    responses.get(
        f"{PROJECT}/pipelines",
        json=[{"id": 210, "sha": "later"}, {"id": 190, "sha": "old000"}, {"id": 150, "sha": "x"}],
        match=[
            responses.matchers.query_param_matcher(
                {"ref": "main", "status": "success", "per_page": "20"}
            )
        ],
    )
    responses.get(
        f"{PROJECT}/repository/compare",
        json={
            "commits": [
                {
                    "id": "new000",
                    "title": "Change DB user",
                    "author_name": "dev",
                    "created_at": "2026-11-05T09:58:00Z",
                }
            ],
            "diffs": [{"new_path": "apps/api/a.properties", "old_path": "apps/api/a.properties"}],
        },
        match=[responses.matchers.query_param_matcher({"from": "old000", "to": "new000"})],
    )

    context = GitLabIncidentSource(client, max_log_lines=5).collect("acme/shop", 200)

    assert [j.name for j in context.jobs] == ["build", "sast", "desplegar-testing"]
    assert [j.name for j in context.failed_jobs] == ["desplegar-testing"]
    failed = context.failed_jobs[0]
    assert failed.log_tail.split("\n") == [f"line {n}" for n in range(295, 300)]
    # The allowed-to-fail job's log is not fetched at all.
    assert not any("/jobs/2/trace" in c.request.url for c in responses.calls)
    assert (context.last_good_pipeline_id, context.last_good_sha) == (190, "old000")
    assert context.commits[0].title == "Change DB user"
    assert context.changed_files == ["apps/api/a.properties"]


@responses.activate
def test_source_without_an_earlier_good_pipeline(client):
    responses.get(f"{PROJECT}/pipelines/5", json={"id": 5, "ref": "main", "sha": "s"})
    responses.get(f"{PROJECT}/pipelines/5/jobs", json=[])
    responses.get(f"{PROJECT}/pipelines", json=[])

    context = GitLabIncidentSource(client).collect("acme/shop", 5)

    assert context.last_good_sha is None and context.commits == []


@responses.activate
def test_publisher_creates_one_issue_then_updates_it(client):
    responses.get(f"{PROJECT}/issues", json=[])
    responses.post(
        f"{PROJECT}/issues",
        json={"iid": 9, "web_url": "https://gitlab.example.com/acme/shop/-/issues/9"},
    )
    url = GitLabIssuePublisher(client).publish("acme/shop", 200, "Incident #200", "report")

    assert url.endswith("/issues/9")
    sent = json.loads(responses.calls[1].request.body)
    assert sent["labels"] == LABEL and sent["description"].endswith(marker(200))

    responses.replace(
        responses.GET,
        f"{PROJECT}/issues",
        json=[
            {"iid": 8, "description": f"other\n{marker(20)}"},
            {"iid": 9, "description": f"old\n{marker(200)}"},
        ],
    )
    responses.put(
        f"{PROJECT}/issues/9",
        json={"iid": 9, "web_url": "https://gitlab.example.com/acme/shop/-/issues/9"},
    )
    url = GitLabIssuePublisher(client).publish("acme/shop", 200, "Incident #200", "new report")

    assert url.endswith("/issues/9")
    assert json.loads(responses.calls[-1].request.body)["description"].startswith("new report")
