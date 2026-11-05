"""Pure helpers over unified-diff patches as returned by the GitHub and GitLab APIs."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace

from agent_langgraph.domain.models import FileChange

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _walk(patch: str) -> Iterator[tuple[str, int | None, str]]:
    """Yield (kind, new_line_number, raw_line) for every line of a patch.

    kind is one of 'hunk', 'add', 'context', 'del', 'meta'. Only 'add' and
    'context' lines exist in the new file, so only they carry a line number.
    """
    new_line: int | None = None
    for raw in patch.splitlines():
        header = _HUNK_HEADER.match(raw)
        if header:
            new_line = int(header.group(1))
            yield "hunk", None, raw
        elif new_line is None or raw.startswith("\\"):
            yield "meta", None, raw
        elif raw.startswith("+"):
            yield "add", new_line, raw
            new_line += 1
        elif raw.startswith("-"):
            yield "del", None, raw
        else:
            yield "context", new_line, raw
            new_line += 1


def added_lines(patch: str) -> set[int]:
    """New-file line numbers that the patch adds or modifies."""
    return {n for kind, n, _ in _walk(patch) if kind == "add" and n is not None}


def commentable_lines(patch: str) -> set[int]:
    """New-file line numbers an inline review comment can be anchored to."""
    return {n for kind, n, _ in _walk(patch) if kind in ("add", "context") and n is not None}


_HUNK_HEADER_FULL = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def line_positions(patch: str) -> dict[int, int | None]:
    """Map each commentable new-file line to its old-file line.

    Added lines map to None (they have no old line). Context lines map to the
    old line they came from: GitLab needs both numbers to anchor a comment on
    an unchanged line, while GitHub only needs the new one.
    """
    positions: dict[int, int | None] = {}
    old: int | None = None
    new: int | None = None
    for raw in patch.splitlines():
        header = _HUNK_HEADER_FULL.match(raw)
        if header:
            old, new = int(header.group(1)), int(header.group(2))
        elif old is None or new is None or raw.startswith("\\"):
            continue
        elif raw.startswith("+"):
            positions[new] = None
            new += 1
        elif raw.startswith("-"):
            old += 1
        else:
            positions[new] = old
            old += 1
            new += 1
    return positions


def annotate_patch(patch: str) -> str:
    """Prefix each line with its new-file line number so an LLM can cite it."""
    rendered = []
    for _kind, number, raw in _walk(patch):
        prefix = f"{number:>5} " if number is not None else "      "
        rendered.append(prefix + raw)
    return "\n".join(rendered)


def apply_budget(
    files: list[FileChange], max_file_chars: int, max_total_chars: int
) -> tuple[list[FileChange], list[str]]:
    """Cap patch sizes so a huge PR cannot blow the model's context or cost.

    Returns the budgeted files plus the paths that were cut or dropped, so the
    review can say what it did not look at.
    """
    budgeted: list[FileChange] = []
    truncated: list[str] = []
    remaining = max_total_chars
    for change in files:
        patch = change.patch
        limit = min(max_file_chars, remaining)
        if len(patch) > limit:
            patch = _cut_at_line(patch, limit)
            truncated.append(change.path)
            change = replace(change, patch=patch, truncated=True)
        remaining -= len(patch)
        budgeted.append(change)
    return budgeted, truncated


def _cut_at_line(patch: str, limit: int) -> str:
    if limit <= 0:
        return ""
    cut = patch[:limit]
    newline = cut.rfind("\n")
    return cut[:newline] if newline != -1 else ""
