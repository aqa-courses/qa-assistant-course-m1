"""M1: model per agent from the environment, retries in the SDK, adaptive thinking for schemas."""

from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from assistant.shared import config


def test_model_falls_back_from_agent_to_global_to_default(monkeypatch):
    assert config.model_name("github_agent") == config.DEFAULT_MODEL
    monkeypatch.setenv("AGENT_MODEL", "claude-global")
    assert config.model_name("github_agent") == "claude-global"
    monkeypatch.setenv("AGENT_MODEL_GITHUB_AGENT", "claude-special")
    assert config.model_name("github_agent") == "claude-special"


def test_get_llm_goes_to_the_anthropic_api_with_retries_and_a_finite_timeout():
    llm = config.get_llm("github_agent")
    assert isinstance(llm, AnthropicLlm), "a bare 'claude-...' string would go through Vertex AI"
    client = llm.client
    assert client is not None, "pass your own AsyncAnthropic: that is where retries and the timeout live"
    assert client.max_retries >= 2
    timeout = client.timeout
    seconds = getattr(timeout, "read", timeout)  # a float or an httpx Timeout
    assert seconds is not None and seconds <= 300, "the SDK default is 10 minutes per call"


def test_requests_without_a_thinking_config_get_adaptive_thinking():
    request = config.with_adaptive_thinking(LlmRequest())
    assert request.config.thinking_config.thinking_budget == -1


def test_an_agents_own_thinking_config_is_kept():
    own = types.ThinkingConfig(thinking_budget=0)
    request = LlmRequest(config=types.GenerateContentConfig(thinking_config=own))
    assert config.with_adaptive_thinking(request).config.thinking_config.thinking_budget == 0
