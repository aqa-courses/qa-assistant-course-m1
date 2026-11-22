"""Business rules of Shoplite.

Some rules look like bugs but are intended. They are described in the
product documentation the course's triage agent reads, so that "works as
designed" has a source to quote:

* at most ``MAX_QTY_PER_ITEM`` units of one product in the cart;
* SAVE10 does not apply to sale items (those with ``old_price``);
* one promo code at a time: a new code replaces the previous one;
* search looks at product names only and needs at least 2 characters;
* shipping is free from ``FREE_SHIPPING_FROM``;
* restricted accounts can fill the cart but cannot check out.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import chaos

MAX_QTY_PER_ITEM = 5
FREE_SHIPPING_FROM = 5000_00
SHIPPING_COST = 299_00
MIN_SEARCH_LEN = 2

PROMOS = {
    "SAVE10": "Скидка 10% на товары без скидки",
    "WELCOME500": "500 ₽ на заказ от 3000 ₽",
}


class ShopError(Exception):
    """A rule was broken; the message is shown to the user as is."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def rub(kopecks: int) -> str:
    rubles = kopecks // 100
    return f"{rubles:,}".replace(",", " ") + " ₽"


# ---- catalog -------------------------------------------------------------

def list_products(conn: sqlite3.Connection, query: str = "", category: str = "",
                  min_price: int | None = None, max_price: int | None = None,
                  sort: str = "") -> list[sqlite3.Row]:
    sql = "SELECT * FROM products WHERE 1=1"
    params: list = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if min_price is not None:
        sql += " AND price >= ?"
        params.append(min_price * 100)
    if max_price is not None:
        sql += " AND price <= ?"
        params.append(max_price * 100)
    order = {"price_asc": "price ASC", "price_desc": "price DESC", "name": "name ASC"}.get(sort, "id ASC")
    rows = conn.execute(f"{sql} ORDER BY {order}", params).fetchall()
    # Name match in Python: SQLite's lower() folds ASCII only, not Cyrillic.
    query = query.strip()
    if len(query) >= MIN_SEARCH_LEN:
        q = query.casefold()
        rows = [r for r in rows if q in r["name"].casefold()]
    return rows


