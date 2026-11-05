"""Incident mode: the pure parts (redaction, map, timeline) and the whole graph over fakes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_langgraph.domain.errors import ConfigError, LLMError
from agent_langgraph.domain.models import TokenUsage
from agent_langgraph.incidents.graph import IncidentDeps, build_incident_graph, build_timeline
from agent_langgraph.incidents.incident_map import load_incident_map, parse_incident_map
from agent_langgraph.incidents.models import (
    CommitInfo,
    IncidentContext,
    IncidentMap,
    JobRun,
    ServiceSpec,
)
from agent_langgraph.incidents.redaction import redact
from agent_langgraph.incidents.schemas import (
    HypothesesSchema,
    Hypothesis,
    HypothesisCheck,
    MitigationPlan,
    PlanStep,
    RefutationSchema,
)

MAP = IncidentMap(
    services=[
        ServiceSpec(name="web", paths=["apps/web/"], depends_on=["api"]),
        ServiceSpec(name="api", paths=["apps/api/"], notes="Spring Boot"),
    ],
    runbook=["desplegar.sh restores the previous version on failure."],
    language="Spanish",
)

FAILED_LOG = (
    "Pulling api...\n"
    "api exited with code 1\n"
    "Caused by: java.sql.SQLException: Access denied for user 'app' (password=hunter2)\n"
    "ERROR: el despliegue fallo"
)

CONTEXT = IncidentContext(
    project="acme/shop",
    pipeline_id=200,
    pipeline_url="https://gitlab.example.com/acme/shop/-/pipelines/200",
    ref="main",
    sha="bbbbbbbbbbbbbbbb",
    created_at="2026-11-05T10:00:00Z",
    jobs=[
        JobRun(
            id=1,
            name="build",
            stage="build",
            status="success",
            allow_failure=False,
            web_url="",
            started_at="2026-11-05T10:00:10Z",
            finished_at="2026-11-05T10:01:00Z",
        ),
        JobRun(
            id=2,
            name="sast",
            stage="validacion",
            status="failed",
            allow_failure=True,
            web_url="",
            started_at="2026-11-05T10:00:05Z",
            finished_at="2026-11-05T10:00:30Z",
        ),
        JobRun(
            id=3,
            name="desplegar-testing",
            stage="testing",
            status="failed",
            allow_failure=False,
            web_url="",
            started_at="2026-11-05T10:02:00Z",
            finished_at="2026-11-05T10:03:00Z",
            log_tail=FAILED_LOG,
        ),
    ],
    last_good_pipeline_id=190,
    last_good_sha="aaaaaaaaaaaaaaaa",
    commits=[
        CommitInfo(
            sha="bbbbbbbbbbbbbbbb",
            title="Change DB user of the API",
            author="dev",
            created_at="2026-11-05T09:58:00Z",
        )
    ],
    changed_files=["apps/api/application.properties"],
)


def hypotheses() -> HypothesesSchema:
    return HypothesesSchema(
        hypotheses=[
            Hypothesis(
                id=1,
                title="Credenciales de la base cambiadas",
                category="configuration",
                services=["api"],
                mechanism="La API no puede conectarse a la base.",
                evidence_for=["Access denied for user 'app'"],
            ),
            Hypothesis(
                id=2,
                title="Falta memoria en la VM",
                category="infrastructure",
                services=["api"],
                mechanism="El contenedor muere por OOM.",
                evidence_for=["api exited with code 1"],
            ),
        ]
    )


def refutation(root: int | None = 1, verdict_1: str = "supported") -> RefutationSchema:
    return RefutationSchema(
        checks=[
            HypothesisCheck(
                id=1, verdict=verdict_1, evidence_against=[], reasoning="El log lo muestra."
            ),
            HypothesisCheck(
                id=2,
                verdict="refuted",
                evidence_against=["No hay OOMKilled en el log"],
                reasoning="El error es de acceso, no de memoria.",
            ),
        ],
        root_cause_id=root,
        confidence="high",
        summary="El deploy falló porque la API no pudo autenticarse en la base.",
    )


PLAN = MitigationPlan(
    summary="Volver al usuario anterior.",
    checks_before=["Confirmar que la versión anterior sigue corriendo."],
    steps=[PlanStep(action="Revertir el commit bbbbbbbb", command="git revert bbbbbbbb")],
    success_criteria=["desplegar-testing en verde"],
    rollback=["Revertir el revert."],
)


@dataclass
class FakeSource:
    context: IncidentContext = CONTEXT

    def collect(self, project: str, pipeline_id: int) -> IncidentContext:
        assert (project, pipeline_id) == ("acme/shop", 200)
        return self.context


@dataclass
class FakeLLM:
    """Answers by schema; an Exception value is raised instead of returned."""

    answers: dict[type, Any] = field(default_factory=dict)
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def review(self, system_prompt: str, user_prompt: str) -> Any:
        raise AssertionError("incident mode never calls review()")

    def generate(self, system_prompt: str, user_prompt: str, schema: type[Any]) -> Any:
        self.prompts.append((system_prompt, user_prompt))
        answer = self.answers[schema]
        if isinstance(answer, Exception):
            raise answer
        return answer, TokenUsage(input_tokens=100, output_tokens=10)


@dataclass
class FakePublisher:
    published: list[tuple[str, str]] = field(default_factory=list)

    def publish(self, project: str, pipeline_id: int, title: str, body: str) -> str:
        self.published.append((title, body))
        return "https://gitlab.example.com/acme/shop/-/issues/1"


def default_llm() -> FakeLLM:
    return FakeLLM(
        answers={
            HypothesesSchema: hypotheses(),
            RefutationSchema: refutation(),
            MitigationPlan: PLAN,
        }
    )


def investigate(llm: FakeLLM, source: FakeSource | None = None, publish: bool = True) -> Any:
    publisher = FakePublisher() if publish else None
    deps = IncidentDeps(source=source or FakeSource(), llm=llm, publisher=publisher)
    result = build_incident_graph(deps).invoke(
        {"project": "acme/shop", "pipeline_id": 200, "incident_map": MAP}
    )
    return result, publisher


# --- pure parts --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "AKIAABCDEFGHIJKLMNOP",
        "glpat-abcdefghijklmnopqrstuvwx",
        "AIzaSyA1234567890abcdefghijklmnopqrstuv",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.abcdefghijklmnop",
        "password=hunter2",
        "MYSQL_ROOT_PASSWORD: 's3cr3t value'",
        "Authorization: Bearer abcdef1234567890",
        "https://deployer:hunter2@registry.example.com/v2/",
    ],
)
def test_redact_hides_common_secret_shapes(secret):
    redacted = redact(f"before {secret} after")
    assert "[REDACTED]" in redacted
    assert "hunter2" not in redacted and "s3cr3t" not in redacted
    assert redacted.startswith("before ")


def test_redact_keeps_ordinary_log_lines():
    line = "api exited with code 1; tag 1b733cd39c54; port 6767"
    assert redact(line) == line


def test_parse_incident_map_and_services_touching():
    incident_map = parse_incident_map(
        "language: Spanish\n"
        "services:\n"
        "  web: {paths: [apps/web/], depends_on: [api]}\n"
        "  api: {paths: [apps/api/], notes: Spring Boot}\n"
        "runbook: [Rollback is automatic.]\n"
    )
    assert [s.name for s in incident_map.services] == ["web", "api"]
    assert incident_map.language == "Spanish"
    assert incident_map.services_touching(["apps/api/pom.xml", "README.md"]) == ["api"]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("services: [web]", "services"),
        ("services:\n  web: {depends_on: [db]}\n", "unknown services"),
        ("services:\n  web: {colour: blue}\n", "colour"),
        ("- just a list", "mapping"),
    ],
)
def test_parse_incident_map_rejects_bad_files(text, error):
    with pytest.raises(ConfigError, match=error):
        parse_incident_map(text)


def test_missing_or_invalid_map_degrades_to_a_warning(tmp_path):
    incident_map, warning = load_incident_map(tmp_path / ".incident.yml")
    assert incident_map == IncidentMap() and warning and "not found" in warning

    bad = tmp_path / "bad.yml"
    bad.write_text("services: [web]", encoding="utf-8")
    incident_map, warning = load_incident_map(bad)
    assert incident_map == IncidentMap() and warning and "without a service map" in warning


def test_timeline_is_chronological_and_flags_allowed_failures():
    texts = [e.text for e in build_timeline(CONTEXT)]
    assert texts[0] == "pipeline #190 passed at aaaaaaaa"
    assert texts[1] == "bbbbbbbb Change DB user of the API"
    assert texts.index("sast failed (allowed to fail)") < texts.index("build success")
    assert texts[-1] == "desplegar-testing failed"


# --- graph --------------------------------------------------------------------------------


def test_full_investigation_publishes_root_cause_and_plan():
    llm = default_llm()
    result, publisher = investigate(llm)

    [(title, body)] = publisher.published
    assert title == "Incident: pipeline #200 failed in desplegar-testing"
    assert "**H1. Credenciales de la base cambiadas** (confidence: high)" in body
    assert "❌ **H2. Falta memoria en la VM**" in body
    assert "against: No hay OOMKilled en el log" in body
    assert "1. Revertir el commit bbbbbbbb — `git revert bbbbbbbb`" in body
    assert "Nothing was changed or executed" in body
    assert result["changed_services"] == ["api"]
    assert result["issue_url"].endswith("/issues/1")
    assert "tokens: 300 in / 30 out" in body


def test_logs_are_redacted_and_marked_untrusted_before_the_model_sees_them():
    llm = default_llm()
    investigate(llm)

    system, user = llm.prompts[0]
    assert "hunter2" not in user and "[REDACTED]" in user
    assert "<untrusted>" in user and "<service_map>" in user and "Spanish" in system
    # Only blocking failures carry logs; the allowed-to-fail scanner does not.
    assert '<job name="desplegar-testing"' in user and '<job name="sast"' not in user


def test_root_cause_must_be_a_supported_hypothesis():
    llm = default_llm()
    llm.answers[RefutationSchema] = refutation(root=1, verdict_1="inconclusive")
    result, publisher = investigate(llm)

    assert result["refutation"].root_cause_id is None
    assert result["refutation"].confidence == "low"
    assert "**Not determined.**" in publisher.published[0][1]


def test_failed_step_still_publishes_the_evidence():
    llm = default_llm()
    llm.answers[RefutationSchema] = LLMError("Gemini request failed: 429 RESOURCE_EXHAUSTED")
    result, publisher = investigate(llm)

    body = publisher.published[0][1]
    assert "Hypotheses (not checked)" in body
    assert "refute: Gemini request failed: 429" in body
    assert "Mitigation plan" not in body
    assert "<summary>Timeline</summary>" in body
    assert len(llm.prompts) == 2


def test_pipeline_without_blocking_failures_calls_no_model():
    jobs = [j for j in CONTEXT.jobs if j.name != "desplegar-testing"]
    source = FakeSource(context=IncidentContext(**{**CONTEXT.__dict__, "jobs": jobs}))
    llm = default_llm()
    _, publisher = investigate(llm, source=source)

    assert llm.prompts == []
    assert "no failed job found" in publisher.published[0][1]


def test_dry_run_publishes_nothing():
    result, publisher = investigate(default_llm(), publish=False)
    assert publisher is None
    assert result["issue_url"] is None
    assert "### Incident Agent" in result["report"]
