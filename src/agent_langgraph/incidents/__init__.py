"""Incident mode: investigates a failed deploy pipeline and proposes a read-only plan.

Same layering as the review agent: `models` and `ports` are the domain, the
graph and its prompts are the application, and the GitLab adapters live under
`agent_langgraph.adapters.gitlab`. The agent only reads: the one thing it writes
is the report (an issue), and every action in the plan is for a human to run.
"""
