"""M1: the model name picks the provider; what differs between providers is evened out in one place."""

import pytest
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel

from assistant.shared import config, providers


class Verdict(BaseModel):
    category: str
    confidence: float


def test_the_model_name_picks_the_provider():
    assert isinstance(config.build_llm("claude-haiku-5-5"), AnthropicLlm)
    assert isinstance(config.build_llm("gemini-3.5-flash-lite"), Gemini)
    deepseek = config.build_llm("deepseek/deepseek-flash")
    assert isinstance(deepseek, providers.CourseOpenAI)
    assert (deepseek.model, deepseek.base_url) == ("deepseek-flash", "https://api.deepseek.com")


def test_a_model_name_may_contain_slashes_and_colons():
    """Ollama tags and hosted model ids: only the first segment is the provider."""
    assert config.build_llm("ollama/qwen3:4b").model == "qwen3:4b"
    assert config.build_llm("openai/qwen/qwen3-coder").model == "qwen/qwen3-coder"


def test_an_unknown_model_fails_with_the_list_of_what_is_accepted():
    with pytest.raises(providers.UnknownModelError) as error:
        config.build_llm("gpt-oss")
    assert "deepseek/" in str(error.value) and "ollama/" in str(error.value)


def test_agents_may_sit_on_different_providers(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "ollama/qwen3:4b")
    monkeypatch.setenv("AGENT_MODEL_ROOT", "gemini-3.5-flash-lite")
    assert isinstance(config.get_llm("github_agent"), providers.CourseOpenAI)
    assert isinstance(config.get_llm("root"), Gemini)


def test_the_server_address_comes_from_the_environment(monkeypatch):
    """Any compatible server — a gateway, a hosted Qwen, a remote Ollama — without touching the code."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434/v1")
    assert config.build_llm("openai/some-model").base_url == "https://llm.example.test/v1"
    assert config.build_llm("ollama/qwen3:4b").base_url == "http://gpu-box:11434/v1"


def test_retries_and_the_timeout_reach_the_openai_client(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    llm = config.build_llm("deepseek/deepseek-flash", max_retries=4, timeout=120.0)
    client = llm._openai_client
    assert (client.max_retries, client.timeout, client.api_key) == (4, 120.0, "sk-test")
    assert str(client.base_url).startswith("https://api.deepseek.com")


def test_retries_and_the_timeout_reach_gemini():
    llm = config.build_llm("gemini-3.5-flash-lite", max_retries=4, timeout=120.0)
    assert llm.retry_options.attempts == 5, "attempts count the first call too"
    assert llm.client_kwargs["http_options"].timeout == 120_000, "google-genai takes milliseconds"


def test_every_provider_model_can_be_deep_copied():
    """ADK and the tests copy agents together with their models; a live client cannot be copied."""
    for name in ("gemini-3.5-flash-lite", "deepseek/deepseek-flash", "ollama/qwen3:4b"):
        llm = config.build_llm(name, max_retries=4, timeout=120.0)
        assert llm.model_copy(deep=True).model == llm.model


def test_the_output_schema_moves_into_the_prompt():
    """DeepSeek takes JSON mode, not a strict schema: the schema is sent as text."""
    request = LlmRequest(config=types.GenerateContentConfig(system_instruction="Classify the failure."))
    request.set_output_schema(Verdict)
    request = providers.with_schema_in_the_prompt(request)
    assert request.config.response_schema is None
    assert request.config.response_mime_type == "application/json"
    instruction = request.config.system_instruction
    assert instruction.startswith("Classify the failure.")
    assert "JSON" in instruction and '"confidence"' in instruction, "DeepSeek's JSON mode needs the word and the shape"


def test_a_request_without_a_schema_is_left_alone():
    request = LlmRequest(config=types.GenerateContentConfig(system_instruction="Answer briefly."))
    request = providers.with_schema_in_the_prompt(request)
    assert request.config.system_instruction == "Answer briefly."
    assert request.config.response_mime_type is None


def test_reasoning_tokens_are_not_counted_twice():
    """The OpenAI format reports reasoning inside completion_tokens; Claude and Gemini report it apart."""
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=1000, candidates_token_count=300, thoughts_token_count=200, total_token_count=1300)
    usage = providers.with_disjoint_usage(LlmResponse(usage_metadata=usage)).usage_metadata
    assert (usage.candidates_token_count, usage.thoughts_token_count) == (100, 200)
    assert usage.candidates_token_count + usage.thoughts_token_count + usage.prompt_token_count == usage.total_token_count


def test_a_429_is_recognised_whoever_sent_it():
    import anthropic
    import httpx
    import openai
    from google.genai import errors

    request = httpx.Request("POST", "https://llm.example.test/v1")
    assert providers.is_rate_limit(anthropic.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None))
    assert providers.is_rate_limit(openai.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None))
    assert providers.is_rate_limit(errors.ClientError(429, {"error": {"message": "quota"}}))
    assert not providers.is_rate_limit(openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None))
    assert not providers.is_rate_limit(TimeoutError())
