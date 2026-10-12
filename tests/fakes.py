"""In-memory port implementations: the whole graph runs in tests with no network."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_langgraph.application.deps import GraphDeps, ReviewConfig
from agent_langgraph.application.prompts import CODE_ARCH_PROMPT, SECURITY_PROMPT
from agent_langgraph.domain.models import (
    FileChange,
    Finding,
    InlineComment,
    LLMResult,
    ReviewItem,
    ReviewTarget,
    Severity,
    TokenUsage,
)

TARGET = ReviewTarget(repo="acme/shop", pr_number=7, head_sha="abc1234def5678")

# New-file lines 1-4: line 1 is context, lines 2-4 are added.
PY_PATCH = '@@ -1,1 +1,4 @@\n import os\n+API_KEY = "hunter2"\n+\n+print(API_KEY)'
PY_FILE = FileChange(path="app/config.py", patch=PY_PATCH, additions=3, deletions=0)
README_FILE = FileChange(
    path="README.md", patch="@@ -1,0 +1,1 @@\n+# Shop", additions=1, deletions=0
)

HIGH_SECRET = ReviewItem(
    file="app/config.py", line=2, message="Hardcoded API key.", severity=Severity.HIGH
)
MEDIUM_BUG = ReviewItem(
    file="app/config.py", line=4, message="Prints a secret to stdout.", severity=Severity.MEDIUM
)


@dataclass
class FakeDiffProvider:
    files: list[FileChange]
    failures_before_success: int = 0
    calls: int = 0

    def get_changed_files(self, target: ReviewTarget) -> list[FileChange]:
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise ConnectionError("transient network failure")
        return list(self.files)


@dataclass
class FakePublisher:
    statuses: list[str] = field(default_factory=list)
    inline: list[list[InlineComment]] = field(default_factory=list)

    def publish_status(self, target: ReviewTarget, body: str) -> None:
        self.statuses.append(body)

    def publish_inline(self, target: ReviewTarget, comments: list[InlineComment]) -> None:
        self.inline.append(comments)


@dataclass
class FakeAnalyzer:
    findings: list[Finding] = field(default_factory=list)
    error: Exception | None = None
    calls: int = 0

    def run(self, files: list[FileChange]) -> list[Finding]:
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.findings)


@dataclass
class FakeLLM:
    """Answers per system prompt; an Exception value is raised instead of returned."""

    security: list[ReviewItem] | Exception = field(default_factory=list)
    code_arch: list[ReviewItem] | Exception = field(default_factory=list)
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def review(self, system_prompt: str, user_prompt: str) -> LLMResult:
        self.prompts.append((system_prompt, user_prompt))
        answer = {SECURITY_PROMPT: self.security, CODE_ARCH_PROMPT: self.code_arch}[system_prompt]
        if isinstance(answer, Exception):
            raise answer
        return LLMResult(items=list(answer), usage=TokenUsage(input_tokens=100, output_tokens=10))


@dataclass
class Harness:
    deps: GraphDeps
    diff: FakeDiffProvider
    publisher: FakePublisher
    analyzer: FakeAnalyzer
    llm: FakeLLM


def make_harness(
    files: list[FileChange] | None = None,
    llm: FakeLLM | None = None,
    analyzer: FakeAnalyzer | None = None,
    config: ReviewConfig | None = None,
    diff: FakeDiffProvider | None = None,
) -> Harness:
    diff = diff or FakeDiffProvider(files if files is not None else [PY_FILE])
    publisher = FakePublisher()
    analyzer = analyzer or FakeAnalyzer()
    llm = llm or FakeLLM()
    deps = GraphDeps(
        diff_provider=diff,
        publisher=publisher,
        static_analyzer=analyzer,
        llm=llm,
        config=config or ReviewConfig(),
    )
    return Harness(deps=deps, diff=diff, publisher=publisher, analyzer=analyzer, llm=llm)
