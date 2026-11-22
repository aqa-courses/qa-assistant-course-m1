"""Service endpoints: health, reset, crawl, access token."""

from conftest import product_id


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_reset_restores_seed_and_optionally_flags(client, alice):
    client.post("/api/cart/items", json={"product_id": product_id("SSD 1 ТБ")}, headers=alice)
    client.post("/__chaos", json={"bug_cart_total": True})
    client.post("/__reset")
    assert client.get("/__chaos").json()["bug_cart_total"] is True       # flags kept by default
    assert client.get("/api/me", headers=alice).status_code == 401       # sessions are gone too
    client.post("/__reset", params={"flags": True})
    assert client.get("/__chaos").json()["bug_cart_total"] is False


def test_crawl_lists_pages_and_follows_flags(client):
    pages = client.get("/__crawl").json()["pages"]
    assert set(pages) == {"login", "catalog", "product", "cart", "checkout", "profile"}
    assert "cart-total" in pages["cart"] and "add-to-cart" in pages["catalog"]

    client.post("/__chaos", json={"ui_version": 2, "feature_wishlist": True})
    pages = client.get("/__crawl").json()["pages"]
    assert "order-sum" in pages["cart"] and "cart-total" not in pages["cart"]
    assert "wishlist" in pages and "wishlist-toggle" in pages["product"]


def test_crawl_does_not_touch_test_users(client, alice):
    client.get("/__crawl")
    assert client.get("/api/cart", headers=alice).json()["items"] == []


def test_service_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("CHAOS_TOKEN", "s3cret")
    assert client.get("/__chaos").status_code == 403
    assert client.get("/__chaos", headers={"X-Chaos-Token": "s3cret"}).status_code == 200
