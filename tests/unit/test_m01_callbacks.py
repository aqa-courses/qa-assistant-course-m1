"""M1: callbacks count tokens, stop at the budget, truncate huge results, turn tool crashes into errors."""

from google.genai import types

from assistant.agents.github_agent import tools
from assistant.agents.github_agent.agent import root_agent
from assistant.shared import observability as obs
from tests.helpers import fake_github
from tests.helpers.runner import run_agent
from tests.helpers.scripted_llm import ScriptedLlm, call, text


def scripted(*responses):
    llm = ScriptedLlm.of(*responses)
    return llm, root_agent.clone(update={"model": llm})


async def test_tokens_are_counted_per_session(monkeypatch):
    fake_github.install(monkeypatch)
    llm, agent = scripted(call("list_workflow_runs", tokens=100, limit=2), text("Упал прогон 1002", tokens=40))
    result = await run_agent(agent, "Что с последним прогоном?")
    assert result.text == "Упал прогон 1002"
    assert result.state[obs.TOKENS_TOTAL] == 140
    assert result.state[obs.MODEL_CALLS] == 2



async def test_thinking_is_counted_as_output():
    """Claude bills thinking as output tokens; ADK reports it apart from the visible answer."""
    answer = text("Упал прогон 1002")
    answer.usage_metadata = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=300, candidates_token_count=40, thoughts_token_count=60, total_token_count=400)
    _, agent = scripted(answer)
    result = await run_agent(agent, "Что с последним прогоном?")
    assert result.state[obs.TOKENS_OUTPUT] == 100, "thinking is billed as output"
    assert result.state[obs.TOKENS_PROMPT] + result.state[obs.TOKENS_OUTPUT] == result.state[obs.TOKENS_TOTAL]


async def test_budget_stops_the_model_before_the_next_call(monkeypatch):
    fake_github.install(monkeypatch)
    monkeypatch.setenv("SESSION_TOKEN_BUDGET", "100")
    llm, agent = scripted(call("list_workflow_runs", tokens=150), text("не должен быть вызван"))
    result = await run_agent(agent, "Что с прогонами?")
    assert len(llm.requests) == 1, "the second model call must be skipped"
    assert "Лимит токенов" in result.text


async def test_huge_tool_result_is_truncated_before_the_model_sees_it(monkeypatch):
    huge = "x" * 1_000_000
    fake_github.install(monkeypatch, routes=lambda path, params, accept: fake_github.response(path, text=huge))
    monkeypatch.setenv("MAX_TOOL_RESPONSE_CHARS", "5000")
    llm, agent = scripted(call("read_repo_file", path="big.json"), text("Файл огромный"))
    await run_agent(agent, "Покажи big.json")
    [seen] = llm.function_responses()
    assert seen.response["truncated"] is True
    assert seen.response["original_chars"] > 1_000_000
    assert len(str(seen.response)) < 6000


async def test_small_tool_result_is_untouched(monkeypatch):
    fake_github.install(monkeypatch)
    llm, agent = scripted(call("read_repo_file", path="autotests/tests/cart.spec.ts"), text("ok"))
    await run_agent(agent, "Покажи тест корзины")
    [seen] = llm.function_responses()
    assert "truncated" not in seen.response and "import" in seen.response["content"]


async def test_tool_crash_becomes_an_error_result(monkeypatch):
    def broken(path, params=None, accept=""):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(tools, "_github_get", broken)
    llm, agent = scripted(call("list_workflow_runs"), text("GitHub недоступен"))
    result = await run_agent(agent, "Что с прогонами?")
    [seen] = llm.function_responses()
    assert "connection reset" in seen.response["error"]
    assert result.text == "GitHub недоступен"
