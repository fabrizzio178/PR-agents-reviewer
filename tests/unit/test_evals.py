from __future__ import annotations

from pathlib import Path

from agent_langgraph.domain.errors import LLMError
from agent_langgraph.domain.models import LLMResult, ReviewItem, Severity, TokenUsage
from agent_langgraph.entrypoints.eval import DEFAULT_DATASET, meets_thresholds, render_report
from agent_langgraph.evals.scoring import PROMPTS, AgentScore, load_cases, run_evals

DATASET = Path(__file__).resolve().parents[2] / "evals" / "dataset.jsonl"


class ScriptedLLM:
    """Returns a canned answer per case, in dataset order."""

    def __init__(self, answers: list[list[ReviewItem] | Exception]) -> None:
        self._answers = iter(answers)

    def review(self, system_prompt: str, user_prompt: str) -> LLMResult:
        answer = next(self._answers)
        if isinstance(answer, Exception):
            raise answer
        return LLMResult(items=answer, usage=TokenUsage())


def test_dataset_is_well_formed():
    assert DEFAULT_DATASET == DATASET
    cases = load_cases(DATASET)
    assert len({c.id for c in cases}) == len(cases) >= 10
    for case in cases:
        assert case.agent in PROMPTS
        assert all(f.patch.startswith("@@") for f in case.files)
        assert all(e.keywords for e in case.expected)
    for agent in PROMPTS:
        assert any(c.agent == agent and not c.expected for c in cases), "needs a clean case"


def test_scoring_counts_hits_misses_and_clean_false_positives():
    cases = [c for c in load_cases(DATASET) if c.id in {"sec-sql-injection", "sec-clean"}]
    hit = ReviewItem("app/users.py", "SQL injection via f-string.", Severity.HIGH, line=11)
    noise = ReviewItem("app/text.py", "Rename this.", Severity.HIGH)

    perfect = run_evals(cases, ScriptedLLM([[hit], []]))["security"]
    assert (perfect.recall, perfect.precision, perfect.failed_cases) == (1.0, 1.0, [])

    noisy = run_evals(cases, ScriptedLLM([[hit], [noise]]))["security"]
    assert noisy.recall == 1.0 and noisy.precision == 0.5
    assert noisy.high_on_clean == 1 and noisy.failed_cases == ["sec-clean"]


def test_an_expectation_needs_file_severity_and_keyword():
    [case] = [c for c in load_cases(DATASET) if c.id == "sec-sql-injection"]
    wrong_file = ReviewItem("other.py", "SQL injection.", Severity.HIGH)
    too_mild = ReviewItem("app/users.py", "SQL injection.", Severity.LOW)
    off_topic = ReviewItem("app/users.py", "Function is too long.", Severity.HIGH)

    score = run_evals([case], ScriptedLLM([[wrong_file, too_mild, off_topic]]))["security"]
    assert score.recall == 0.0 and score.failed_cases == ["sec-sql-injection"]


def test_an_llm_error_counts_as_a_miss():
    [case] = [c for c in load_cases(DATASET) if c.id == "sec-sql-injection"]
    score = run_evals([case], ScriptedLLM([LLMError("boom")]))["security"]
    assert score.errors == 1 and score.recall == 0.0


def test_thresholds_and_report():
    good = {
        "security": AgentScore(cases=5, met=4, missed=1),
        "code_arch": AgentScore(met=2, missed=1),
    }
    assert meets_thresholds(good) is True
    assert meets_thresholds({"security": AgentScore(met=1, missed=1)}) is False
    assert meets_thresholds({"security": AgentScore(met=1, high_on_clean=1)}) is False
    assert "| security | 5 | 0.80 |" in render_report(good, "test-model")
