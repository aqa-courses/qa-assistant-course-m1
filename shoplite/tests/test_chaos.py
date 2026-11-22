"""Each fault flag breaks exactly what it claims to break."""

from app import main
from conftest import page_login, product_id


def set_flags(client, **flags):
    r = client.post("/__chaos", json=flags)
    assert r.status_code == 200, r.text
    return r.json()


def test_bug_cart_total_ignores_discount_but_still_shows_it(client, alice):
    client.post("/api/cart/items", json={"product_id": product_id("USB-C хаб")}, headers=alice)
    client.post("/api/cart/promo", json={"code": "SAVE10"}, headers=alice)
    good = client.get("/api/cart", headers=alice).json()
    set_flags(client, bug_cart_total=True)
    bad = client.get("/api/cart", headers=alice).json()
    assert bad["discount"] == good["discount"] == 249
    assert bad["total"] == good["total"] + 249


def test_ui_version_2_renames_hooks_and_redesigns_cart(client):
    page_login(client)
    client.post("/cart/add", data={"product_id": product_id("USB-C хаб")})
    v1 = client.get("/cart").text
    assert 'data-test="cart-total"' in v1 and 'data-test="cart-table"' in v1
    set_flags(client, ui_version=2)
    v2 = client.get("/cart").text
    assert 'data-test="cart-total"' not in v2 and 'data-test="order-sum"' in v2
    assert 'data-test="cart-table"' not in v2 and 'data-test="basket"' in v2
    login = client.get("/login").text
    assert 'data-test="signin-email"' in login and 'data-test="login-email"' not in login


def test_db_down_breaks_pages_api_and_health_but_not_service(client):
    set_flags(client, db_down=True)
    assert client.get("/api/products").status_code == 503
    assert client.get("/health").status_code == 503
    page = client.get("/catalog")
    assert page.status_code == 503 and 'data-test="error-page"' in page.text
    assert client.get("/__chaos").json()["db_down"] is True
    set_flags(client, db_down=False)
    assert client.get("/health").status_code == 200


def test_flaky_search_delays_only_searches(client, monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    set_flags(client, flaky_search=1.0)
    client.get("/api/products")                      # no query: no delay
    assert sleeps == []
    client.get("/api/products", params={"q": "мышь"})
    client.get("/catalog", params={"q": "мышь"})
    assert len(sleeps) == 2 and all(0 <= s <= 5 for s in sleeps)


def test_wishlist_is_hidden_until_enabled(client, alice):
    page_login(client)
    pid = product_id("SSD 1 ТБ")
    assert client.get("/wishlist").status_code == 404
    assert client.post(f"/api/wishlist/{pid}", headers=alice).status_code == 404
    assert 'data-test="wishlist-toggle"' not in client.get(f"/product/{pid}").text
    set_flags(client, feature_wishlist=True)
    assert 'data-test="wishlist-toggle"' in client.get(f"/product/{pid}").text
    assert client.post(f"/api/wishlist/{pid}", headers=alice).json() == {"in_wishlist": True}
    assert "SSD 1 ТБ" in client.get("/wishlist").text


def test_invalid_flags_are_rejected(client):
    assert client.post("/__chaos", json={"ui_version": 3}).status_code == 400
    assert client.post("/__chaos", json={"flaky_search": 2}).status_code == 400
    assert client.post("/__chaos", json={"db_down": "yes"}).status_code == 400
    assert client.post("/__chaos", json={"no_such_flag": True}).status_code == 400
