"""Markdown rendering of everything the agent publishes on a pull request.

Finding messages originate from an LLM that read untrusted code, so they are
sanitized before they reach GitHub: one line, bounded length, no mentions.
"""

from __future__ import annotations

from agent_langgraph.domain.models import (
    DiscardedFinding,
    Finding,
    GraphState,
    ReviewVerdict,
    Severity,
)

TITLE = "### PR Review Agent"
_MAX_MESSAGE_CHARS = 500
_SEVERITY_LABEL = {
    Severity.HIGH: "🔴 High",
    Severity.MEDIUM: "🟠 Medium",
    Severity.LOW: "🟡 Low",
}


def sanitize(text: str) -> str:
    """Make model-written text safe to publish: no pings, no layout breakage."""
    single_line = " ".join(text.split())
    if len(single_line) > _MAX_MESSAGE_CHARS:
        single_line = single_line[: _MAX_MESSAGE_CHARS - 1] + "…"
    # A zero-width space after '@' stops GitHub from resolving a mention.
    return single_line.replace("@", "@​").replace("<!--", "&lt;!--")


def render_counts(verdict: ReviewVerdict) -> str:
    counts = []
    for severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        n = sum(1 for f in verdict.findings if f.severity == severity)
        if n:
            counts.append(f"{n} {severity.value}")
    return ", ".join(counts) or "no findings"


def render_inline(finding: Finding) -> str:
    return (
        f"**{_SEVERITY_LABEL[finding.severity]}** · `{finding.agent}`"
        f"{' · unverified' if finding.unverified else ''}\n\n"
        f"{sanitize(finding.message)}{_unverified_note(finding)}"
    )


def render_review(state: GraphState) -> str:
    verdict = state["verdict"]
    assert verdict is not None
    errors = state.get("agent_errors", [])
    lines = [TITLE, ""]

    if verdict.findings:
        lines.append(f"Found {render_counts(verdict)}.")
    elif errors:
        lines.append("No findings were produced, but the review did not complete (see below).")
    else:
        lines.append("✅ No issues found.")

    for severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        group = [f for f in verdict.findings if f.severity == severity]
        if not group:
            continue
        lines += ["", f"#### {_SEVERITY_LABEL[severity]}", ""]
        lines += [_render_finding(f) for f in group]

    discarded = state.get("discarded") or []
    if discarded:
        lines += [
            "",
            f"<details><summary>🧪 Discarded by the self-check ({len(discarded)})</summary>",
            "",
        ]
        lines += [_render_discarded(d) for d in discarded]
        lines += ["", "</details>"]

    verification_error = state.get("verification_error")
    if verification_error:
        lines += [
            "",
            f"⚠️ The self-check did not run ({sanitize(verification_error)}), so these "
            "findings were not double-checked.",
        ]

    if errors:
        lines += ["", "#### ⚠️ Incomplete review", ""]
        lines.append("These reviewers failed, so their part of the diff was **not** checked:")
        lines += [f"- {sanitize(e)}" for e in errors]

    config_warning = state.get("config_warning")
    if config_warning:
        lines += [
            "",
            f"⚠️ `.pr-review.yml` is invalid and was ignored ({sanitize(config_warning)}). "
            "Defaults were used.",
        ]

    truncated = state.get("truncated_files", [])
    if truncated:
        lines += ["", "#### ✂️ Not fully reviewed (diff too large)", ""]
        lines += [f"- `{path}`" for path in truncated]

    lines += ["", _render_footer(state)]
    return "\n".join(lines)


def render_pending(verdict: ReviewVerdict) -> str:
    return "\n".join(
        [
            TITLE,
            "",
            f"⏸️ Review complete ({render_counts(verdict)}), including "
            f"**{verdict.max_severity.value}**-severity findings.",
            "",
            "Details are withheld until a maintainer approves publishing them.",
        ]
    )


def render_withheld(verdict: ReviewVerdict) -> str:
    return "\n".join(
        [
            TITLE,
            "",
            f"🚫 A maintainer reviewed the findings ({render_counts(verdict)}) and "
            "chose not to publish them.",
        ]
    )


def _location(finding: Finding) -> str:
    return f"{finding.file}:{finding.line}" if finding.line else finding.file


def _render_finding(finding: Finding) -> str:
    return (
        f"- `{_location(finding)}` — {sanitize(finding.message)} _({finding.agent})_"
        f"{_unverified_note(finding)}"
    )


def _unverified_note(finding: Finding) -> str:
    if not finding.unverified:
        return ""
    note = f": {sanitize(finding.verification_note)}" if finding.verification_note else ""
    return f" ⚠️ _unverified{note}_"


def _render_discarded(discarded: DiscardedFinding) -> str:
    finding = discarded.finding
    return (
        f"- `{_location(finding)}` — {sanitize(finding.message)} _({finding.agent})_ "
        f"→ **why discarded:** {sanitize(discarded.reason)}"
    )


def _render_footer(state: GraphState) -> str:
    target = state["target"]
    parts = [f"Reviewed `{target.head_sha[:7]}`"]
    agents = state.get("active_agents", [])
    parts.append(f"agents: {', '.join(agents) if agents else 'none (no reviewable changes)'}")
    usage = state.get("usage")
    if usage and (usage.input_tokens or usage.output_tokens):
        parts.append(f"tokens: {usage.input_tokens} in / {usage.output_tokens} out")
    return "<sub>" + " · ".join(parts) + "</sub>"
