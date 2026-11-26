"""HTTP entry point: the ADK API and dev UI plus /health.

Run: uvicorn --env-file .env assistant.app:app --port 8080
"""

from pathlib import Path

from google.adk.cli.fast_api import get_fast_api_app

AGENTS_DIR = Path(__file__).parent / "agents"

app = get_fast_api_app(agents_dir=str(AGENTS_DIR), web=True)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. If the event loop is blocked, this does not answer either."""
    return {"status": "ok"}
