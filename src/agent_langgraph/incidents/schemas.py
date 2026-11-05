"""Structured-output contracts for the three LLM steps of an investigation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "code_change",
    "configuration",
    "dependency",
    "infrastructure",
    "pipeline_or_test",
    "external",
    "unknown",
]


class Hypothesis(BaseModel):
    id: int
    title: str = Field(description="One short sentence naming the suspected cause.")
    category: Category
    services: list[str] = Field(description="Affected services, by name from the map.")
    mechanism: str = Field(description="How this cause would produce the observed failure.")
    evidence_for: list[str] = Field(description="Concrete facts from the evidence, quoted.")


class HypothesesSchema(BaseModel):
    hypotheses: list[Hypothesis] = Field(max_length=5)


class HypothesisCheck(BaseModel):
    id: int
    verdict: Literal["supported", "refuted", "inconclusive"]
    evidence_against: list[str] = Field(description="Facts that contradict it, quoted.")
    reasoning: str = Field(description="One or two sentences weighing both sides.")


class RefutationSchema(BaseModel):
    checks: list[HypothesisCheck]
    root_cause_id: int | None = Field(
        description="Id of the supported hypothesis that best explains the failure, or null."
    )
    confidence: Literal["low", "medium", "high"]
    summary: str = Field(description="Two sentences: what failed and why.")


class PlanStep(BaseModel):
    action: str
    command: str | None = Field(
        default=None, description="A command a human could run, or null if none applies."
    )


class MitigationPlan(BaseModel):
    summary: str
    checks_before: list[str] = Field(description="What to confirm before acting.")
    steps: list[PlanStep]
    success_criteria: list[str]
    rollback: list[str] = Field(description="How to undo the steps if they make it worse.")
