import os
import tempfile
from pathlib import Path

# Must happen before the app is imported: db.DB_PATH is read at import time.
os.environ["SHOPLITE_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")
for flag in ("UI_VERSION", "BUG_CART_TOTAL", "FLAKY_SEARCH", "DB_DOWN", "FEATURE_WISHLIST", "CHAOS_TOKEN"):
    os.environ.pop(flag, None)

import pytest
from fastapi.testclient import TestClient

from app import chaos, db
from app.main import app


@pytest.fixture(autouse=True)
def fresh_state():
    db.reset()
    chaos.state.update(chaos.Chaos().as_dict())
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def api_login(client, email="alice@example.com", password="password123") -> dict:
    r = client.post("/api/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def page_login(client, email="alice@example.com", password="password123"):
    r = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


@pytest.fixture
def alice(client):
    return api_login(client)


def product_id(name: str) -> int:
    with db.transaction() as conn:
        return conn.execute("SELECT id FROM products WHERE name = ?", (name,)).fetchone()["id"]
