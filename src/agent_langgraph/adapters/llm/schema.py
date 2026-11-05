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


def parse_as[M: BaseModel](schema: type[M], text: str) -> M:
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise LLMError("Model returned output that does not match the schema") from exc


def to_review_items(parsed: ReviewSchema) -> list[ReviewItem]:
    return [
        ReviewItem(
            file=f.file,
            message=f.message,
            severity=Severity(f.severity),
            line=f.line if f.line and f.line > 0 else None,
        )
        for f in parsed.findings
    ]


def parse_review(text: str) -> list[ReviewItem]:
    return to_review_items(parse_as(ReviewSchema, text))
