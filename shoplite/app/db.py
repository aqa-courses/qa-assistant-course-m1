"""SQLite storage for Shoplite: schema, seed data, connection helper.

The database is recreated from the seed on start and on ``POST /__reset``,
so every test run can begin from the same known state.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.getenv("SHOPLITE_DB", Path(__file__).resolve().parent.parent / "shoplite.db"))

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'restricted', 'admin')),
    locked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    price INTEGER NOT NULL,          -- kopecks
    old_price INTEGER,               -- set for sale items
    stock INTEGER NOT NULL
);
CREATE TABLE cart_items (
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty INTEGER NOT NULL,
    PRIMARY KEY (user_id, product_id)
);
CREATE TABLE cart_promo (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    code TEXT NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    address TEXT NOT NULL,
    subtotal INTEGER NOT NULL,
    discount INTEGER NOT NULL,
    shipping INTEGER NOT NULL,
    total INTEGER NOT NULL,
    promo TEXT
);
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    qty INTEGER NOT NULL
);
CREATE TABLE wishlist (
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    PRIMARY KEY (user_id, product_id)
);
"""

# Training stand only: well-known passwords are the point.
USERS = [
    ("alice@example.com", "Алиса", "password123", "customer", 0),
    ("bob@example.com", "Борис", "password123", "customer", 0),
    ("restricted@example.com", "Ограниченный Пользователь", "password123", "restricted", 0),
    ("locked@example.com", "Заблокированный Пользователь", "password123", "customer", 1),
    ("admin@example.com", "Администратор", "admin123", "admin", 0),
    # Used by /__crawl only, so crawling never touches the test users' carts.
    ("crawler@example.com", "Краулер", "crawler123", "customer", 0),
]

# (name, description, category, price ₽, old price ₽ or None, stock)
PRODUCTS = [
    ("Механическая клавиатура", "Клавиатура с переключателями Brown, подсветка, раскладка RU/EN.", "Периферия", 6990, None, 12),
    ("Беспроводная мышь", "Тихая мышь, 4000 DPI, до 12 месяцев на одной батарейке.", "Периферия", 1990, 2490, 30),
    ("Монитор 27\"", "IPS, 2560×1440, 165 Гц.", "Мониторы", 24990, None, 4),
    ("Монитор 24\"", "IPS, 1920×1080, 75 Гц, тонкие рамки.", "Мониторы", 12990, 14990, 0),
    ("USB-C хаб", "7 портов: HDMI, 3×USB-A, USB-C PD, SD, microSD.", "Аксессуары", 2490, None, 25),
    ("Подставка для ноутбука", "Алюминиевая, регулируемая по высоте.", "Аксессуары", 1790, None, 18),
    ("Веб-камера Full HD", "1080p, автофокус, два микрофона.", "Периферия", 3490, None, 9),
    ("Наушники с шумоподавлением", "Активное шумоподавление, до 30 часов работы.", "Аудио", 9990, 12990, 6),
    ("Колонки для ПК", "Стерео 2.0, 20 Вт, регулятор громкости на корпусе.", "Аудио", 2990, None, 11),
    ("Коврик для мыши XL", "900×400 мм, прошитые края.", "Аксессуары", 990, None, 50),
    ("SSD 1 ТБ", "NVMe M.2, чтение до 3500 МБ/с.", "Комплектующие", 6490, None, 15),
    ("Оперативная память 16 ГБ", "DDR4 3200 МГц, комплект 2×8 ГБ.", "Комплектующие", 3990, None, 0),
]


def hash_password(password: str) -> str:
    return hashlib.sha256(("shoplite:" + password).encode()).hexdigest()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset() -> None:
    """Drop everything and load the seed again."""
    DB_PATH.unlink(missing_ok=True)
    with transaction() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO users (email, name, password_hash, role, locked) VALUES (?, ?, ?, ?, ?)",
            [(e, n, hash_password(p), r, lk) for e, n, p, r, lk in USERS],
        )
        conn.executemany(
            "INSERT INTO products (name, description, category, price, old_price, stock) VALUES (?, ?, ?, ?, ?, ?)",
            [(n, d, c, p * 100, op * 100 if op else None, s) for n, d, c, p, op, s in PRODUCTS],
        )
