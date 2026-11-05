"""GitLab IncidentPublisher: one issue per failed pipeline, updated if the job reruns."""

from __future__ import annotations

from agent_langgraph.adapters.gitlab.rest_client import GitLabRestClient, project_path

LABEL = "incident-agent"


def marker(pipeline_id: int) -> str:
    return f"<!-- incident-agent:pipeline:{pipeline_id} -->"


class GitLabIssuePublisher:
    def __init__(self, client: GitLabRestClient) -> None:
        self._client = client

    def publish(self, project: str, pipeline_id: int, title: str, body: str) -> str:
        base = project_path(project)
        tag = marker(pipeline_id)
        description = f"{body}\n\n{tag}"
        existing = self._client.get(
            f"{base}/issues",
            params={"labels": LABEL, "state": "opened", "search": f"#{pipeline_id}", "in": "title"},
        )
        for issue in existing:
            if tag in (issue.get("description") or ""):
                updated = self._client.put(
                    f"{base}/issues/{issue['iid']}", {"title": title, "description": description}
                )
                return str(updated["web_url"])
        created = self._client.post(
            f"{base}/issues", {"title": title, "description": description, "labels": LABEL}
        )
        return str(created["web_url"])
