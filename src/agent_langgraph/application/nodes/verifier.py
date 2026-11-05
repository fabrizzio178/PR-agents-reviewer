"""VERIFIER node: a second LLM pass that tries to refute every finding before it is published.

Reviewers are asked to find problems, so they over-report. The verifier gets the
opposite job: argue against each finding using only the diff. A refuted finding
is dropped from the review but listed, with the reason, in a collapsed section,
so a reader can audit the decision. A finding it cannot settle stays, marked as
unverified. Static-analysis findings are deterministic and pass straight through.

If the verifier itself fails, every finding is kept as it was and the summary
says the self-check did not run: a failure never hides a finding.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.application.nodes.supervisor import CODE_ARCH, SECURITY
from agent_langgraph.application.prompts import VERIFIER_PROMPT, render_verification
from agent_langgraph.application.schemas import VerificationSchema
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import DiscardedFinding, Finding, GraphState

VERIFIER = "verifier"
_LLM_AGENTS = {SECURITY, CODE_ARCH}

logger = logging.getLogger(__name__)


def make_verifier(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def verifier(state: GraphState) -> dict[str, Any]:
        findings = state.get("findings", [])
        to_check = [f for f in findings if f.agent in _LLM_AGENTS]
        if not deps.config.verify_findings or not to_check:
            return {"verified_findings": findings, "discarded": []}

        prompt = render_verification(state["files"], to_check)
        try:
            parsed, usage = deps.llm.generate(VERIFIER_PROMPT, prompt, VerificationSchema)
        except LLMError as exc:
            logger.warning("verifier failed: %s", exc)
            return {
                "verified_findings": findings,
                "discarded": [],
                "verification_error": str(exc),
            }

        checks = {c.id: c for c in parsed.checks}
        kept = [f for f in findings if f.agent not in _LLM_AGENTS]
        discarded: list[DiscardedFinding] = []
        for number, finding in enumerate(to_check, start=1):
            check = checks.get(number)
            if check is None:
                kept.append(_unverified(finding, "the self-check returned no verdict for it"))
            elif check.verdict == "refuted":
                discarded.append(DiscardedFinding(finding=finding, reason=check.evidence_against))
            elif check.verdict == "uncertain":
                kept.append(_unverified(finding, check.evidence_against))
            else:
                kept.append(finding)
        return {"verified_findings": kept, "discarded": discarded, "usage": usage}

    return verifier


def _unverified(finding: Finding, note: str) -> Finding:
    return replace(finding, unverified=True, verification_note=note)
