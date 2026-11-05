"""Markdown report published as an issue: conclusion first, evidence in collapsed sections."""

from __future__ import annotations

from agent_langgraph.application.rendering import sanitize
from agent_langgraph.incidents.models import IncidentState
from agent_langgraph.incidents.schemas import HypothesesSchema, RefutationSchema

TITLE = "### Incident Agent"
_VERDICT_ICON = {"supported": "✅", "refuted": "❌", "inconclusive": "❔"}
_CONFIDENCE = {"low": "low", "medium": "medium", "high": "high"}


def issue_title(state: IncidentState) -> str:
    context = state["context"]
    failed = ", ".join(j.name for j in context.failed_jobs) or "unknown job"
    return f"Incident: pipeline #{context.pipeline_id} failed in {failed}"


def render_report(state: IncidentState) -> str:
    context = state["context"]
    lines = [TITLE, ""]
    failed = ", ".join(f"`{j.name}`" for j in context.failed_jobs) or "_none found_"
    lines.append(
        f"Pipeline [#{context.pipeline_id}]({context.pipeline_url}) on `{context.ref}` "
        f"(commit `{context.sha[:8]}`) failed in {failed}."
    )
    lines += ["", "> The agent only read logs and history. Nothing was changed or executed."]

    hypotheses = state.get("hypotheses")
    refutation = state.get("refutation")
    if hypotheses and refutation:
        lines += _render_conclusion(hypotheses, refutation)
        lines += _render_hypotheses(hypotheses, refutation)
    elif hypotheses:
        lines += ["", "#### Hypotheses (not checked)", ""]
        lines += [f"- **H{h.id}** {sanitize(h.title)}" for h in hypotheses.hypotheses]

    plan = state.get("plan")
    if plan:
        lines += ["", "#### Mitigation plan (recommendation)", "", sanitize(plan.summary)]
        lines += _bullets("Check before acting", plan.checks_before)
        lines += ["", "**Steps**", ""]
        for number, step in enumerate(plan.steps, start=1):
            command = f" — `{_code(step.command)}`" if step.command else ""
            lines.append(f"{number}. {sanitize(step.action)}{command}")
        lines += _bullets("Success criteria", plan.success_criteria)
        lines += _bullets("If it gets worse, roll back", plan.rollback)

    lines += _render_evidence(state)

    errors = state.get("errors", [])
    warning = state.get("map_warning")
    if errors or warning:
        lines += ["", "#### ⚠️ Incomplete investigation", ""]
        if warning:
            lines.append(f"- {sanitize(warning)}")
        lines += [f"- {sanitize(e)}" for e in errors]

    usage = state.get("usage")
    tokens = (
        f" · tokens: {usage.input_tokens} in / {usage.output_tokens} out"
        if usage and (usage.input_tokens or usage.output_tokens)
        else ""
    )
    lines += ["", f"<sub>Investigated pipeline #{context.pipeline_id}{tokens}</sub>"]
    return "\n".join(lines)


def _render_conclusion(hypotheses: HypothesesSchema, refutation: RefutationSchema) -> list[str]:
    by_id = {h.id: h for h in hypotheses.hypotheses}
    root = by_id.get(refutation.root_cause_id) if refutation.root_cause_id is not None else None
    lines = ["", "#### Root cause", ""]
    if root:
        lines.append(
            f"**H{root.id}. {sanitize(root.title)}** "
            f"(confidence: {_CONFIDENCE[refutation.confidence]})"
        )
        lines += ["", sanitize(root.mechanism)]
    else:
        lines.append("**Not determined.** No hypothesis survived the evidence; see the plan.")
    lines += ["", sanitize(refutation.summary)]
    return lines


def _render_hypotheses(hypotheses: HypothesesSchema, refutation: RefutationSchema) -> list[str]:
    checks = {c.id: c for c in refutation.checks}
    lines = ["", "#### Hypotheses and how they were checked", ""]
    for h in hypotheses.hypotheses:
        check = checks.get(h.id)
        verdict = check.verdict if check else "inconclusive"
        services = f" · {', '.join(h.services)}" if h.services else ""
        lines.append(
            f"- {_VERDICT_ICON[verdict]} **H{h.id}. {sanitize(h.title)}** "
            f"_({h.category}{services})_"
        )
        for evidence in h.evidence_for:
            lines.append(f"  - for: {sanitize(evidence)}")
        if check:
            for evidence in check.evidence_against:
                lines.append(f"  - against: {sanitize(evidence)}")
            lines.append(f"  - {verdict}: {sanitize(check.reasoning)}")
    return lines


def _render_evidence(state: IncidentState) -> list[str]:
    context = state["context"]
    lines = ["", "<details><summary>Timeline</summary>", ""]
    lines += [f"- `{e.at}` **{e.kind}** {sanitize(e.text)}" for e in state.get("timeline", [])]
    lines += ["", "</details>"]

    lines += ["", "<details><summary>Changes since the last good pipeline</summary>", ""]
    if context.last_good_sha:
        lines.append(
            f"From `{context.last_good_sha[:8]}` (pipeline #{context.last_good_pipeline_id}) "
            f"to `{context.sha[:8]}`."
        )
    else:
        lines.append("No earlier successful pipeline on this ref.")
    changed = state.get("changed_services") or []
    lines.append(f"Services with changed files: {', '.join(changed) or 'none'}.")
    lines += [
        f"- `{c.sha[:8]}` {sanitize(c.title)} — {sanitize(c.author)}" for c in context.commits
    ]
    lines += ["", "</details>"]
    return lines


def _bullets(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return ["", f"**{title}**", ""] + [f"- {sanitize(item)}" for item in items]


def _code(command: str) -> str:
    return sanitize(command).replace("`", "'")
