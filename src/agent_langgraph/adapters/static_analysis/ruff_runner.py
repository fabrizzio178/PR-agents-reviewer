"""Static analysis adapter: runs ruff against touched Python files. No LLM."""

from __future__ import annotations

import subprocess

from agent_langgraph.domain.models import FileChange


class RuffStaticAnalyzer:
    def run(self, files: list[FileChange]) -> str:
        python_files = [f.path for f in files if f.path.endswith(".py")]
        if not python_files:
            return "No Python files to lint."
        result = subprocess.run(
            ["ruff", "check", *python_files],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout or result.stderr or "No issues."
