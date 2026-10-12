"""Static analysis adapter: runs ruff against touched Python files. No LLM.

Only diagnostics on lines the PR added are reported, and only for files that
exist in the working tree (in CI that is the checked-out PR head; locally,
reviewing someone else's repo, there is simply nothing to lint).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from agent_langgraph.domain.diff import added_lines
from agent_langgraph.domain.errors import StaticAnalysisError
from agent_langgraph.domain.models import FileChange, Finding, Severity

AGENT_NAME = "ruff"
# Correctness (pyflakes), security (bandit) and syntax errors rank above style.
# Nothing here is ever HIGH: a linter must not trigger the human gate.
_MEDIUM_CODES = re.compile(r"^(F\d|S\d|E9)")
_TIMEOUT_SECONDS = 60


class RuffStaticAnalyzer:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path.cwd()

    def run(self, files: list[FileChange]) -> list[Finding]:
        added_by_path = {
            (self._root / f.path).resolve(): (f.path, added_lines(f.patch))
            for f in files
            if f.path.endswith(".py") and (self._root / f.path).is_file()
        }
        if not added_by_path:
            return []

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--output-format=json",
                    "--no-fix",
                    "--force-exclude",
                    *(str(p) for p in added_by_path),
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=self._root,
                timeout=_TIMEOUT_SECONDS,
            )
            diagnostics = json.loads(result.stdout or "[]")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            raise StaticAnalysisError(f"ruff could not run: {exc}") from exc
        if result.returncode not in (0, 1):
            raise StaticAnalysisError(
                f"ruff exited with {result.returncode}: {result.stderr[:200]}"
            )

        findings = []
        for diagnostic in diagnostics:
            entry = added_by_path.get(Path(diagnostic["filename"]).resolve())
            line = diagnostic["location"]["row"]
            if entry is None or line not in entry[1]:
                continue
            code = diagnostic.get("code") or "invalid-syntax"
            findings.append(
                Finding(
                    agent=AGENT_NAME,
                    file=entry[0],
                    line=line,
                    message=f"{code}: {diagnostic['message']}",
                    severity=_severity_for(code),
                )
            )
        return findings


def _severity_for(code: str) -> Severity:
    if code == "invalid-syntax" or _MEDIUM_CODES.match(code):
        return Severity.MEDIUM
    return Severity.LOW
