"""Configuration: which model each agent uses and how model calls are retried."""

from __future__ import annotations

import os
from functools import cached_property
from typing import AsyncGenerator

from anthropic import AsyncAnthropic
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

DEFAULT_MODEL = "claude-haiku-5-5"


class MissingConfigError(RuntimeError):
    """A required setting is missing. The message is written for the agent and the user."""


def with_adaptive_thinking(llm_request: LlmRequest) -> LlmRequest:
    """Ask for adaptive thinking unless the agent configured thinking itself.

    ADK hands an `output_schema` to Claude as a tool and, when the request has no
    thinking config, forces the call to it (`tool_choice: tool`). Claude Sonnet 5.5
    rejects forced tool use with a 400; with adaptive thinking ADK offers the tool
    instead. Current Claude models think adaptively by default, so nothing else changes.
    """
    config = llm_request.config or types.GenerateContentConfig()
    if config.thinking_config is None:
        config.thinking_config = types.ThinkingConfig(thinking_budget=-1)  # -1: adaptive
    llm_request.config = config
    return llm_request


class CourseClaude(AnthropicLlm):
    """Claude through the Anthropic API (ANTHROPIC_API_KEY), always with adaptive thinking.

    A bare "claude-..." string in `Agent(model=...)` would resolve to ADK's `Claude`,
    which goes through Google Cloud (Agent Platform in the ADK docs). The course uses the Anthropic API directly.
    """

    max_retries: int = 2      # the Anthropic SDK defaults
    timeout: float = 600.0    # seconds per call

    @cached_property
    def _anthropic_client(self) -> AsyncAnthropic:
        # Built on the first real call, not stored as a field: a live client cannot be
        # deep-copied, and agents (with their models) get copied in tests and by ADK.
        return AsyncAnthropic(max_retries=self.max_retries, timeout=self.timeout)

    async def generate_content_async(self, llm_request: LlmRequest,
                                     stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        async for response in super().generate_content_async(with_adaptive_thinking(llm_request), stream):
            yield response


def model_name(agent_name: str) -> str:
    """AGENT_MODEL_<AGENT_NAME> → AGENT_MODEL → DEFAULT_MODEL."""
    # TODO М1.1: read the per-agent variable first, then AGENT_MODEL, then fall back to DEFAULT_MODEL.
    return DEFAULT_MODEL


def get_llm(agent_name: str) -> CourseClaude:
    """The model for one agent, with retries in the Anthropic SDK and a finite timeout.

    Only the model call is retried. Tools are never re-run by this retry,
    so a tool with side effects cannot fire twice because of it.
    """
    # TODO М1.1: pass max_retries=... and timeout=... Which errors does the SDK retry,
    #  and why is retrying 429 fine here? How long may one call hang by default?
    return CourseClaude(model=model_name(agent_name))


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
