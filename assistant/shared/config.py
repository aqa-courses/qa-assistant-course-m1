"""Configuration: which model each agent uses and how model calls are retried."""

from __future__ import annotations

import os

from google.adk.models import Gemini
from google.genai import types  # noqa: F401  (types.HttpRetryOptions)

DEFAULT_MODEL = "gemini-3.5-flash"


class MissingConfigError(RuntimeError):
    """A required setting is missing. The message is written for the agent and the user."""


def model_name(agent_name: str) -> str:
    """AGENT_MODEL_<AGENT_NAME> → AGENT_MODEL → DEFAULT_MODEL."""
    # TODO М1.1: read the per-agent variable first, then AGENT_MODEL, then fall back to DEFAULT_MODEL.
    return DEFAULT_MODEL


def get_llm(agent_name: str) -> Gemini:
    """The model for one agent, with retries on 408/5xx.

    Only the model call is retried. Tools are never re-run by this retry,
    so a tool with side effects cannot fire twice because of it.
    """
    # TODO М1.1: pass retry_options=types.HttpRetryOptions(...): a few attempts with
    #  exponential backoff on 408 and 5xx. Not on 429: think about why.
    return Gemini(model=model_name(agent_name))


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
