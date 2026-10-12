from agent_langgraph.domain.models import Severity, TokenUsage


def test_severity_ranks_are_ordered():
    assert Severity.LOW.rank < Severity.MEDIUM.rank < Severity.HIGH.rank


def test_token_usage_adds_fieldwise():
    total = TokenUsage(10, 2) + TokenUsage(5, 1)
    assert total == TokenUsage(input_tokens=15, output_tokens=3)
