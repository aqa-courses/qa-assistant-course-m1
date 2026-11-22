"""Shoplite: the system under test of the course.

Pages (server-rendered, every interactive element has ``data-test``), a REST
API under ``/api`` for test data setup, and service endpoints under ``/__``:
fault flags, database reset and a UI crawl for the coverage agent.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import chaos, db, shop

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals["dt"] = chaos.dt
templates.env.globals["chaos"] = chaos.state
templates.env.filters["rub"] = shop.rub

SESSION_COOKIE = "sid"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("SHOPLITE_KEEP_DB") != "1" or not db.DB_PATH.exists():
        db.reset()
    yield


app = FastAPI(title="Shoplite", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


# ---- infrastructure fault ------------------------------------------------

@app.middleware("http")
async def db_down_middleware(request: Request, call_next):
    path = request.url.path
    if chaos.state.db_down and not path.startswith(("/__", "/static")):
        if path.startswith("/api") or path == "/health":
            return JSONResponse({"status": "degraded", "detail": "Database unavailable"}, status_code=503)
        return templates.TemplateResponse(
            request, "error.html",
            {"user": None, "code": 503, "message": "Сервис временно недоступен. Попробуйте позже."},
            status_code=503,
        )
    return await call_next(request)


async def maybe_slow_search(query: str) -> None:
    if query.strip() and chaos.state.flaky_search and random.random() < chaos.state.flaky_search:
        await asyncio.sleep(random.uniform(0, 5))


# ---- auth ----------------------------------------------------------------

def find_user(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)
    ).fetchone()


def login(conn: sqlite3.Connection, email: str, password: str) -> tuple[str, sqlite3.Row]:
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if user is None or user["password_hash"] != db.hash_password(password):
        raise shop.ShopError("Неверный email или пароль", 401)
    if user["locked"]:
        raise shop.ShopError("Учётная запись заблокирована. Обратитесь в поддержку.", 403)
    token = secrets.token_urlsafe(24)
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user["id"]))
    return token, user


def page_user(request: Request) -> sqlite3.Row | None:
    with db.transaction() as conn:
        return find_user(conn, request.cookies.get(SESSION_COOKIE))


def api_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    with db.transaction() as conn:
        user = find_user(conn, token)
    if user is None:
        raise HTTPException(401, "Требуется авторизация")
    return user


def to_login(next_path: str) -> RedirectResponse:
    return RedirectResponse(f"/login?next={quote(next_path)}", status_code=303)


def back(path: str, note: str = "", error: str = "") -> RedirectResponse:
    sep = "&" if "?" in path else "?"
    if note:
        path += f"{sep}note={quote(note)}"
    elif error:
        path += f"{sep}error={quote(error)}"
    return RedirectResponse(path, status_code=303)


def render(request: Request, name: str, user, status_code: int = 200, **ctx) -> HTMLResponse:
    ctx.setdefault("note", request.query_params.get("note", ""))
    ctx.setdefault("error", request.query_params.get("error", ""))
    cart_count = 0
    if user is not None:
        with db.transaction() as conn:
            cart_count = shop.get_cart(conn, user["id"]).count
    return templates.TemplateResponse(request, name, {"user": user, "cart_count": cart_count, **ctx},
                                      status_code=status_code)


# ---- pages ---------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/catalog", status_code=303)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, next: str = "/catalog"):
    return render(request, "login.html", page_user(request), next=next)


@app.post("/login", include_in_schema=False)
def login_submit(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form("/catalog")):
    try:
        with db.transaction() as conn:
            token, _ = login(conn, email, password)
    except shop.ShopError as e:
        return render(request, "login.html", None, next=next, login_error=e.message, email=email,
                      status_code=e.status)
    target = next if next.startswith("/") and not next.startswith("//") else "/catalog"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    return response


@app.post("/logout", include_in_schema=False)
def logout(request: Request):
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (request.cookies.get(SESSION_COOKIE),))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/catalog", response_class=HTMLResponse, include_in_schema=False)
async def catalog(request: Request, q: str = "", category: str = "", sort: str = "",
                  min_price: str = "", max_price: str = ""):
    await maybe_slow_search(q)
    lo = int(min_price) if min_price.isdigit() else None
    hi = int(max_price) if max_price.isdigit() else None
    with db.transaction() as conn:
        products = shop.list_products(conn, q, category, lo, hi, sort)
        cats = shop.categories(conn)
    hint = ""
    if q.strip() and len(q.strip()) < shop.MIN_SEARCH_LEN:
        hint = f"Введите не меньше {shop.MIN_SEARCH_LEN} символов для поиска"
    return render(request, "catalog.html", page_user(request), products=products, categories=cats,
                  q=q, category=category, sort=sort, min_price=min_price, max_price=max_price, hint=hint)


@app.get("/product/{product_id}", response_class=HTMLResponse, include_in_schema=False)
def product_page(request: Request, product_id: int):
    user = page_user(request)
    with db.transaction() as conn:
        try:
            product = shop.get_product(conn, product_id)
        except shop.ShopError as e:
            return render(request, "error.html", user, code=404, message=e.message, status_code=404)
        in_wishlist = bool(user and conn.execute(
            "SELECT 1 FROM wishlist WHERE user_id = ? AND product_id = ?", (user["id"], product_id)).fetchone())
    return render(request, "product.html", user, product=product, in_wishlist=in_wishlist,
                  max_qty=shop.MAX_QTY_PER_ITEM)


@app.post("/cart/add", include_in_schema=False)
def cart_add(request: Request, product_id: int = Form(...), qty: int = Form(1), back_to: str = Form("/cart")):
    user = page_user(request)
    if user is None:
        return to_login(f"/product/{product_id}")
    target = back_to if back_to.startswith("/") and not back_to.startswith("//") else "/cart"
    try:
        with db.transaction() as conn:
            note = shop.add_to_cart(conn, user["id"], product_id, qty)
    except shop.ShopError as e:
        return back(target, error=e.message)
    return back(target, note=note or "Товар добавлен в корзину")


@app.get("/cart", response_class=HTMLResponse, include_in_schema=False)
def cart_page(request: Request):
    user = page_user(request)
    if user is None:
        return to_login("/cart")
    with db.transaction() as conn:
        cart = shop.get_cart(conn, user["id"])
    return render(request, "cart.html", user, cart=cart, max_qty=shop.MAX_QTY_PER_ITEM,
                  free_from=shop.FREE_SHIPPING_FROM)


@app.post("/cart/update", include_in_schema=False)
def cart_update(request: Request, product_id: int = Form(...), qty: int = Form(...)):
    user = page_user(request)
    if user is None:
        return to_login("/cart")
    try:
        with db.transaction() as conn:
            note = shop.set_qty(conn, user["id"], product_id, qty)
    except shop.ShopError as e:
        return back("/cart", error=e.message)
    return back("/cart", note=note)


@app.post("/cart/remove", include_in_schema=False)
def cart_remove(request: Request, product_id: int = Form(...)):
    user = page_user(request)
    if user is None:
        return to_login("/cart")
    with db.transaction() as conn:
        shop.remove_from_cart(conn, user["id"], product_id)
    return back("/cart", note="Товар удалён из корзины")


@app.post("/cart/promo", include_in_schema=False)
def cart_promo(request: Request, code: str = Form("")):
    user = page_user(request)
    if user is None:
        return to_login("/cart")
    try:
        with db.transaction() as conn:
            shop.apply_promo(conn, user["id"], code)
    except shop.ShopError as e:
        return back("/cart", error=e.message)
    return back("/cart", note="Промокод применён")


@app.get("/checkout", response_class=HTMLResponse, include_in_schema=False)
def checkout_page(request: Request):
    user = page_user(request)
    if user is None:
        return to_login("/checkout")
    with db.transaction() as conn:
        cart = shop.get_cart(conn, user["id"])
    if not cart.lines:
        return back("/cart", error="Корзина пуста")
    return render(request, "checkout.html", user, cart=cart)


@app.post("/checkout", include_in_schema=False)
def checkout_submit(request: Request, address: str = Form("")):
    user = page_user(request)
    if user is None:
        return to_login("/checkout")
    try:
        with db.transaction() as conn:
            order_id = shop.place_order(conn, user, address)
    except shop.ShopError as e:
        with db.transaction() as conn:
            cart = shop.get_cart(conn, user["id"])
        return render(request, "checkout.html", user, cart=cart, error=e.message, address=address,
                      status_code=e.status)
    return RedirectResponse(f"/orders/{order_id}", status_code=303)


@app.get("/orders/{order_id}", response_class=HTMLResponse, include_in_schema=False)
def order_page(request: Request, order_id: int):
    user = page_user(request)
    if user is None:
        return to_login(f"/orders/{order_id}")
    with db.transaction() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user["id"])).fetchone()
        items = shop.order_items(conn, order_id) if order else []
    if order is None:
        return render(request, "error.html", user, code=404, message="Заказ не найден", status_code=404)
    return render(request, "order.html", user, order=order, items=items)


@app.get("/profile", response_class=HTMLResponse, include_in_schema=False)
def profile_page(request: Request):
    user = page_user(request)
    if user is None:
        return to_login("/profile")
    with db.transaction() as conn:
        orders = shop.list_orders(conn, user["id"])
    return render(request, "profile.html", user, orders=orders)


@app.get("/wishlist", response_class=HTMLResponse, include_in_schema=False)
def wishlist_page(request: Request):
    if not chaos.state.feature_wishlist:
        return render(request, "error.html", page_user(request), code=404, message="Страница не найдена",
                      status_code=404)
    user = page_user(request)
    if user is None:
        return to_login("/wishlist")
    with db.transaction() as conn:
        items = shop.get_wishlist(conn, user["id"])
    return render(request, "wishlist.html", user, items=items)


@app.post("/wishlist/toggle", include_in_schema=False)
def wishlist_toggle(request: Request, product_id: int = Form(...)):
    if not chaos.state.feature_wishlist:
        raise HTTPException(404)
    user = page_user(request)
    if user is None:
        return to_login(f"/product/{product_id}")
    with db.transaction() as conn:
        added = shop.toggle_wishlist(conn, user["id"], product_id)
    return back(f"/product/{product_id}", note="Добавлено в избранное" if added else "Удалено из избранного")


# ---- REST API ------------------------------------------------------------

class LoginIn(BaseModel):
    email: str
    password: str


class CartItemIn(BaseModel):
    product_id: int
    qty: int = 1


class QtyIn(BaseModel):
    qty: int


class PromoIn(BaseModel):
    code: str


class OrderIn(BaseModel):
    address: str


@app.exception_handler(shop.ShopError)
async def shop_error_handler(_: Request, exc: shop.ShopError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


def product_json(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "name": r["name"], "description": r["description"], "category": r["category"],
            "price": r["price"] / 100, "old_price": r["old_price"] / 100 if r["old_price"] else None,
            "stock": r["stock"]}


def cart_json(cart: shop.Cart, note: str = "") -> dict:
    return {
        "items": [{"product_id": line.product_id, "name": line.name, "price": line.price / 100,
                   "qty": line.qty, "on_sale": line.on_sale} for line in cart.lines],
        "promo": cart.promo, "promo_note": cart.promo_note,
        "subtotal": cart.subtotal / 100, "discount": cart.discount / 100,
        "shipping": cart.shipping / 100, "total": cart.total / 100, "note": note,
    }


def user_json(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}


@app.post("/api/login", tags=["auth"])
def api_login(body: LoginIn):
    with db.transaction() as conn:
        token, user = login(conn, body.email, body.password)
    return {"token": token, "user": user_json(user)}


@app.get("/api/me", tags=["auth"])
def api_me(user=Depends(api_user)):
    return user_json(user)


@app.get("/api/products", tags=["catalog"])
async def api_products(q: str = "", category: str = "", min_price: int | None = None,
                       max_price: int | None = None, sort: str = ""):
    await maybe_slow_search(q)
    with db.transaction() as conn:
        return [product_json(r) for r in shop.list_products(conn, q, category, min_price, max_price, sort)]


@app.get("/api/products/{product_id}", tags=["catalog"])
def api_product(product_id: int):
    with db.transaction() as conn:
        return product_json(shop.get_product(conn, product_id))


@app.get("/api/cart", tags=["cart"])
def api_cart(user=Depends(api_user)):
    with db.transaction() as conn:
        return cart_json(shop.get_cart(conn, user["id"]))


@app.post("/api/cart/items", tags=["cart"])
def api_cart_add(body: CartItemIn, user=Depends(api_user)):
    with db.transaction() as conn:
        note = shop.add_to_cart(conn, user["id"], body.product_id, body.qty)
        return cart_json(shop.get_cart(conn, user["id"]), note)


@app.patch("/api/cart/items/{product_id}", tags=["cart"])
def api_cart_qty(product_id: int, body: QtyIn, user=Depends(api_user)):
    with db.transaction() as conn:
        note = shop.set_qty(conn, user["id"], product_id, body.qty)
        return cart_json(shop.get_cart(conn, user["id"]), note)


@app.delete("/api/cart/items/{product_id}", tags=["cart"])
def api_cart_remove(product_id: int, user=Depends(api_user)):
    with db.transaction() as conn:
        shop.remove_from_cart(conn, user["id"], product_id)
        return cart_json(shop.get_cart(conn, user["id"]))


@app.post("/api/cart/promo", tags=["cart"])
def api_promo(body: PromoIn, user=Depends(api_user)):
    with db.transaction() as conn:
        shop.apply_promo(conn, user["id"], body.code)
        return cart_json(shop.get_cart(conn, user["id"]))


@app.delete("/api/cart/promo", tags=["cart"])
def api_promo_remove(user=Depends(api_user)):
    with db.transaction() as conn:
        shop.remove_promo(conn, user["id"])
        return cart_json(shop.get_cart(conn, user["id"]))


@app.post("/api/orders", status_code=201, tags=["orders"])
def api_order(body: OrderIn, user=Depends(api_user)):
    with db.transaction() as conn:
        return {"order_id": shop.place_order(conn, user, body.address)}


@app.get("/api/orders", tags=["orders"])
def api_orders(user=Depends(api_user)):
    with db.transaction() as conn:
        return [{"id": o["id"], "created_at": o["created_at"], "total": o["total"] / 100, "promo": o["promo"],
                 "items": [{"name": i["name"], "qty": i["qty"], "price": i["price"] / 100}
                           for i in shop.order_items(conn, o["id"])]}
                for o in shop.list_orders(conn, user["id"])]


@app.get("/api/wishlist", tags=["wishlist"])
def api_wishlist(user=Depends(api_user)):
    if not chaos.state.feature_wishlist:
        raise HTTPException(404)
    with db.transaction() as conn:
        return [product_json(r) for r in shop.get_wishlist(conn, user["id"])]


@app.post("/api/wishlist/{product_id}", tags=["wishlist"])
def api_wishlist_toggle(product_id: int, user=Depends(api_user)):
    if not chaos.state.feature_wishlist:
        raise HTTPException(404)
    with db.transaction() as conn:
        return {"in_wishlist": shop.toggle_wishlist(conn, user["id"], product_id)}


# ---- service -------------------------------------------------------------

def service_guard(x_chaos_token: str | None = Header(default=None)) -> None:
    expected = os.getenv("CHAOS_TOKEN")
    if expected and not secrets.compare_digest(x_chaos_token or "", expected):
        raise HTTPException(403, "Wrong or missing X-Chaos-Token")


@app.get("/health", tags=["service"])
def health():
    with db.transaction() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "version": app.version, "ui_version": chaos.state.ui_version}


@app.get("/__chaos", tags=["service"], dependencies=[Depends(service_guard)])
def get_chaos():
    return chaos.state.as_dict()


@app.post("/__chaos", tags=["service"], dependencies=[Depends(service_guard)])
def set_chaos(changes: dict):
    try:
        chaos.state.update(changes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return chaos.state.as_dict()


@app.post("/__reset", tags=["service"], dependencies=[Depends(service_guard)])
def reset(flags: bool = False):
    """Reload the seed data; with ``flags=true`` also reset fault flags to the environment's values."""
    db.reset()
    if flags:
        fresh = chaos.Chaos.from_env()
        chaos.state.update(fresh.as_dict())
    return {"status": "reset", "flags": chaos.state.as_dict()}


