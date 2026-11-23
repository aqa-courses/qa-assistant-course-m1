"""M1: model per agent from the environment, retries in the SDK, adaptive thinking for schemas."""

import warnings

from google.adk.agents.context_cache_config import ContextCacheConfig
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
    assert isinstance(llm, AnthropicLlm), "a bare 'claude-...' string would go through Google Cloud"
    assert llm.max_retries >= 2
    assert llm.timeout <= 300, "the SDK default is 10 minutes per call"
    client = llm._anthropic_client
    assert (client.max_retries, client.timeout) == (llm.max_retries, llm.timeout)


def test_a_model_can_be_deep_copied():
    """ADK and the tests copy agents together with their models; a live client cannot be copied."""
    llm = config.get_llm("github_agent")
    assert llm.model_copy(deep=True).model == llm.model


def test_requests_without_a_thinking_config_get_adaptive_thinking():
    request = config.with_adaptive_thinking(LlmRequest())
    assert request.config.thinking_config.thinking_budget == -1


def test_an_agents_own_thinking_config_is_kept():
    own = types.ThinkingConfig(thinking_budget=0)
    request = LlmRequest(config=types.GenerateContentConfig(thinking_config=own))
    assert config.with_adaptive_thinking(request).config.thinking_config.thinking_budget == 0


def test_requests_get_a_prompt_cache_unless_the_app_set_one():
    assert config.with_prompt_cache(LlmRequest()).cache_config is config.PROMPT_CACHE
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # ContextCacheConfig is experimental in ADK 2.15
        own = ContextCacheConfig(ttl_seconds=3600)
    assert config.with_prompt_cache(LlmRequest(cache_config=own)).cache_config is own
