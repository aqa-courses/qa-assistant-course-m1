"""Check the course environment: python scripts/doctor.py, before module 1 and after every merge.

Python and the packages from pyproject.toml, Docker, Node.js, .env, the fork and the token, the model key. Nothing is
written anywhere and no tokens are spent: the model key is checked by listing
models. Secrets are never printed.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failed = False


def ok(text: str) -> None:
    print(f"  ok    {text}")


def warn(text: str) -> None:
    print(f"  !     {text}")


def fail(text: str) -> None:
    global failed
    failed = True
    print(f"  НЕТ   {text}")


def run(*cmd: str) -> str | None:
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        out = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def read_env() -> dict[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            env[key.strip()] = value.split(" #")[0].strip().strip('"').strip("'")
    return {**env, **{k: v for k, v in os.environ.items() if v}}  # the shell wins, as for the app


def get(url: str, headers: dict[str, str]) -> tuple[int, dict | list | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "qa-course-doctor", **headers})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, None
    except ssl.SSLError as error:
        raise SystemExit(f"  НЕТ   Python не может открыть HTTPS ({error}). "
                         "Обычно это корпоративный прокси или сертификат в системе; спросите администратора.")
    except urllib.error.URLError as error:
        return 0, {"reason": str(error.reason)}


def check_tools() -> None:
    print("Программы")
    if sys.version_info >= (3, 11):
        ok(f"Python {sys.version.split()[0]}")
    else:
        fail(f"Python {sys.version.split()[0]}: нужен 3.11 или новее")
    if sys.prefix == sys.base_prefix:
        warn("виртуальное окружение не активировано (README, «Окружение»)")
    missing = missing_packages()
    if missing:
        fail(f'не установлены {", ".join(missing)}: pip install -e ".[dev]" (заготовка модуля могла добавить зависимости)')
    else:
        ok("все зависимости из pyproject.toml установлены")
    docker = run("docker", "version", "--format", "{{.Server.Version}}")
    if docker:
        ok(f"Docker {docker}")
    else:
        fail("Docker не установлен или не запущен (Docker Desktop должен работать)")
    node = run("node", "--version")
    if not node:
        fail("Node.js не найден: нужен 24 (автотесты; с модуля 3 — браузер для агента)")
    elif int(node.lstrip("v").split(".")[0]) < 24:
        warn(f"Node.js {node}: курс проверен на 24")
    else:
        ok(f"Node.js {node}")
    if (ROOT / "autotests" / "node_modules" / "@playwright" / "test").exists():
        ok("зависимости автотестов установлены")
    else:
        warn("автотесты не установлены, они нужны с модуля 4: cd autotests && npm ci && npx playwright install chromium")


def missing_packages() -> list[str]:
    """Requirements of pyproject.toml (and the dev extra) that are not installed, extras included."""
    import re
    import tomllib
    from importlib import metadata
    try:
        from packaging.requirements import Requirement
    except ImportError:
        Requirement = None
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wanted = [*project.get("dependencies", []), *project.get("optional-dependencies", {}).get("dev", [])]
    missing = []
    for line in wanted:
        match = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*(?:\[([^\]]*)\])?", line)
        name, extras = match.group(1), [e.strip() for e in (match.group(2) or "").split(",") if e.strip()]
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
            continue
        for extra in extras:
            for dep in metadata.requires(name) or []:
                if Requirement is not None:
                    req = Requirement(dep)
                    if not req.marker or not req.marker.evaluate({"extra": extra}):
                        continue
                    dep_name = req.name
                elif re.search(rf"extra\s*==\s*['\"]{re.escape(extra)}['\"]", dep):
                    dep_name = re.match(r"\s*([A-Za-z0-9_.\-]+)", dep).group(1)
                else:
                    continue
                try:
                    metadata.version(dep_name)
                except metadata.PackageNotFoundError:
                    missing.append(f"{name}[{extra}]")
                    break
    return missing


def check_model(env: dict[str, str]) -> None:
    print("Модель")
    model = env.get("AGENT_MODEL") or "claude-haiku-5-5"
    if not model.startswith("claude"):
        need = {"gemini": "GOOGLE_API_KEY", "deepseek/": "DEEPSEEK_API_KEY", "openai/": "OPENAI_BASE_URL"}
        key = next((v for k, v in need.items() if model.startswith(k)), None)
        if key and not env.get(key):
            fail(f"AGENT_MODEL={model}, но {key} пуст")
        else:
            ok(f"AGENT_MODEL={model}: ключ этого провайдера не проверяю (docs/models.md)")
        return
    if not env.get("ANTHROPIC_API_KEY"):
        fail("ANTHROPIC_API_KEY пуст (README, «Ключ Claude»)")
        return
    status, _ = get("https://api.anthropic.com/v1/models?limit=1",
                    {"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    if status == 200:
        ok(f"ключ Claude принят, модель {model}")
    elif status == 401:
        fail("ключ Claude не принят: скопируйте его заново из консоли Claude")
    elif status == 403:
        fail("ключ Claude отклонён (403): проверьте страну по списку из README и баланс")
    else:
        warn(f"api.anthropic.com не ответил как обычно (код {status}): нет сети?")


def check_github(env: dict[str, str]) -> None:
    print("Форк и токен GitHub")
    repo, token = env.get("GITHUB_REPO", ""), env.get("GITHUB_TOKEN", "")
    if not repo or repo.startswith("owner/") or "/" not in repo:
        fail("GITHUB_REPO не задан: <ваш логин>/<ваш форк>")
        return
    if not token:
        fail("GITHUB_TOKEN пуст (README, «Форк и токен GitHub»)")
        return
    api, headers = f"https://api.github.com/repos/{repo}", {"Authorization": f"Bearer {token}"}
    status, info = get(api, headers)
    if status == 401:
        fail("GitHub не принял токен: он просрочен или скопирован не целиком")
        return
    if status != 200 or not isinstance(info, dict):
        fail(f"{repo} не виден с этим токеном (код {status}): опечатка в GITHUB_REPO "
             "или токену не дан доступ к этому репозиторию")
        return
    ok(f"{repo} виден")
    if not info.get("fork"):
        warn(f"{repo} — не форк. Агенты будут работать с ним; так и задумано?")
    if not info.get("has_issues"):
        fail("Issues выключены: Settings → General → Features → Issues (нужны с модуля 2)")
    status, branches = get(f"{api}/branches?per_page=100", headers)
    names = {b["name"] for b in branches} if status == 200 and isinstance(branches, list) else set()
    if status != 200:
        fail(f"ветки не читаются (код {status}): токену нужно Contents: read")
    elif len(names) <= 1:
        fail("в форке одна ветка: при создании форка осталась галочка «Copy the … branch only». "
             "Создайте форк заново без неё")
    elif "m01-start" not in names:
        fail("в форке нет ветки m01-start")
    else:
        ok(f"веток в форке: {len(names)}")
    status, workflows = get(f"{api}/actions/workflows", headers)
    if status != 200 or not isinstance(workflows, dict):
        fail(f"Actions не читаются (код {status}): токену нужно Actions: read")
    else:
        e2e = [w for w in workflows.get("workflows", []) if w.get("path", "").endswith("/e2e.yml")]
        if e2e and e2e[0].get("state") != "active":
            fail("Actions в форке не включены: вкладка Actions → «I understand my workflows, go ahead and enable them»")
        else:
            ok("Actions включены")
    status, _ = get(f"{api}/issues?per_page=1", headers)
    if status == 200:
        ok("Issues читаются")
    else:
        warn("Issues не читаются: токену понадобится Issues: read and write с модуля 2")
    print("        Права на запись (Issues, Contents, Pull requests) без записи не проверить:")
    print("        сверьте их с таблицей в README, раздел «Форк и токен GitHub».")


def main() -> None:
    check_tools()
    if not (ROOT / ".env").exists():
        print("Настройки")
        fail(".env нет: cp .env.example .env и заполните")
    else:
        env = read_env()
        check_model(env)
        check_github(env)
    print("\nВсё готово." if not failed else "\nИсправьте строки с «НЕТ» и запустите проверку ещё раз.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
