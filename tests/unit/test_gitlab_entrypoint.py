"""GitLab CI entrypoint, platform settings and wiring."""

from __future__ import annotations

import pytest

from agent_langgraph.adapters.github.rest_review_publisher import GitHubRestReviewPublisher
from agent_langgraph.adapters.gitlab.rest_review_publisher import GitLabRestReviewPublisher
from agent_langgraph.application.nodes.supervisor import SECURITY, supervisor
from agent_langgraph.domain.diff import line_positions
from agent_langgraph.domain.models import FileChange, RepoConfig, ReviewTarget
from agent_langgraph.entrypoints import gitlab_ci_entrypoint as entry
from agent_langgraph.entrypoints.runner import RunOutcome
from agent_langgraph.entrypoints.settings import Settings
from agent_langgraph.entrypoints.wiring import build_deps

CI_ENV = {
    "GITLAB_TOKEN": "glpat",
    "CI_API_V4_URL": "https://labsys.example/gitlab/api/v4",
    "GEMINI_API_KEY": "k",
    "CI_PROJECT_PATH": "devops/tps-2026/grupo-03/tp2",
    "CI_MERGE_REQUEST_IID": "12",
    "CI_COMMIT_SHA": "0123456789abcdef",
    "CI_PIPELINE_ID": "4567",
}


def test_gitlab_platform_takes_the_api_url_from_ci():
    settings = Settings.from_env(CI_ENV, default_platform="gitlab")
    assert settings.platform.name == "gitlab"
    assert settings.platform.api_url == "https://labsys.example/gitlab/api/v4"
    assert isinstance(build_deps(settings).publisher, GitLabRestReviewPublisher)


def test_explicit_api_url_wins_over_ci():
    env = CI_ENV | {"GITLAB_API_URL": "https://other/api/v4"}
    assert Settings.from_env(env, default_platform="gitlab").platform.api_url == (
        "https://other/api/v4"
    )


def test_github_stays_the_default_platform():
    settings = Settings.from_env({"GITHUB_TOKEN": "t", "GEMINI_API_KEY": "k"})
    assert settings.platform.name == "github"
    assert isinstance(build_deps(settings).publisher, GitHubRestReviewPublisher)


@pytest.mark.parametrize(
    ("env", "missing"),
    [
        ({"GEMINI_API_KEY": "k", "CI_API_V4_URL": "u"}, "GITLAB_TOKEN"),
        ({"GEMINI_API_KEY": "k", "GITLAB_TOKEN": "t"}, "GITLAB_API_URL"),
        ({"GEMINI_API_KEY": "k", "REVIEW_PLATFORM": "bitbucket"}, "REVIEW_PLATFORM"),
    ],
)
def test_gitlab_settings_fail_loudly(env, missing):
    with pytest.raises(RuntimeError, match=missing):
        Settings.from_env(env, default_platform="gitlab")


def test_target_and_thread_come_from_the_ci_variables():
    target = entry.target_from_ci(CI_ENV)
    assert target == ReviewTarget(
        repo="devops/tps-2026/grupo-03/tp2", pr_number=12, head_sha="0123456789abcdef"
    )
    assert entry.thread_id_for(target, CI_ENV) == "mr12-01234567-4567"


def test_target_requires_a_merge_request_pipeline():
    env = {k: v for k, v in CI_ENV.items() if k != "CI_MERGE_REQUEST_IID"}
    with pytest.raises(RuntimeError, match="merge request"):
        entry.target_from_ci(env)


def test_job_results_write_dotenv_and_report(tmp_path):
    dotenv, report = tmp_path / "review.env", tmp_path / "review.md"
    outcome = RunOutcome(thread_id="mr12-01234567-4567", paused=True, posted=False, body="X")

    entry.write_job_results(outcome, dotenv, report)

    assert dotenv.read_text() == "REVIEW_PAUSED=true\nREVIEW_THREAD=mr12-01234567-4567\n"
    assert "Waiting for approval" in report.read_text()


def test_job_results_reject_an_unsafe_thread_id(tmp_path):
    outcome = RunOutcome(thread_id="a\nEVIL=1", paused=False, posted=True, body="")
    with pytest.raises(RuntimeError, match="unsafe"):
        entry.write_job_results(outcome, tmp_path / "e", tmp_path / "r")


def test_resume_without_a_paused_review_is_a_no_op(monkeypatch, tmp_path, capsys):
    for key, value in CI_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("REVIEW_CHECKPOINT_PATH", str(tmp_path / "c.sqlite"))
    monkeypatch.delenv("REVIEW_THREAD", raising=False)

    assert entry.main(["resume"]) == 0
    assert entry.main(["resume", "--thread", "mr1-deadbeef-1"]) == 0
    assert capsys.readouterr().out.count("No review is waiting") == 2


def test_line_positions_map_context_lines_to_their_old_numbers():
    patch = "@@ -10,3 +10,3 @@\n same\n-old\n+new\n tail\n\\ No newline at end of file"
    assert line_positions(patch) == {10: 10, 11: None, 12: 12}


def test_stack_config_files_reach_the_security_agent():
    for path in ("web/nginx/nginx.conf", "src/main/resources/application.properties", "a.csproj"):
        state = {"files": [FileChange(path=path, patch="", additions=0, deletions=0)]}
        state["repo_config"] = RepoConfig()
        assert SECURITY in supervisor(state)["active_agents"], path
