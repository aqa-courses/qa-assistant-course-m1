"""M1: every agent loads the way `adk web` loads it.

ADK imports each folder of assistant/agents as a top-level package, not as
assistant.agents.<name>. Imports that work in tests can still fail there.
"""

from pathlib import Path

import pytest
from google.adk.agents import LlmAgent
from google.adk.cli.utils.agent_loader import AgentLoader

AGENTS_DIR = Path(__file__).resolve().parents[2] / "assistant" / "agents"
AGENTS = sorted(p.name for p in AGENTS_DIR.iterdir() if (p / "agent.py").exists())


def test_there_are_agents():
    assert "github_agent" in AGENTS


@pytest.mark.parametrize("name", AGENTS)
def test_agent_loads_like_in_adk_web(name):
    agent = AgentLoader(str(AGENTS_DIR)).load_agent(name)
    assert isinstance(agent, LlmAgent) and agent.name == name
    assert agent.description, "description is what an orchestrator routes by: it cannot be empty"
