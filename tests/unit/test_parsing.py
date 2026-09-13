from agent_langgraph.application.nodes.parsing import parse_findings
from agent_langgraph.domain.models import Severity


def test_clean_response_yields_no_findings():
    assert parse_findings("security", "CLEAN") == []


def test_parses_pipe_delimited_findings():
    response = "high|auth.py|hardcoded API key\nlow|utils.py|unused variable"
    findings = parse_findings("security", response)
    assert len(findings) == 2
    assert findings[0].severity == Severity.HIGH
    assert findings[1].file == "utils.py"


def test_unparseable_line_is_skipped():
    findings = parse_findings("security", "not a valid line")
    assert findings == []
