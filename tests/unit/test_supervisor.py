from agent_langgraph.application.nodes.supervisor import supervisor
from agent_langgraph.domain.models import FileChange


def test_readme_only_change_still_routes_to_code_arch():
    state = {"files": [FileChange(path="README.md", patch="", additions=1, deletions=0)]}
    result = supervisor(state)
    assert result["active_agents"] == ["code_arch"]


def test_python_change_activates_both_agents():
    state = {"files": [FileChange(path="app/main.py", patch="", additions=5, deletions=1)]}
    result = supervisor(state)
    assert result["active_agents"] == ["security", "code_arch"]