DATA_TEST = re.compile(r'data-test="([^"]+)"')


@app.get("/__crawl", tags=["service"], dependencies=[Depends(service_guard)])
async def crawl():
    """Visit every page as a dedicated user and list the data-test elements on each.

    The coverage agent compares this map with what the autotests touch. It
    reflects the current flags: UI_VERSION=2 renames elements, FEATURE_WISHLIST
    adds pages and buttons.
    """
    if chaos.state.db_down:
        raise HTTPException(503, "Database unavailable")
    transport = httpx.ASGITransport(app=app)
    pages: dict[str, list[str]] = {}
    async with httpx.AsyncClient(transport=transport, base_url="http://shoplite") as client:
        async def visit(name: str, url: str) -> None:
            html = (await client.get(url)).text
            pages[name] = sorted(set(DATA_TEST.findall(html)))

        await visit("login", "/login")
        await client.post("/login", data={"email": "crawler@example.com", "password": "crawler123"})
        with db.transaction() as conn:
            first = conn.execute("SELECT id FROM products WHERE stock > 0 ORDER BY id LIMIT 1").fetchone()["id"]
            crawler_id = conn.execute("SELECT id FROM users WHERE email = 'crawler@example.com'").fetchone()["id"]
        await visit("catalog", "/catalog")
        await visit("product", f"/product/{first}")
        await client.post("/cart/add", data={"product_id": first, "qty": 1})
        await visit("cart", "/cart")
        await visit("checkout", "/checkout")
        await visit("profile", "/profile")
        if chaos.state.feature_wishlist:
            await visit("wishlist", "/wishlist")
        with db.transaction() as conn:
            conn.execute("DELETE FROM cart_items WHERE user_id = ?", (crawler_id,))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (crawler_id,))
    return {"flags": chaos.state.as_dict(), "pages": pages}
