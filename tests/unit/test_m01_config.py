"""M1: model per agent from the environment, retries only where they help."""

from google.adk.models import Gemini

from assistant.shared import config


def test_model_falls_back_from_agent_to_global_to_default(monkeypatch):
    assert config.model_name("github_agent") == config.DEFAULT_MODEL
    monkeypatch.setenv("AGENT_MODEL", "gemini-global")
    assert config.model_name("github_agent") == "gemini-global"
    monkeypatch.setenv("AGENT_MODEL_GITHUB_AGENT", "gemini-special")
    assert config.model_name("github_agent") == "gemini-special"


def test_get_llm_retries_timeouts_and_server_errors_but_not_quota():
    llm = config.get_llm("github_agent")
    assert isinstance(llm, Gemini)
    retry = llm.retry_options
    assert retry is not None and retry.attempts >= 2
    codes = set(retry.http_status_codes)
    assert {408, 500, 503} <= codes
    assert 429 not in codes, "429 is a quota: retrying in seconds does not help"
