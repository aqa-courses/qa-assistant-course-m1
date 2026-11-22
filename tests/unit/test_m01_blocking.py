"""M1 homework: a slow tool must not freeze the process.

ADK calls a plain `def` tool right in the event loop. While it waits for the
network, /health does not answer either, and an orchestrator kills the container.
"""

import asyncio
import inspect
import time

import httpx
from google.adk.tools import FunctionTool

from assistant.agents.github_agent import tools
from assistant.agents.github_agent.agent import root_agent
from assistant.shared.tools import offload_blocking_tools
from tests.helpers import fake_github
from tests.helpers.runner import run_agent
from tests.helpers.scripted_llm import ScriptedLlm, call, text

ORIGINALS = [tools.list_workflow_runs, tools.get_failed_job_logs, tools.read_repo_file]


def test_agent_tools_do_not_block_the_event_loop():
    for tool in root_agent.tools:
        assert inspect.iscoroutinefunction(tool), f"{tool.__name__} still runs in the event loop"


def test_offloading_keeps_what_the_model_sees():
    for original, wrapped in zip(ORIGINALS, offload_blocking_tools(ORIGINALS)):
        assert wrapped.__name__ == original.__name__
        assert wrapped.__doc__ == original.__doc__
        assert inspect.signature(wrapped) == inspect.signature(original)
        assert FunctionTool(wrapped)._get_declaration() == FunctionTool(original)._get_declaration()


async def test_offloaded_tool_still_returns_its_result():
    async def native(x: int) -> int:
        return x

    def double(x: int) -> int:
        return x * 2

    wrapped_native, wrapped_double = offload_blocking_tools([native, double])
    assert wrapped_native is native  # async tools are left alone
    assert await wrapped_double(21) == 42


async def test_health_answers_while_a_slow_tool_runs(monkeypatch):
    from assistant.app import app

    fake_github.install(monkeypatch, delay=2.0)
    llm = ScriptedLlm.of(call("list_workflow_runs"), text("готово"))
    agent = root_agent.clone(update={"model": llm})

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async def probe_health(stop: asyncio.Event) -> tuple[float, int]:
            """Like a liveness probe: ask /health over and over, return the longest silence."""
            last, worst, answers = time.perf_counter(), 0.0, 0
            while not stop.is_set():
                response = await client.get("/health")
                assert response.json() == {"status": "ok"}
                now = time.perf_counter()
                worst, last, answers = max(worst, now - last), now, answers + 1
                await asyncio.sleep(0.05)
            return worst, answers

        stop = asyncio.Event()
        probe = asyncio.create_task(probe_health(stop))
        started = time.perf_counter()
        result = await run_agent(agent, "Что с прогонами?")
        took = time.perf_counter() - started
        stop.set()
        worst, answers = await probe

    assert result.text == "готово"
    assert took >= 2.0, "the slow tool did not run"
    assert worst < 1.0, f"/health was silent for {worst:.1f} s: the event loop is blocked"
    assert answers >= 10
