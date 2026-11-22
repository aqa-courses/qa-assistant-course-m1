"""M1: GitHub tools return short, model-friendly data and errors as text."""

from assistant.agents.github_agent import tools
from tests.helpers import fake_github


def test_list_workflow_runs_maps_fields(monkeypatch):
    calls = fake_github.install(monkeypatch)
    runs = tools.list_workflow_runs(limit=2)["runs"]
    assert calls == ["/repos/student/qa-assistant-course/actions/workflows/e2e.yml/runs"]
    assert runs[0] == {
        "id": 1002, "workflow": "e2e", "title": "Cart: promo", "branch": "main", "sha": "abcdef1",
        "event": "push", "status": "completed", "conclusion": "failure", "created_at": "2026-11-20T10:00:00Z",
        "url": "https://github.com/student/qa-assistant-course/actions/runs/1002",
    }


def test_failed_job_logs_only_failed_jobs_cut_at_the_last_error(monkeypatch):
    fake_github.install(monkeypatch)
    result = tools.get_failed_job_logs(1002, tail_lines=50)
    [job] = result["failed_jobs"]  # the successful "lint" job is skipped
    assert job["name"] == "e2e" and job["failed_steps"] == ["Run tests"]
    assert job["errors"] == ["Process completed with exit code 1."]
    lines = job["log_tail"].splitlines()
    assert len(lines) == 50
    assert lines[-1] == "##[error]Process completed with exit code 1."  # runner cleanup is cut off
    assert "  1 failed" in lines  # terminal colors stripped
    assert any("SAVE10 уменьшает итог на 10% @id:10" in line for line in lines)
    assert not any(line.startswith("2026-") for line in lines)


def test_read_repo_file(monkeypatch):
    calls = fake_github.install(monkeypatch)
    result = tools.read_repo_file("/autotests/tests/cart.spec.ts", ref="m01-start")
    assert calls == ["/repos/student/qa-assistant-course/contents/autotests/tests/cart.spec.ts"]
    assert result["path"] == "autotests/tests/cart.spec.ts" and "import" in result["content"]


def test_missing_config_is_a_readable_error_not_an_exception(monkeypatch):
    monkeypatch.delenv("GITHUB_REPO")
    result = tools.list_workflow_runs()
    assert "GITHUB_REPO" in result["error"]


def test_http_errors_become_readable_errors(monkeypatch):
    def fake_get(url, **kwargs):
        return fake_github.response(url.removeprefix(tools.API), status=404)

    monkeypatch.setattr(tools.httpx, "get", fake_get)  # the real _github_get, a fake network
    result = tools.read_repo_file("nope.txt")
    assert "Не найдено" in result["error"] and "nope.txt" in result["error"]
