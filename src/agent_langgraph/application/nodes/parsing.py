"""Shared parsing helper for the LLM-backed review agents.

Both the security and code/architecture agents are prompted to reply in the
same 'SEVERITY|file|message' line format so this parser can be reused as-is.
"""

from __future__ import annotations

from agent_langgraph.domain.models import Finding, Severity


def parse_findings(agent_name: str, response: str) -> list[Finding]:
    if response.strip().upper() == "CLEAN":
        return []

    findings: list[Finding] = []
    for line in response.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        severity_raw, file_path, message = parts
        try:
            severity = Severity(severity_raw.strip().lower())
        except ValueError:
            severity = Severity.LOW
        findings.append(
            Finding(
                agent=agent_name,
                file=file_path.strip(),
                message=message.strip(),
                severity=severity,
            )
        )
    return findings
