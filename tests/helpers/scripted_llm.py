"""ScriptedLlm: a model that answers from a script. No network, no tokens, same result every run.

    llm = ScriptedLlm.of(call("list_workflow_runs", limit=3), text("Последний прогон упал"))
    agent = root_agent.clone(update={"model": llm})

Every request the agent sends is kept in ``llm.requests``: tests check what the
model would have seen, e.g. a truncated tool result.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types
from pydantic import Field


def call(tool: str, tokens: int | None = None, **args: Any) -> LlmResponse:
    """The model decides to call a tool."""
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=tool, args=args))]),
        usage_metadata=_usage(tokens),
    )


def text(answer: str, tokens: int | None = None) -> LlmResponse:
    """The model answers with text; the turn ends."""
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=answer)]), usage_metadata=_usage(tokens))


def _usage(tokens: int | None) -> types.GenerateContentResponseUsageMetadata | None:
    if tokens is None:
        return None
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=tokens - tokens // 4, candidates_token_count=tokens // 4, total_token_count=tokens)


class ScriptedLlm(BaseLlm):
    model: str = "scripted"
    script: list[LlmResponse] = Field(default_factory=list)
    requests: list[LlmRequest] = Field(default_factory=list)

    @classmethod
    def of(cls, *responses: LlmResponse) -> "ScriptedLlm":
        return cls(script=list(responses))

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False
                                     ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request.model_copy(deep=True))
        if not self.script:
            raise AssertionError(f"ScriptedLlm: the script is over, but the agent made call #{len(self.requests)}")
        yield self.script.pop(0)

    def function_responses(self) -> list[types.FunctionResponse]:
        """Tool results the model received, in order."""
        seen: list[types.FunctionResponse] = []
        for request in self.requests:
            for content in request.contents:
                for part in content.parts or []:
                    if part.function_response and part.function_response not in seen:
                        seen.append(part.function_response)
        return seen
