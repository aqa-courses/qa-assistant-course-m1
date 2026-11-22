"""Business rules, including those that look like bugs but are intended."""

from conftest import api_login, page_login, product_id


def names(products):
    return [p["name"] for p in products]


# ---- login ---------------------------------------------------------------

def test_login_ok_and_me(client, alice):
    assert client.get("/api/me", headers=alice).json()["email"] == "alice@example.com"


def test_login_wrong_password(client):
    r = client.post("/api/login", json={"email": "alice@example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Неверный email или пароль"


def test_locked_user_cannot_login(client):
    r = client.post("/api/login", json={"email": "locked@example.com", "password": "password123"})
    assert r.status_code == 403
    assert "заблокирована" in r.json()["detail"]


def test_login_page_shows_error_inside_form(client):
    r = client.post("/login", data={"email": "alice@example.com", "password": "nope"})
    assert r.status_code == 401
    assert 'data-test="login-error"' in r.text


def test_api_requires_token(client):
    assert client.get("/api/cart").status_code == 401


def test_pages_redirect_to_login(client):
    r = client.get("/cart", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")


# ---- search --------------------------------------------------------------

def test_search_is_case_insensitive_for_cyrillic(client):
    assert names(client.get("/api/products", params={"q": "МОНИТОР"}).json()) == ['Монитор 27"', 'Монитор 24"']


def test_search_by_name_only_not_description(client):
    # "IPS" is in monitors' descriptions only: intended, search looks at names.
    assert client.get("/api/products", params={"q": "IPS"}).json() == []


def test_one_letter_search_does_not_filter_and_shows_hint(client):
    assert len(client.get("/api/products", params={"q": "м"}).json()) == 12
    assert 'data-test="search-hint"' in client.get("/catalog", params={"q": "м"}).text


def test_category_price_and_sort(client):
    got = client.get("/api/products", params={"category": "Мониторы", "sort": "price_asc"}).json()
    assert names(got) == ['Монитор 24"', 'Монитор 27"']
    cheap = client.get("/api/products", params={"max_price": 1000}).json()
    assert names(cheap) == ["Коврик для мыши XL"]


# ---- cart ----------------------------------------------------------------

def test_at_most_five_units_of_one_product(client, alice):
    pid = product_id("USB-C хаб")
    r = client.post("/api/cart/items", json={"product_id": pid, "qty": 7}, headers=alice).json()
    assert r["items"][0]["qty"] == 5
    assert "не больше 5" in r["note"]


def test_limit_is_stock_when_stock_is_lower(client, alice):
    pid = product_id('Монитор 27"')  # stock 4
    r = client.post("/api/cart/items", json={"product_id": pid, "qty": 5}, headers=alice).json()
    assert r["items"][0]["qty"] == 4


def test_out_of_stock_cannot_be_added(client, alice):
    r = client.post("/api/cart/items", json={"product_id": product_id('Монитор 24"')}, headers=alice)
    assert r.status_code == 400 and r.json()["detail"] == "Товара нет в наличии"


def test_save10_skips_sale_items(client, alice):
    client.post("/api/cart/items", json={"product_id": product_id("USB-C хаб")}, headers=alice)          # 2490
    client.post("/api/cart/items", json={"product_id": product_id("Беспроводная мышь")}, headers=alice)  # sale 1990
    cart = client.post("/api/cart/promo", json={"code": "save10"}, headers=alice).json()
    assert cart["discount"] == 249.0
    assert cart["total"] == 2490 + 1990 - 249 + 299


def test_save10_on_sale_items_only_explains_why(client, alice):
    client.post("/api/cart/items", json={"product_id": product_id("Беспроводная мышь")}, headers=alice)
    cart = client.post("/api/cart/promo", json={"code": "SAVE10"}, headers=alice).json()
    assert cart["discount"] == 0 and "не действует на товары со скидкой" in cart["promo_note"]


def test_welcome500_threshold_and_promo_replacement(client, alice):
    client.post("/api/cart/items", json={"product_id": product_id("USB-C хаб")}, headers=alice)  # 2490
    cart = client.post("/api/cart/promo", json={"code": "WELCOME500"}, headers=alice).json()
    assert cart["discount"] == 0 and "от 3 000" in cart["promo_note"]
    client.patch(f"/api/cart/items/{product_id('USB-C хаб')}", json={"qty": 2}, headers=alice)   # 4980
    cart = client.get("/api/cart", headers=alice).json()
    assert cart["discount"] == 500
    cart = client.post("/api/cart/promo", json={"code": "SAVE10"}, headers=alice).json()
    assert cart["promo"] == "SAVE10" and cart["discount"] == 498  # replaced, not stacked


def test_unknown_promo(client, alice):
    r = client.post("/api/cart/promo", json={"code": "FREE"}, headers=alice)
    assert r.status_code == 400 and r.json()["detail"] == "Промокод не найден"


def test_free_shipping_from_5000(client, alice):
    pid = product_id("Механическая клавиатура")  # 6990
    cart = client.post("/api/cart/items", json={"product_id": pid}, headers=alice).json()
    assert cart["shipping"] == 0 and cart["total"] == 6990


# ---- orders --------------------------------------------------------------

def test_order_clears_cart_and_takes_stock(client, alice):
    pid = product_id("SSD 1 ТБ")  # stock 15
    client.post("/api/cart/items", json={"product_id": pid, "qty": 2}, headers=alice)
    r = client.post("/api/orders", json={"address": "Москва, ул. Тестовая, д. 1"}, headers=alice)
    assert r.status_code == 201
    assert client.get("/api/cart", headers=alice).json()["items"] == []
    assert client.get(f"/api/products/{pid}").json()["stock"] == 13
    assert client.get("/api/orders", headers=alice).json()[0]["items"][0]["qty"] == 2


def test_short_address_rejected(client, alice):
    client.post("/api/cart/items", json={"product_id": product_id("SSD 1 ТБ")}, headers=alice)
    r = client.post("/api/orders", json={"address": "Москва"}, headers=alice)
    assert r.status_code == 400 and "адрес" in r.json()["detail"]


def test_restricted_user_cannot_check_out(client):
    h = api_login(client, "restricted@example.com")
    client.post("/api/cart/items", json={"product_id": product_id("SSD 1 ТБ")}, headers=h)
    r = client.post("/api/orders", json={"address": "Москва, ул. Тестовая, д. 1"}, headers=h)
    assert r.status_code == 403 and "недоступно" in r.json()["detail"]


def test_full_ui_purchase_flow(client):
    page_login(client)
    pid = product_id("Коврик для мыши XL")
    client.post("/cart/add", data={"product_id": pid, "qty": 1})
    assert 'data-test="cart-total"' in client.get("/cart").text
    r = client.post("/checkout", data={"address": "Москва, ул. Тестовая, д. 1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/orders/")
    page = client.get(r.headers["location"]).text
    assert 'data-test="order-number"' in page and "оформлен" in page
