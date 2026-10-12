from agent_langgraph.domain.diff import (
    added_lines,
    annotate_patch,
    apply_budget,
    commentable_lines,
)
from agent_langgraph.domain.models import FileChange

TWO_HUNKS = (
    "@@ -1,3 +1,4 @@ def header():\n"
    " keep\n"
    "-old\n"
    "+new\n"
    "+extra\n"
    " tail\n"
    "\\ No newline at end of file\n"
    "@@ -20,2 +21,3 @@\n"
    " ctx\n"
    "+added\n"
    " end"
)


def test_added_lines_track_new_file_numbering_across_hunks():
    assert added_lines(TWO_HUNKS) == {2, 3, 22}


def test_commentable_lines_include_context_but_not_deletions():
    assert commentable_lines(TWO_HUNKS) == {1, 2, 3, 4, 21, 22, 23}


def test_empty_patch_has_no_lines():
    assert added_lines("") == set()
    assert commentable_lines("") == set()


def test_annotate_patch_prefixes_new_line_numbers():
    annotated = annotate_patch("@@ -1,1 +1,2 @@\n a\n-b\n+c").splitlines()
    assert annotated[1].split() == ["1", "a"]
    assert annotated[2].strip() == "-b"
    assert annotated[3].split() == ["2", "+c"]


def _file(path: str, size: int) -> FileChange:
    return FileChange(path=path, patch="x" * 9 + "\n" + "y" * (size - 10), additions=1, deletions=0)


def test_budget_leaves_small_diffs_untouched():
    files = [_file("a.py", 50)]
    budgeted, truncated = apply_budget(files, max_file_chars=100, max_total_chars=100)
    assert budgeted == files and truncated == []


def test_budget_cuts_a_large_file_at_a_line_boundary():
    budgeted, truncated = apply_budget([_file("a.py", 50)], 20, 1000)
    assert truncated == ["a.py"]
    assert budgeted[0].patch == "x" * 9
    assert budgeted[0].truncated is True


def test_budget_drops_patches_once_the_total_is_spent():
    budgeted, truncated = apply_budget([_file("a.py", 50), _file("b.py", 50)], 100, 50)
    assert truncated == ["b.py"]
    assert budgeted[1].patch == ""
