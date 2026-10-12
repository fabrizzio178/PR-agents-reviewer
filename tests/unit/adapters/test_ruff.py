"""Ruff adapter against the real ruff binary on files in a temp directory."""

from __future__ import annotations

from agent_langgraph.adapters.static_analysis.ruff_runner import RuffStaticAnalyzer
from agent_langgraph.domain.models import FileChange, Severity

SOURCE = "import os\nimport sys\n\nprint('hi')\n"
# Only line 2 (`import sys`) was added by the PR; line 1 predates it.
PATCH = "@@ -1,3 +1,4 @@\n import os\n+import sys\n \n print('hi')"


def _change(path: str, patch: str = PATCH) -> FileChange:
    return FileChange(path=path, patch=patch, additions=1, deletions=0)


def test_reports_only_diagnostics_on_added_lines(tmp_path):
    (tmp_path / "mod.py").write_text(SOURCE, encoding="utf-8")

    findings = RuffStaticAnalyzer(root=tmp_path).run([_change("mod.py")])

    assert [(f.file, f.line, f.agent) for f in findings] == [("mod.py", 2, "ruff")]
    assert findings[0].message.startswith("F401")
    assert findings[0].severity == Severity.MEDIUM


def test_files_missing_from_the_working_tree_are_skipped(tmp_path):
    assert RuffStaticAnalyzer(root=tmp_path).run([_change("not_checked_out.py")]) == []


def test_non_python_files_are_ignored(tmp_path):
    (tmp_path / "notes.md").write_text("# hi", encoding="utf-8")
    assert RuffStaticAnalyzer(root=tmp_path).run([_change("notes.md")]) == []


def test_syntax_errors_are_reported_not_fatal(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    findings = RuffStaticAnalyzer(root=tmp_path).run(
        [_change("bad.py", "@@ -0,0 +1,1 @@\n+def broken(:")]
    )
    assert findings and all(f.severity == Severity.MEDIUM for f in findings)
