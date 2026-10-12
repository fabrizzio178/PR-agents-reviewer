"""Offline evals for the LLM review agents: dataset loading and scoring.

A case is a small diff plus the findings a competent reviewer must report.
An expectation is met when some finding names the same file, is at least as
severe as required, and mentions one of the expected keywords.

Metrics per agent:
  recall     expectations met / expectations
  precision  expectations met / (expectations met + findings on clean cases)
Extra findings on a non-clean case are not counted as false positives: a
reviewer may legitimately notice more than the one issue the case plants.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent_langgraph.application.nodes.supervisor import CODE_ARCH, SECURITY
from agent_langgraph.application.prompts import CODE_ARCH_PROMPT, SECURITY_PROMPT, render_diff
from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import FileChange, ReviewItem, Severity
from agent_langgraph.domain.ports import LLMClient

PROMPTS = {SECURITY: SECURITY_PROMPT, CODE_ARCH: CODE_ARCH_PROMPT}


@dataclass(frozen=True)
class Expectation:
    file: str
    min_severity: Severity
    keywords: tuple[str, ...]

    def is_met_by(self, item: ReviewItem) -> bool:
        message = item.message.lower()
        return (
            item.file == self.file
            and item.severity.rank >= self.min_severity.rank
            and any(keyword in message for keyword in self.keywords)
        )


@dataclass(frozen=True)
class EvalCase:
    id: str
    agent: str
    files: list[FileChange]
    expected: list[Expectation]


@dataclass
class AgentScore:
    cases: int = 0
    met: int = 0
    missed: int = 0
    false_positives: int = 0
    high_on_clean: int = 0
    errors: int = 0
    failed_cases: list[str] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        total = self.met + self.missed
        return self.met / total if total else 1.0

    @property
    def precision(self) -> float:
        total = self.met + self.false_positives
        return self.met / total if total else 1.0


def load_cases(path: Path) -> list[EvalCase]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        cases.append(
            EvalCase(
                id=raw["id"],
                agent=raw["agent"],
                files=[
                    FileChange(path=f["path"], patch=f["patch"], additions=0, deletions=0)
                    for f in raw["files"]
                ],
                expected=[
                    Expectation(
                        file=e["file"],
                        min_severity=Severity(e["min_severity"]),
                        keywords=tuple(k.lower() for k in e["keywords"]),
                    )
                    for e in raw["expected"]
                ],
            )
        )
    return cases


def score_case(case: EvalCase, items: list[ReviewItem], score: AgentScore) -> None:
    score.cases += 1
    if not case.expected:
        score.false_positives += len(items)
        score.high_on_clean += sum(1 for i in items if i.severity == Severity.HIGH)
        if items:
            score.failed_cases.append(case.id)
        return

    missed = sum(1 for e in case.expected if not any(e.is_met_by(i) for i in items))
    score.met += len(case.expected) - missed
    score.missed += missed
    if missed:
        score.failed_cases.append(case.id)


def run_evals(
    cases: list[EvalCase],
    llm: LLMClient,
    delay_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, AgentScore]:
    scores: dict[str, AgentScore] = {}
    for index, case in enumerate(cases):
        score = scores.setdefault(case.agent, AgentScore())
        if index and delay_seconds:
            sleep(delay_seconds)
        try:
            result = llm.review(PROMPTS[case.agent], render_diff(case.files))
        except LLMError as exc:
            # An errored case counts as fully missed: a failure is never a pass.
            score.error_messages.append(f"{case.id}: {str(exc.__cause__ or exc)[:160]}")
            score.cases += 1
            score.errors += 1
            score.missed += len(case.expected)
            score.failed_cases.append(case.id)
            continue
        score_case(case, result.items, score)
    return scores
