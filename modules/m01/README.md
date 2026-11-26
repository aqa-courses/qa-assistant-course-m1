# Модуль 1. Основы ADK

Первый агент: `github_agent` отвечает на вопросы о прогонах GitHub Actions вашего форка и читает файлы репозитория. Вокруг него — то, без чего агента нельзя пускать к людям: выбор модели через окружение, повтор упавших вызовов модели, логи, счёт токенов и защита от огромных ответов инструментов.

Объём: около 100 строк Python.

## Что уже есть в `m01-start`

- `assistant/agents/github_agent/agent.py` — агент: инструкция, описание, список инструментов.
- `assistant/agents/github_agent/tools.py` — HTTP-вызов GitHub `_github_get` и готовый инструмент `list_workflow_runs` как образец.
- `assistant/app.py` — FastAPI-приложение ADK с `/health`.
- `assistant/shared/config.py` — `CourseClaude`: Claude через Anthropic API с адаптивными размышлениями. Зачем свой класс — в уроке.
- `assistant/shared/providers.py` — другие модели вместо Claude: Gemini и серверы с API OpenAI (DeepSeek, Ollama). Провайдер выбирается по имени модели, готово, писать не нужно.
- `tests/helpers/scripted_llm.py` — `ScriptedLlm`, модель по сценарию для тестов.

## Задания

Каждому заданию соответствует файл тестов. Задание сделано, когда его тесты зелёные.

### 1. Модель и повторы — `assistant/shared/config.py`

- `model_name(agent)`: `AGENT_MODEL_<AGENT>` → `AGENT_MODEL` → `DEFAULT_MODEL`. Так можно дать дорогую модель одному агенту, не трогая остальных.
- `get_llm(agent)`: `CourseClaude` с `max_retries` и `timeout`. Временные сбои и 429 SDK повторяет сам, выдерживая паузу из `retry-after`. Ваша часть — ограничить число повторов и время одного вызова: по умолчанию SDK ждёт ответа до 10 минут.

Тесты: `tests/unit/test_m01_config.py` и `tests/unit/test_m01_providers.py`. Провайдеры в `providers.py` уже готовы, но тест выбирает модель для агента через ваш `model_name`, поэтому до задания часть его проверок красная.

### 2. Инструменты GitHub — `assistant/agents/github_agent/tools.py`

- `get_failed_job_logs(run_id, tail_lines)`: упавшие джобы прогона, строки `##[error]` и хвост лога **до последней ошибки** — после неё раннер только прибирается. Таймстемпы и цвета терминала убрать.
- Очистку и хвост напишите в заготовленных `_clean_log(raw)` и `_log_tail(lines, tail_lines)`, а не внутри `get_failed_job_logs`: в модуле 5 их возьмёт разбор падений CI.
- `read_repo_file(path, ref)`: текст файла из репозитория.

Ожидаемые сбои (нет настройки, 404, нет доступа) возвращаются как `{"error": "..."}`: модель перескажет их пользователю. Docstring и аннотации типов — это то, что модель читает о вашем инструменте, пишите их для неё.

Тесты: `tests/unit/test_m01_tools.py`.

### 3. Колбэки — `assistant/shared/observability.py`

- `log_tool_call` — лог каждого вызова инструмента;
- `count_tokens` — токены сессии в `state` по `usage_metadata` ответа модели. Размышления Claude оплачиваются как выход, но ADK кладёт их отдельно от ответа, в `thoughts_token_count`: в `usage:output_tokens` нужны оба;
- `enforce_token_budget` — если сессия потратила `SESSION_TOKEN_BUDGET`, вернуть ответ вместо вызова модели;
- `truncate_tool_response` — ответ инструмента больше `MAX_TOOL_RESPONSE_CHARS` заменить началом и пометкой. Один полный лог CI попадает в каждый следующий вызов модели в сессии;
- `tool_error_to_result` — исключение в инструменте превратить в `{"error": ...}`.

Тесты: `tests/unit/test_m01_callbacks.py`.

### 4. Домашнее задание: зависший процесс — `assistant/shared/tools.py`

