"""Typed settings resolved from environment variables.

Together with wiring.py this is the only place that reads the environment —
nodes and adapters receive already-resolved values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agent_langgraph.adapters.llm.gemini_client import DEFAULT_MODEL
from agent_langgraph.application.deps import ReviewConfig
from agent_langgraph.domain.models import Severity

GEMINI = "gemini"
OPENAI_COMPATIBLE = "openai-compatible"


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str
    model: str
    base_url: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> LLMSettings:
        provider = (env.get("LLM_PROVIDER") or GEMINI).strip().lower()
        if provider == GEMINI:
            return cls(
                provider=GEMINI,
                api_key=_require(env, "GEMINI_API_KEY"),
                model=env.get("GEMINI_MODEL") or DEFAULT_MODEL,
            )
        if provider == OPENAI_COMPATIBLE:
            return cls(
                provider=OPENAI_COMPATIBLE,
                api_key=_require(env, "LLM_API_KEY"),
                model=_require(env, "LLM_MODEL"),
                base_url=_require(env, "LLM_BASE_URL"),
            )
        raise RuntimeError(
            f"LLM_PROVIDER must be '{GEMINI}' or '{OPENAI_COMPATIBLE}', got {provider!r}"
        )


@dataclass(frozen=True)
class Settings:
    github_token: str
    llm: LLMSettings
    checkpoint_path: str
    review: ReviewConfig

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        defaults = ReviewConfig()
        return cls(
            github_token=_require(env, "GITHUB_TOKEN"),
            llm=LLMSettings.from_env(env),
            checkpoint_path=env.get("REVIEW_CHECKPOINT_PATH") or "agent_langgraph.sqlite",
            review=ReviewConfig(
                max_file_chars=_int(env, "REVIEW_MAX_FILE_CHARS", defaults.max_file_chars),
                max_total_chars=_int(env, "REVIEW_MAX_TOTAL_CHARS", defaults.max_total_chars),
                gate_severity=_severity(env, "REVIEW_GATE_SEVERITY", defaults.gate_severity),
            ),
        )


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise RuntimeError(f"{name} must be positive, got {value}")
    return value


def _severity(env: Mapping[str, str], name: str, default: Severity) -> Severity:
    raw = env.get(name)
    if not raw:
        return default
    try:
        return Severity(raw.strip().lower())
    except ValueError:
        raise RuntimeError(f"{name} must be one of low, medium, high; got {raw!r}") from None
