"""A fake GitHub API at the edge: replaces tools._github_get, keeps everything above it real."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from assistant.agents.github_agent import tools

RUNS = {"workflow_runs": [
    {"id": 1002, "name": "e2e", "display_title": "Cart: promo", "head_branch": "main", "head_sha": "abcdef1234",
     "event": "push", "status": "completed", "conclusion": "failure", "created_at": "2026-11-20T10:00:00Z",
     "html_url": "https://github.com/student/qa-assistant-course/actions/runs/1002"},
    {"id": 1001, "name": "e2e", "display_title": "Docs", "head_branch": "main", "head_sha": "1234567abc",
     "event": "push", "status": "completed", "conclusion": "success", "created_at": "2026-11-19T10:00:00Z",
     "html_url": "https://github.com/student/qa-assistant-course/actions/runs/1001"},
]}

JOBS = {"jobs": [
    {"id": 7, "name": "e2e", "conclusion": "failure", "html_url": "https://github.com/x/job/7",
     "steps": [{"name": "Start Shoplite", "conclusion": "success"}, {"name": "Run tests", "conclusion": "failure"}]},
    {"id": 8, "name": "lint", "conclusion": "success", "html_url": "https://github.com/x/job/8", "steps": []},
]}

# Shaped like a real Actions log: timestamps, terminal colors, ##[error], runner cleanup after it.
LOG = "\n".join([
    *(f"2026-11-20T10:01:{i % 60:02d}.0000000Z line {i}" for i in range(300)),
    "2026-11-20T10:02:00.0000000Z \x1b[31m  1 failed\x1b[39m",
    "2026-11-20T10:02:00.0000000Z     [chromium] › tests/cart.spec.ts:27:3 › Корзина › SAVE10 уменьшает итог на 10% @id:10",
    "2026-11-20T10:02:01.0000000Z ##[error]Process completed with exit code 1.",
    "2026-11-20T10:02:02.0000000Z Post job cleanup.",
    "2026-11-20T10:02:03.0000000Z Cleaning up orphan processes",
])


def response(path: str, *, json: Any = None, text: str | None = None, status: int = 200) -> httpx.Response:
    request = httpx.Request("GET", tools.API + path)
    if json is not None:
        return httpx.Response(status, json=json, request=request)
    return httpx.Response(status, text=text or "", request=request)


def default_routes(path: str, params: dict | None, accept: str) -> httpx.Response:
    if path.endswith("/runs") :
        return response(path, json=RUNS)
    if path.endswith("/jobs"):
        return response(path, json=JOBS)
    if path.endswith("/logs"):
        return response(path, text=LOG)
    if "/contents/" in path:
        return response(path, text="import { test } from './fixtures';\n")
    raise AssertionError(f"unexpected GitHub call {path}")


def install(monkeypatch, routes: Callable[..., httpx.Response] = default_routes, delay: float = 0.0) -> list[str]:
    """Replace the HTTP edge. Returns the list of called paths."""
    calls: list[str] = []

    def fake(path: str, params: dict | None = None, accept: str = "application/vnd.github+json") -> httpx.Response:
        calls.append(path)
        if delay:
            time.sleep(delay)  # a slow, blocking network call
        return routes(path, params, accept)

    monkeypatch.setattr(tools, "_github_get", fake)
    return calls
