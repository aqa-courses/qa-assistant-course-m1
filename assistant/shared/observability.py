"""Agent callbacks: tool logging, token accounting, a token budget and truncation of huge tool results.

Every agent gets them through ``**AGENT_CALLBACKS``. A callback that returns
None lets ADK go on as usual; a returned value replaces what ADK would do.
"""

from __future__ import annotations

import json  # noqa: F401
import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool, ToolContext
from google.genai import types  # noqa: F401

from assistant.shared.config import env_int  # noqa: F401

log = logging.getLogger("assistant")

# Session state keys. Kept in the session, so the budget spans the whole conversation.
TOKENS_PROMPT = "usage:prompt_tokens"
TOKENS_OUTPUT = "usage:output_tokens"
TOKENS_TOTAL = "usage:total_tokens"
MODEL_CALLS = "usage:model_calls"

DEFAULT_MAX_TOOL_RESPONSE_CHARS = 20_000
DEFAULT_SESSION_TOKEN_BUDGET = 1_500_000


# ---- tools ---------------------------------------------------------------

def log_tool_call(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> None:
    # TODO М1.3: log the tool name, its arguments (shortened) and the agent name.
    return None


def truncate_tool_response(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext,
                           tool_response: Any) -> dict[str, Any] | None:
    """Replace a result bigger than MAX_TOOL_RESPONSE_CHARS with its head and a note.

    Return {"truncated": True, "original_chars": ..., "head": ..., "note": ...},
    the note telling the model what happened. Return None for a small result.
    """
    # TODO М1.3
    return None


def tool_error_to_result(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext,
                         error: Exception) -> dict[str, Any] | None:
    """An exception in a tool becomes {"error": "<Type>: <message>"} the model can react to."""
    # TODO М1.3
    return None


# ---- model ---------------------------------------------------------------

def count_tokens(callback_context: CallbackContext, llm_response: LlmResponse) -> None:
    """Add llm_response.usage_metadata to the session state: MODEL_CALLS, TOKENS_* keys.

    Output is what Anthropic bills as output: the answer (candidates_token_count)
    plus thinking (thoughts_token_count), which ADK reports separately.
    """
    # TODO М1.3
    return None


def enforce_token_budget(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """Once the session spent SESSION_TOKEN_BUDGET tokens, answer instead of the model.

    The answer must say "Лимит токенов" and suggest starting a new session.
    """
    # TODO М1.3
    return None


AGENT_CALLBACKS: dict[str, Any] = {
    "before_tool_callback": log_tool_call,
    "after_tool_callback": truncate_tool_response,
    "on_tool_error_callback": tool_error_to_result,
    "before_model_callback": enforce_token_budget,
    "after_model_callback": count_tokens,
}
