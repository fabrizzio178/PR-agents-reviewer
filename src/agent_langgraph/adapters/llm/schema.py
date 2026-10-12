"""The structured-output contract every LLM adapter validates against.

Whatever the provider, a reply only becomes findings after it passes this
schema; anything else raises LLMError, so a malformed reply is never read as
"no findings".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ValidationError

from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import ReviewItem, Severity


class FindingSchema(BaseModel):
    severity: Literal["low", "medium", "high"]
    file: str
    line: int | None = None
    message: str


class ReviewSchema(BaseModel):
    findings: list[FindingSchema]


def parse_review(text: str) -> list[ReviewItem]:
    try:
        parsed = ReviewSchema.model_validate_json(text)
    except ValidationError as exc:
        raise LLMError("Model returned output that does not match the schema") from exc
    return [
        ReviewItem(
            file=f.file,
            message=f.message,
            severity=Severity(f.severity),
            line=f.line if f.line and f.line > 0 else None,
        )
        for f in parsed.findings
    ]
