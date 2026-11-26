"""GitHub REST tools: workflow runs, logs of failed jobs, repository files.

The functions are plain ``def`` on purpose: httpx' sync client is the simplest
way to call an API. They block while waiting for GitHub, which is why
agent.py passes them through ``offload_blocking_tools``.

Docstrings and type hints are not decoration: ADK turns them into the tool
declaration the model reads to decide when and how to call a tool.
"""

from __future__ import annotations

import functools
import re
from typing import Any

import httpx

from assistant.shared.config import MissingConfigError, require_env

API = "https://api.github.com"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ", re.MULTILINE)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_ERROR = "##[error]"


class GitHubError(Exception):
    pass


def _repo() -> str:
    return require_env("GITHUB_REPO", "Укажи свой форк в формате owner/repo, см. .env.example.")


def _github_get(path: str, params: dict[str, Any] | None = None,
                accept: str = "application/vnd.github+json") -> httpx.Response:
    """One GET to the GitHub API. Tests replace this function."""
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    token = require_env("GITHUB_TOKEN", "Нужен токен с правом чтения Actions и Contents, см. .env.example.")
    headers["Authorization"] = f"Bearer {token}"
    # Job logs answer with a redirect to storage; httpx drops Authorization on a cross-origin redirect.
    response = httpx.get(API + path, params=params, headers=headers, timeout=TIMEOUT, follow_redirects=True)
    if response.status_code == 404:
        raise GitHubError(f"Не найдено: {path}. Проверь GITHUB_REPO и права токена.")
    if response.status_code in (401, 403):
        raise GitHubError(f"GitHub отказал в доступе ({response.status_code}): {response.text[:200]}")
    response.raise_for_status()
    return response


def _errors_as_result(func):
    """Expected failures become {"error": ...}: the model can explain them to the user."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (MissingConfigError, GitHubError) as e:
            return {"error": str(e)}
        except httpx.HTTPError as e:
            return {"error": f"Ошибка запроса к GitHub: {e}"}
    return wrapper


@_errors_as_result
def list_workflow_runs(workflow: str = "e2e.yml", branch: str = "", status: str = "",
                       limit: int = 10) -> dict[str, Any]:
    """Lists recent GitHub Actions runs of the repository, newest first.

    Args:
        workflow: Workflow file name, e.g. "e2e.yml". Empty string means all workflows.
        branch: Only runs on this branch. Empty string means any branch.
        status: "failure", "success", "in_progress", "completed" or empty for any.
        limit: How many runs to return, 1..30.

    Returns:
        {"runs": [{"id", "workflow", "title", "branch", "sha", "event", "status",
        "conclusion", "created_at", "url"}]}
    """
    limit = max(1, min(int(limit), 30))
    path = f"/repos/{_repo()}/actions/workflows/{workflow}/runs" if workflow else f"/repos/{_repo()}/actions/runs"
    params: dict[str, Any] = {"per_page": limit}
    if branch:
        params["branch"] = branch
    if status:
        params["status"] = status
    runs = _github_get(path, params).json().get("workflow_runs", [])
    return {"runs": [{
        "id": r["id"],
        "workflow": r.get("name"),
        "title": r.get("display_title"),
        "branch": r.get("head_branch"),
        "sha": (r.get("head_sha") or "")[:7],
        "event": r.get("event"),
        "status": r.get("status"),
        "conclusion": r.get("conclusion"),
        "created_at": r.get("created_at"),
        "url": r.get("html_url"),
    } for r in runs[:limit]]}


def _clean_log(raw: str) -> list[str]:
    """The log as lines, without timestamps and terminal colors. Module 5 reuses it."""
    return _ANSI.sub("", _TIMESTAMP.sub("", raw)).splitlines()


def _log_tail(lines: list[str], tail_lines: int) -> str:
    """Up to tail_lines lines that end with the last ##[error]: after it the runner only cleans up.

    Without any ##[error], the last tail_lines lines. Module 5 reuses it.
    """
    errors = [i for i, line in enumerate(lines) if line.startswith(_ERROR)]
    end = errors[-1] + 1 if errors else len(lines)
    return "\n".join(lines[max(0, end - tail_lines):end])


@_errors_as_result
def get_failed_job_logs(run_id: int, tail_lines: int = 150) -> dict[str, Any]:
    """Returns the failed jobs of a workflow run: error annotations and the end of each log.

    The log is cut at the last "##[error]" line, because after it the runner only
    cleans up. Timestamps and terminal colors are stripped.

    Args:
        run_id: Workflow run id from list_workflow_runs.
        tail_lines: How many log lines before the last error to return per failed job, 20..500.

    Returns:
        {"run_id", "failed_jobs": [{"id", "name", "failed_steps", "errors", "log_tail", "url"}]}.
        "errors" are the "##[error]" lines. An empty failed_jobs list means no job of the run failed.
    """
    tail_lines = max(20, min(int(tail_lines), 500))
    repo = _repo()
    jobs = _github_get(f"/repos/{repo}/actions/runs/{run_id}/jobs", {"filter": "latest"}).json().get("jobs", [])
    failed = []
    for job in jobs:
        if job.get("conclusion") != "failure":
            continue
        raw = _github_get(f"/repos/{repo}/actions/jobs/{job['id']}/logs", accept="application/vnd.github.raw").text
        lines = _clean_log(raw)
        failed.append({
            "id": job["id"],
            "name": job.get("name"),
            "failed_steps": [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"],
            "errors": [line.removeprefix(_ERROR) for line in lines if line.startswith(_ERROR)],
            "log_tail": _log_tail(lines, tail_lines),
            "url": job.get("html_url"),
        })
    return {"run_id": run_id, "failed_jobs": failed}


@_errors_as_result
def read_repo_file(path: str, ref: str = "") -> dict[str, Any]:
    """Reads a text file from the repository.

    Args:
        path: Path from the repository root, e.g. "autotests/tests/cart.spec.ts".
        ref: Branch, tag or commit sha. Empty: the repository's default branch.

    Returns:
        {"path", "ref", "content"}
    """
    path = path.strip().lstrip("/")
    # No ref: GitHub reads the default branch. A fork may have no "main", or "main" may hold another module.
    content = _github_get(f"/repos/{_repo()}/contents/{path}", {"ref": ref} if ref else None,
                          accept="application/vnd.github.raw+json").text
    return {"path": path, "ref": ref or "ветка по умолчанию", "content": content}
