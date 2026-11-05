"""`.pr-review.yml` parsing, shared by every code-hosting adapter (GitHub, GitLab).

Each platform only decides where to read the file from (always the base or
target branch, never the PR head); turning its text into a RepoConfig is the
same everywhere.
"""

from __future__ import annotations

import base64
import binascii
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_langgraph.domain.errors import ConfigError
from agent_langgraph.domain.models import RepoConfig, Severity

CONFIG_PATH = ".pr-review.yml"
ReviewerName = Literal["static_analysis", "security", "code_arch"]


class _ReviewersSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    static_analysis: bool = True
    security: bool = True
    code_arch: bool = True


class _ConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewers: _ReviewersSchema = Field(default_factory=_ReviewersSchema)
    ignore: list[str] = Field(default_factory=list, max_length=100)
    rules: list[str] = Field(default_factory=list, max_length=20)
    gate_severity: Literal["low", "medium", "high"] | None = None


_MAX_RULE_CHARS = 300


def parse_config(text: str) -> RepoConfig:
    try:
        raw = yaml.safe_load(text) or {}
        parsed = _ConfigSchema.model_validate(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML ({type(exc).__name__})") from exc
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "top level"
        raise ConfigError(f"{location}: {first['msg']}") from exc

    too_long = [r for r in parsed.rules if len(r) > _MAX_RULE_CHARS]
    if too_long:
        raise ConfigError(f"rules: each rule must be at most {_MAX_RULE_CHARS} characters")

    reviewers = parsed.reviewers.model_dump()
    return RepoConfig(
        disabled_reviewers=[name for name, enabled in reviewers.items() if not enabled],
        ignore=parsed.ignore,
        rules=[" ".join(rule.split()) for rule in parsed.rules],
        gate_severity=Severity(parsed.gate_severity) if parsed.gate_severity else None,
    )


def decode_base64_entry(entry: object) -> str:
    """Decode a file entry as both GitHub and GitLab return it: base64 `content`."""
    if not isinstance(entry, dict) or entry.get("encoding") != "base64":
        raise ConfigError(f"{CONFIG_PATH} is not a regular file")
    try:
        return base64.b64decode(entry["content"]).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, KeyError) as exc:
        raise ConfigError(f"{CONFIG_PATH} could not be decoded") from exc