ADK вызывает инструмент-функцию `def` прямо в event loop. Пока инструмент ждёт GitHub, процесс не делает ничего другого: не отвечает другим пользователям и не отвечает на `/health`. Liveness-проба в Kubernetes ждёт ответа секунду, после трёх неудач контейнер перезапускают — вместе со всеми живыми сессиями.

1. **Воспроизведите.** Запустите `pytest tests/unit/test_m01_blocking.py` и прочитайте, почему падает `test_health_answers_while_a_slow_tool_runs`. Потом вживую: `uvicorn assistant.app:app --port 8080`, в соседнем терминале (Git Bash) опрашивайте `/health` раз в полсекунды:

   ```bash
   while true; do
     curl -s -o /dev/null -m 1 -w "$(date +%T) %{http_code} %{time_total}s\n" http://localhost:8080/health
     sleep 0.5
   done
   ```

   То же в PowerShell (вместо кода `000` он пишет «нет ответа»):

   ```powershell
   while ($true) { $s = Get-Date; try { $c = (Invoke-WebRequest http://localhost:8080/health -TimeoutSec 1 -UseBasicParsing).StatusCode } catch { $c = 'нет ответа' }; '{0:HH:mm:ss} {1} {2:N2}s' -f (Get-Date), $c, ((Get-Date) - $s).TotalSeconds; Start-Sleep -Milliseconds 500 }
   ```

   Попросите агента в `/dev-ui` разобрать упавший прогон. Пока инструмент ждёт GitHub, ответы `/health` задерживаются, а код `000` значит, что ответа не было дольше секунды: настоящая проба засчитала бы неудачу. Остановить опрос — Ctrl+C. После исправления повторите и сравните. Чтобы снова увидеть зависание уже с исправленным кодом, временно уберите обёртку в `assistant/agents/github_agent/agent.py`: `tools=[list_workflow_runs, get_failed_job_logs, read_repo_file]` вместо `offload_blocking_tools([...])`, а после проверки верните.
2. **Почините** `offload_blocking_tools`: синхронную функцию обернуть в `async def`, которая ждёт `asyncio.to_thread`. Через `functools.wraps`, иначе модель получит инструмент с другими параметрами — это тоже проверяется тестом.
3. **Ответьте в пулл-реквесте (PR):** в ADK 2.x есть встроенный `RunConfig(tool_thread_pool_config=...)`. Почему в этом проекте он не спасает `/health` в `adk web`, а обёртка спасает? (Подсказка: кто создаёт `RunConfig`, когда запрос приходит через `get_fast_api_app`.)

Тесты: `tests/unit/test_m01_blocking.py`.

### 5. Агент загружается как в `adk web`

`tests/unit/test_m01_loading.py` грузит агентов тем же загрузчиком, что `adk web`. Он импортирует папку агента как пакет верхнего уровня, поэтому общий код импортируется абсолютно: `from assistant.shared...`.

Писать здесь ничего не нужно, если вы импортируете общий код абсолютно, как в заготовке. Тест — страховка: он покраснеет, если в агенте появится относительный импорт вроде `from ...shared`.

## Проверка

```bash
pytest tests/unit          # всё зелёное — можно открывать PR
adk web --port 8080 assistant/agents
```

Спросите агента в `adk web`: «Почему упал последний прогон e2e?» Чтобы прогон был красным, запустите его на сломанном стенде: в форке Actions → e2e → Run workflow, отметьте `bug_cart_total` и нажмите Run workflow. Прогон идёт несколько минут. Какие ещё есть флаги и что каждый ломает — в [shoplite/README.md](../../shoplite/README.md#флаги-поломок). Агент должен назвать `@id:10` и ошибку про итог корзины, не выдумав ни id, ни текста.

Расход: разговор из 4 вопросов — около 150 тыс. токенов, $0,006 на Haiku с кэшем промпта (замер; больше всего весит лог упавшего прогона, без кэша было бы $0,016). Точное число агент сам записывает в `state` сессии (`usage:total_tokens`), его видно во вкладке State в `adk web`.
