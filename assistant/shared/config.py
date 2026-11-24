"""Configuration: which model each agent uses and how model calls are retried."""

from __future__ import annotations

import os
import warnings
from functools import cached_property
from typing import AsyncGenerator

from anthropic import AsyncAnthropic
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

DEFAULT_MODEL = "claude-haiku-5-5"

# The SDK retries what passes by itself while it waits: 408, 409, 5xx, dropped connections
# and 429. Anthropic's rate limits refill continuously and a 429 carries retry-after, which
# the SDK honours. 400/401/403/404 are never retried: the same request fails the same way.
MAX_RETRIES = 4          # the first call plus 4 retries, with exponential backoff
TIMEOUT_SECONDS = 120.0  # per call; the SDK default is 10 minutes


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


# Prompt caching. Every call re-sends the instruction, the tools and the whole conversation;
# with a cache Anthropic reads the repeated start at a tenth of the price. Measured on Haiku
# (module 1 lesson): a 5-question conversation with root, $0.025 → $0.012.
# ContextCacheConfig is marked experimental in ADK 2.15 and warns on creation: once, here.
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    PROMPT_CACHE = ContextCacheConfig(min_tokens=1024, ttl_seconds=300, cache_intervals=100)


def with_prompt_cache(llm_request: LlmRequest) -> LlmRequest:
    """Cache the repeated start of the prompt unless the app configured caching itself.

    The app-level way is App(context_cache_config=...). adk web builds one App per
    agent folder, and the pipelines run their own Runners: per request, every agent
    and every pipeline gets the cache, wherever it runs.
    """
    if llm_request.cache_config is None:
        llm_request.cache_config = PROMPT_CACHE
    return llm_request


class CourseClaude(AnthropicLlm):
    """Claude through the Anthropic API (ANTHROPIC_API_KEY), with adaptive thinking and a prompt cache.

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
        async for response in super().generate_content_async(
                with_prompt_cache(with_adaptive_thinking(llm_request)), stream):
            yield response


def model_name(agent_name: str) -> str:
    """AGENT_MODEL_<AGENT_NAME> → AGENT_MODEL → DEFAULT_MODEL."""
    per_agent = os.getenv(f"AGENT_MODEL_{agent_name.upper()}", "").strip()
    return per_agent or os.getenv("AGENT_MODEL", "").strip() or DEFAULT_MODEL


def build_llm(model: str, **client) -> BaseLlm:
    """The model object for a model name. The name picks the provider.

    claude-... is the course's reference and goes to CourseClaude. Everything else —
    gemini-..., deepseek/..., ollama/..., openai/... — is built in providers.py.
    """
    if model.startswith("claude-"):
        return CourseClaude(model=model, **client)
    from assistant.shared import providers   # here, not at the top: Claude alone needs neither SDK
    return providers.build(model, **client)


def get_llm(agent_name: str) -> BaseLlm:
    """The model for one agent, with retries in the provider's SDK and a finite timeout.

    Only the model call is retried. Tools are never re-run by this retry,
    so a tool with side effects cannot fire twice because of it.
    """
    return build_llm(model_name(agent_name), max_retries=MAX_RETRIES, timeout=TIMEOUT_SECONDS)


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
