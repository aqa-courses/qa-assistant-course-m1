"""Runs an agent through the real ADK Runner with a fresh in-memory session per run.

Doubles go at the edge (the model, the HTTP call), never around the Runner:
a test that mocks the whole chain passes even when the chain is broken.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types


@dataclass
class RunResult:
    text: str
    events: list[Event] = field(default_factory=list)
    session: Session | None = None

    @property
    def state(self) -> dict[str, Any]:
        return dict(self.session.state) if self.session else {}


async def run_agent(agent: BaseAgent, message: str, state: dict[str, Any] | None = None) -> RunResult:
    service = InMemorySessionService()
    session = await service.create_session(app_name="test", user_id="student", state=state or {})
    runner = Runner(app_name="test", agent=agent, session_service=service)
    events: list[Event] = []
    async for event in runner.run_async(
            user_id="student", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)])):
        events.append(event)
    final = [p.text for e in events if e.is_final_response() and e.content for p in e.content.parts or [] if p.text]
    session = await service.get_session(app_name="test", user_id="student", session_id=session.id)
    return RunResult(text="\n".join(final), events=events, session=session)
