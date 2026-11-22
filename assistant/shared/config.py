"""Configuration: which model each agent uses and how model calls are retried."""

from __future__ import annotations

import os

from google.adk.models import Gemini
from google.genai import types

DEFAULT_MODEL = "gemini-3.5-flash"

# Retry model calls on timeouts and server errors only.
# 429 is deliberately absent: a per-minute quota does not recover in the few
# seconds a retry waits, so retrying only burns more of it and delays the error.
RETRY_STATUS_CODES = (408, 500, 502, 503, 504)
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=4,          # the first call plus 3 retries
    initial_delay=1.0,
    max_delay=20.0,
    exp_base=2.0,
    jitter=1.0,
    http_status_codes=list(RETRY_STATUS_CODES),
)


class MissingConfigError(RuntimeError):
    """A required setting is missing. The message is written for the agent and the user."""


def model_name(agent_name: str) -> str:
    """AGENT_MODEL_<AGENT_NAME> → AGENT_MODEL → DEFAULT_MODEL."""
    per_agent = os.getenv(f"AGENT_MODEL_{agent_name.upper()}", "").strip()
    return per_agent or os.getenv("AGENT_MODEL", "").strip() or DEFAULT_MODEL


def get_llm(agent_name: str) -> Gemini:
    """The model for one agent, with retries on 408/5xx.

    Only the model call is retried. Tools are never re-run by this retry,
    so a tool with side effects cannot fire twice because of it.
    """
    return Gemini(model=model_name(agent_name), retry_options=RETRY_OPTIONS)


def require_env(name: str, hint: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingConfigError(f"Не задана переменная окружения {name}. {hint}")
    return value


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default