def categories(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT category FROM products ORDER BY category")]


def get_product(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise ShopError("Товар не найден", 404)
    return row


# ---- cart ----------------------------------------------------------------

@dataclass
class CartLine:
    product_id: int
    name: str
    price: int
    qty: int
    on_sale: bool

    @property
    def amount(self) -> int:
        return self.price * self.qty


@dataclass
class Cart:
    lines: list[CartLine] = field(default_factory=list)
    promo: str | None = None
    subtotal: int = 0
    discount: int = 0
    shipping: int = 0
    total: int = 0
    promo_note: str = ""

    @property
    def count(self) -> int:
        return sum(line.qty for line in self.lines)


def add_to_cart(conn: sqlite3.Connection, user_id: int, product_id: int, qty: int = 1) -> str:
    """Add ``qty`` units. Returns a note for the user ('' when nothing to say)."""
    if qty < 1:
        raise ShopError("Количество должно быть не меньше 1")
    product = get_product(conn, product_id)
    if product["stock"] <= 0:
        raise ShopError("Товара нет в наличии")
    row = conn.execute("SELECT qty FROM cart_items WHERE user_id = ? AND product_id = ?",
                       (user_id, product_id)).fetchone()
    current = row["qty"] if row else 0
    wanted = current + qty
    limit = min(MAX_QTY_PER_ITEM, product["stock"])
    new_qty = min(wanted, limit)
    conn.execute(
        "INSERT INTO cart_items (user_id, product_id, qty) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, product_id) DO UPDATE SET qty = excluded.qty",
        (user_id, product_id, new_qty),
    )
    if new_qty < wanted:
        return f"В корзину можно положить не больше {limit} шт. этого товара"
    return ""


def set_qty(conn: sqlite3.Connection, user_id: int, product_id: int, qty: int) -> str:
    if qty <= 0:
        remove_from_cart(conn, user_id, product_id)
        return ""
    conn.execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?", (user_id, product_id))
    return add_to_cart(conn, user_id, product_id, qty)


def remove_from_cart(conn: sqlite3.Connection, user_id: int, product_id: int) -> None:
    conn.execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?", (user_id, product_id))


def apply_promo(conn: sqlite3.Connection, user_id: int, code: str) -> None:
    code = code.strip().upper()
    if code not in PROMOS:
        raise ShopError("Промокод не найден")
    conn.execute(
        "INSERT INTO cart_promo (user_id, code) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET code = excluded.code",
        (user_id, code),
    )


def remove_promo(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("DELETE FROM cart_promo WHERE user_id = ?", (user_id,))


def get_cart(conn: sqlite3.Connection, user_id: int) -> Cart:
    rows = conn.execute(
        "SELECT p.id, p.name, p.price, p.old_price, c.qty FROM cart_items c "
        "JOIN products p ON p.id = c.product_id WHERE c.user_id = ? ORDER BY p.id",
        (user_id,),
    ).fetchall()
    cart = Cart(lines=[CartLine(r["id"], r["name"], r["price"], r["qty"], r["old_price"] is not None)
                       for r in rows])
    promo = conn.execute("SELECT code FROM cart_promo WHERE user_id = ?", (user_id,)).fetchone()
    cart.promo = promo["code"] if promo else None
    cart.subtotal = sum(line.amount for line in cart.lines)

    if cart.promo == "SAVE10":
        eligible = sum(line.amount for line in cart.lines if not line.on_sale)
        cart.discount = eligible // 10
        if cart.lines and eligible == 0:
            cart.promo_note = "SAVE10 не действует на товары со скидкой"
    elif cart.promo == "WELCOME500":
        if cart.subtotal >= 3000_00:
            cart.discount = 500_00
        else:
            cart.promo_note = "WELCOME500 действует на заказ от 3 000 ₽"

    after_discount = cart.subtotal - cart.discount
    cart.shipping = 0 if not cart.lines or after_discount >= FREE_SHIPPING_FROM else SHIPPING_COST
    if chaos.state.bug_cart_total:
        # Seeded product bug: the discount is shown but not subtracted.
        cart.total = cart.subtotal + cart.shipping
    else:
        cart.total = after_discount + cart.shipping
    return cart


# ---- orders --------------------------------------------------------------

def place_order(conn: sqlite3.Connection, user: sqlite3.Row, address: str) -> int:
    if user["role"] == "restricted":
        raise ShopError("Оформление заказа недоступно для вашей учётной записи", 403)
    address = address.strip()
    if len(address) < 10:
        raise ShopError("Укажите адрес доставки полностью: город, улица, дом")
    cart = get_cart(conn, user["id"])
    if not cart.lines:
        raise ShopError("Корзина пуста")
    for line in cart.lines:
        stock = conn.execute("SELECT stock FROM products WHERE id = ?", (line.product_id,)).fetchone()["stock"]
        if stock < line.qty:
            raise ShopError(f"«{line.name}»: на складе осталось {stock} шт.")
    cur = conn.execute(
        "INSERT INTO orders (user_id, address, subtotal, discount, shipping, total, promo) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user["id"], address, cart.subtotal, cart.discount, cart.shipping, cart.total, cart.promo),
    )
    order_id = cur.lastrowid
    for line in cart.lines:
        conn.execute("INSERT INTO order_items (order_id, product_id, name, price, qty) VALUES (?, ?, ?, ?, ?)",
                     (order_id, line.product_id, line.name, line.price, line.qty))
        conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (line.qty, line.product_id))
    conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user["id"],))
    conn.execute("DELETE FROM cart_promo WHERE user_id = ?", (user["id"],))
    return order_id


def list_orders(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()


def order_items(conn: sqlite3.Connection, order_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()


# ---- wishlist (FEATURE_WISHLIST) -----------------------------------------

def toggle_wishlist(conn: sqlite3.Connection, user_id: int, product_id: int) -> bool:
    get_product(conn, product_id)
    exists = conn.execute("SELECT 1 FROM wishlist WHERE user_id = ? AND product_id = ?",
                          (user_id, product_id)).fetchone()
    if exists:
        conn.execute("DELETE FROM wishlist WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        return False
    conn.execute("INSERT INTO wishlist (user_id, product_id) VALUES (?, ?)", (user_id, product_id))
    return True


def get_wishlist(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT p.* FROM wishlist w JOIN products p ON p.id = w.product_id "
                        "WHERE w.user_id = ? ORDER BY p.name", (user_id,)).fetchall()
