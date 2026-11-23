"""Agent callbacks: tool logging, token accounting, a token budget and truncation of huge tool results.

Every agent gets them through ``**AGENT_CALLBACKS``. A callback that returns
None lets ADK go on as usual; a returned value replaces what ADK would do.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from assistant.shared.config import env_int

log = logging.getLogger("assistant")

# Session state keys. Kept in the session, so the budget spans the whole conversation.
TOKENS_PROMPT = "usage:prompt_tokens"
TOKENS_OUTPUT = "usage:output_tokens"
TOKENS_TOTAL = "usage:total_tokens"
MODEL_CALLS = "usage:model_calls"

DEFAULT_MAX_TOOL_RESPONSE_CHARS = 20_000
DEFAULT_SESSION_TOKEN_BUDGET = 1_500_000


def _short(value: Any, limit: int = 200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit})"


# ---- tools ---------------------------------------------------------------

def log_tool_call(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> None:
    log.info("tool %s(%s) agent=%s", tool.name, _short(args), tool_context.agent_name)
    return None  # None: run the tool as usual


def truncate_tool_response(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext,
                           tool_response: Any) -> dict[str, Any] | None:
    """Replace a result bigger than MAX_TOOL_RESPONSE_CHARS with its head and a note.

    One oversized result (a full CI log, a screenshot in base64) goes into every
    following model call of the session: it eats the budget and can exceed the
    context window. The note tells the model what happened, so it can ask for less.
    """
    limit = env_int("MAX_TOOL_RESPONSE_CHARS", DEFAULT_MAX_TOOL_RESPONSE_CHARS)
    text = tool_response if isinstance(tool_response, str) else json.dumps(
        tool_response, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return None  # None: keep the original result
    log.warning("tool %s returned %d chars, truncated to %d", tool.name, len(text), limit)
    return {
        "truncated": True,
        "original_chars": len(text),
        "head": text[:limit],
        "note": (f"Ответ инструмента обрезан до {limit} из {len(text)} символов. "
                 "Если нужно больше, запроси меньший фрагмент."),
    }


def tool_error_to_result(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext,
                         error: Exception) -> dict[str, Any]:
    """An exception in a tool becomes a result the model can read and react to."""
    log.exception("tool %s failed", tool.name, exc_info=error)
    return {"error": f"{type(error).__name__}: {error}"}


# ---- model ---------------------------------------------------------------

def count_tokens(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    """Add llm_response.usage_metadata to the session state: MODEL_CALLS, TOKENS_* keys.

    Output is what Anthropic bills as output: the answer (candidates_token_count)
    plus thinking (thoughts_token_count), which ADK reports separately.
    """
    usage = llm_response.usage_metadata
    state = callback_context.state
    state[MODEL_CALLS] = state.get(MODEL_CALLS, 0) + 1
    if usage is None:
        return None
    state[TOKENS_PROMPT] = state.get(TOKENS_PROMPT, 0) + (usage.prompt_token_count or 0)
    output = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    state[TOKENS_OUTPUT] = state.get(TOKENS_OUTPUT, 0) + output
    state[TOKENS_TOTAL] = state.get(TOKENS_TOTAL, 0) + (usage.total_token_count or 0)
    log.info("model %s: +%s tokens, session total %s", callback_context.agent_name,
             usage.total_token_count, state[TOKENS_TOTAL])
    return None


def enforce_token_budget(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """Stop calling the model once the session spent SESSION_TOKEN_BUDGET tokens.

    Returning a response from before_model skips the model call: a looping agent
    stops here instead of on the bill.
    """
    budget = env_int("SESSION_TOKEN_BUDGET", DEFAULT_SESSION_TOKEN_BUDGET)
    spent = callback_context.state.get(TOKENS_TOTAL, 0)
    if spent < budget:
        return None
    log.warning("session token budget exhausted: %s of %s", spent, budget)
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(
        text=f"Лимит токенов на сессию исчерпан ({spent} из {budget}). Начни новую сессию.")]))


AGENT_CALLBACKS: dict[str, Any] = {
    "before_tool_callback": log_tool_call,
    "after_tool_callback": truncate_tool_response,
    "on_tool_error_callback": tool_error_to_result,
    "before_model_callback": enforce_token_budget,
    "after_model_callback": count_tokens,
}
