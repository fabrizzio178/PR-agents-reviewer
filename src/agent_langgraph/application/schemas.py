"""Structured-output contracts for the LLM steps that are not plain reviews."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FindingCheck(BaseModel):
    id: int
    verdict: Literal["confirmed", "refuted", "uncertain"]
    evidence_for: str = Field(description="What in the diff supports the finding.")
    evidence_against: str = Field(description="The strongest evidence that it is wrong.")


class VerificationSchema(BaseModel):
    checks: list[FindingCheck]
