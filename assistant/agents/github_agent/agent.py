"""github_agent: answers questions about CI runs and repository files.

Imports: shared code absolutely (``assistant.shared``), this agent's own modules
relatively. ``adk web`` imports this folder as a top-level package
``github_agent``, so ``...shared`` would point outside of it.
"""

from google.adk.agents import Agent

from assistant.shared.config import get_llm
from assistant.shared.observability import AGENT_CALLBACKS
from assistant.shared.tools import offload_blocking_tools
from .tools import get_failed_job_logs, list_workflow_runs, read_repo_file

INSTRUCTION = """\
Ты помощник QA-инженера. Отвечаешь на вопросы о прогонах GitHub Actions и файлах репозитория
с автотестами интернет-магазина Shoplite.

Как работать:
- Про прогоны сначала вызывай list_workflow_runs. Прогон e2e — это workflow "e2e.yml".
- Чтобы понять, почему прогон упал, вызывай get_failed_job_logs с id прогона.
  В ответе назови упавшие тесты и ошибку каждого так, как они записаны в логе.
- Если нужно посмотреть код теста или конфиг, вызывай read_repo_file. Тесты лежат в autotests/tests.
- Не выдумывай: id прогонов, имена тестов и тексты ошибок бери только из ответов инструментов.
- Если инструмент вернул error, перескажи его пользователю и подскажи, что поправить.

Отвечай по-русски, коротко, со ссылкой на прогон.
"""

root_agent = Agent(
    **AGENT_CALLBACKS,
    name="github_agent",
    model=get_llm("github_agent"),
    description=(
        "Прогоны GitHub Actions и файлы репозитория: последние запуски e2e, "
        "почему упал прогон, логи упавших джоб, содержимое тестов и конфигов."
    ),
    instruction=INSTRUCTION,
    tools=offload_blocking_tools([list_workflow_runs, get_failed_job_logs, read_repo_file]),
)
