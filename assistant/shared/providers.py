"""Models other than Claude: Gemini and everything that speaks the OpenAI Chat Completions API.

The course is measured on Claude (config.CourseClaude). The provider is chosen by the model name:

    AGENT_MODEL=claude-haiku-5-5          Anthropic API           ANTHROPIC_API_KEY
    AGENT_MODEL=gemini-3.5-flash-lite     Gemini API              GOOGLE_API_KEY
    AGENT_MODEL=deepseek/deepseek-flash   DeepSeek                DEEPSEEK_API_KEY
    AGENT_MODEL=ollama/qwen3:4b           a local Ollama          no key
    AGENT_MODEL=openai/<model>            any compatible server   OPENAI_BASE_URL, OPENAI_API_KEY

Agents may sit on different providers: the name is resolved per agent (AGENT_MODEL_<AGENT>).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import cached_property
from typing import Any, AsyncGenerator

from google.adk.integrations.openai import OpenAILlm
from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel


@dataclass(frozen=True)
class Provider:
    """An OpenAI-compatible server: where it is and which variable holds its key."""

    base_url: str   # default; <PREFIX>_BASE_URL overrides it
    key_env: str    # "" for a server without keys


# The prefix of the model name, before the first "/".
OPENAI_COMPATIBLE: dict[str, Provider] = {
    "deepseek": Provider("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "ollama": Provider("http://localhost:11434/v1", ""),
    "openai": Provider("https://api.openai.com/v1", "OPENAI_API_KEY"),
}


class UnknownModelError(ValueError):
    """The model name matches no provider. The message lists what is accepted."""


def with_schema_in_the_prompt(llm_request: LlmRequest) -> LlmRequest:
    """Move the output schema from the request parameters into the instruction.

    ADK sends an `output_schema` as OpenAI's strict `json_schema` response format. Compatible
    servers differ here: DeepSeek documents only `json_object`. JSON mode plus the schema in
    the prompt is what all of them take; the reply is validated by our own parsers anyway.
    """
    config = llm_request.config
    if config is None or config.response_schema is None:
        return llm_request
    schema = config.response_schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        schema = schema.model_json_schema()
    elif isinstance(schema, BaseModel):
        schema = type(schema).model_json_schema()
    elif isinstance(schema, types.Schema):
        schema = schema.model_dump(exclude_none=True, mode="json")
    config.response_schema = None
    config.response_mime_type = "application/json"   # → response_format: json_object
    llm_request.append_instructions([
        "Reply with one JSON object and nothing else. It must match this JSON schema:\n"
        + json.dumps(schema, ensure_ascii=False)])
    return llm_request


def with_disjoint_usage(response: LlmResponse) -> LlmResponse:
    """Report the answer and the reasoning as separate token counts, as Claude and Gemini do.

    The OpenAI format counts reasoning tokens inside completion_tokens. ADK copies both
    numbers as they are, so answer + reasoning would count the reasoning twice.
    """
    usage = response.usage_metadata
    if usage and usage.thoughts_token_count and usage.candidates_token_count:
        usage.candidates_token_count = max(usage.candidates_token_count - usage.thoughts_token_count, 0)
    return response


class CourseOpenAI(OpenAILlm):
    """A model behind the OpenAI Chat Completions API: DeepSeek, Ollama, any compatible server."""

    key_env: str = ""
    max_retries: int = 2      # the OpenAI SDK defaults
    timeout: float = 600.0    # seconds per call

    @cached_property
    def _openai_client(self) -> AsyncOpenAI:
        # Built on the first real call, as in CourseClaude: a live client cannot be deep-copied.
        if self.client is not None:
            return self.client
        # A server without keys still needs a non-empty string: the SDK refuses to start without one.
        key = os.getenv(self.key_env, "").strip() if self.key_env else "none"
        return AsyncOpenAI(api_key=key or "missing", base_url=self.base_url,
                           max_retries=self.max_retries, timeout=self.timeout)

    async def generate_content_async(self, llm_request: LlmRequest,
                                     stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        async for response in super().generate_content_async(with_schema_in_the_prompt(llm_request), stream):
            yield with_disjoint_usage(response)


def build(model: str, **client: Any) -> BaseLlm:
    """The model object for a non-Claude model name. `client` is max_retries and timeout, if given."""
    if model.startswith("gemini-"):
        return _gemini(model, **client)
    prefix, _, name = model.partition("/")
    provider = OPENAI_COMPATIBLE.get(prefix)
    if provider is None or not name:
        raise UnknownModelError(
            f"Не знаю, чья это модель: {model!r}. Подходят claude-..., gemini-... и "
            + ", ".join(f"{p}/<модель>" for p in OPENAI_COMPATIBLE) + ".")
    base_url = os.getenv(f"{prefix.upper()}_BASE_URL", "").strip() or provider.base_url
    return CourseOpenAI(model=name, base_url=base_url, key_env=provider.key_env, **client)


def _gemini(model: str, max_retries: int | None = None, timeout: float | None = None) -> Gemini:
    """Gemini through the Gemini API (GOOGLE_API_KEY). Retries and the timeout live in google-genai."""
    options: dict[str, Any] = {}
    if max_retries is not None:
        options["retry_options"] = types.HttpRetryOptions(attempts=max_retries + 1)   # attempts include the first call
    if timeout is not None:
        options["client_kwargs"] = {"http_options": types.HttpOptions(timeout=int(timeout * 1000))}   # milliseconds
    return Gemini(model=model, **options)


def is_rate_limit(error: Exception) -> bool:
    """A 429 from any provider. The SDKs name the field differently: status_code or code."""
    return 429 in (getattr(error, "status_code", None), getattr(error, "code", None))
