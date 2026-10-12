"""INGEST node: loads the repo's review config and the PR's diff.

The diff is filtered by the config's ignore patterns and capped to the
configured budget. An invalid config never blocks a review: defaults apply
and the published summary says the file was ignored.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from fnmatch import fnmatchcase
from typing import Any

from agent_langgraph.application.deps import GraphDeps
from agent_langgraph.domain.diff import apply_budget
from agent_langgraph.domain.errors import ConfigError
from agent_langgraph.domain.models import GraphState, RepoConfig

logger = logging.getLogger(__name__)


def make_ingest_node(deps: GraphDeps) -> Callable[[GraphState], dict[str, Any]]:
    def ingest(state: GraphState) -> dict[str, Any]:
        target = state["target"]
        warning = None
        try:
            repo_config = deps.config_provider.load(target)
        except ConfigError as exc:
            logger.warning("repo config ignored: %s", exc)
            repo_config, warning = RepoConfig(), str(exc)

        files = [
            f
            for f in deps.diff_provider.get_changed_files(target)
            if not is_ignored(f.path, repo_config.ignore)
        ]
        budgeted, truncated = apply_budget(
            files, deps.config.max_file_chars, deps.config.max_total_chars
        )
        return {
            "repo_config": repo_config,
            "config_warning": warning,
            "files": budgeted,
            "truncated_files": truncated,
        }

    return ingest


def is_ignored(path: str, patterns: list[str]) -> bool:
    """Glob match on the full path; `*` crosses directories, `dir/` ignores a tree."""
    return any(
        path.startswith(pattern) if pattern.endswith("/") else fnmatchcase(path, pattern)
        for pattern in patterns
    )
