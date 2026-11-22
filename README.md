# QA-ассистент на Google ADK — учебный репозиторий

Репозиторий курса: за 8 модулей вы собираете ассистента QA-инженера на [Google ADK](https://google.github.io/adk-docs/). Ассистент разбирает падения CI, чинит автотесты, триажит обращения поддержки и работает в продакшене. Всё — на учебном магазине Shoplite, который можно ломать по команде.

## Что внутри

| Папка | Что это |
|---|---|
| [shoplite/](shoplite/) | учебный стенд: магазин на FastAPI с флагами поломок |
| [autotests/](autotests/) | 15 e2e-тестов стенда на Playwright + TypeScript |
| [docs/product/](docs/product/) | спецификации магазина, по ним работает триаж |
| [fixtures/](fixtures/) | тест-кейсы и 40 тикетов поддержки с эталонной разметкой |
| [assistant/](assistant/) | ассистент — его вы и пишете |
| [tests/](tests/) | автопроверка заданий; без модели и без сети |
| [modules/](modules/) | задания модулей |

## Как проходить курс

Каждый модуль — пара веток:

- `mNN-start` — заготовка: код с `TODO` и тесты, которые пока падают;
- `mNN-solution` — эталонное решение. Подсматривать можно, но после своей попытки.

```bash
git switch m01-start
# решаете задания из modules/m01/README.md, пока не позеленеет:
pytest tests/unit
```

Решение сдаётся пулл-реквестом в ваш репозиторий: GitHub Actions прогоняет автопроверку, а я делаю код-ревью. Следующий модуль начинается с `git merge origin/m02-start`. Если отстали, начните с `m01-solution`.

## Быстрый старт

Нужны Python 3.11+, Docker, Node.js 24 (для автотестов) и ключ Gemini API.

```bash
cp .env.example .env              # GOOGLE_API_KEY, GITHUB_REPO, GITHUB_TOKEN
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

docker build -t shoplite shoplite && docker run --rm -p 8000:8000 shoplite   # стенд на :8000
adk web --port 8080 assistant/agents                                          # чат с агентами на :8080
```

Агентам нужен ваш форк этого репозитория на GitHub: они читают его прогоны Actions и файлы.

## Сколько стоит модель

Автопроверка не тратит токены: вместо Gemini в тестах работает `ScriptedLlm`, который отвечает по сценарию. Токены тратятся только когда вы сами говорите с агентом в `adk web`. Лимит на сессию задаёт `SESSION_TOKEN_BUDGET` (по умолчанию 200 000): зациклившийся агент остановится на нём, а не на вашем счёте.
