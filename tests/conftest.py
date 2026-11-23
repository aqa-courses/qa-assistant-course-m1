import pytest

_ENV = ["AGENT_MODEL", "AGENT_MODEL_GITHUB_AGENT", "SESSION_TOKEN_BUDGET", "MAX_TOOL_RESPONSE_CHARS",
        "GITHUB_REPO", "GITHUB_TOKEN"]

# Other model providers (assistant/shared/providers.py): their keys and addresses.
_MODEL_ENV = ["GOOGLE_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
              "DEEPSEEK_BASE_URL", "OLLAMA_BASE_URL", "OPENAI_BASE_URL"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Tests never see the developer's .env: no real keys, no real repository."""
    for name in _ENV + _MODEL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    monkeypatch.setenv("GITHUB_REPO", "student/qa-assistant-course")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
