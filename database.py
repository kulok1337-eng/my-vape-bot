import os
import secrets
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "shop.db")

# Способы получения: ключ -> (подпись на кнопке, цена, текст в заказе)
DELIVERY = {
    "pickup": ("🏃 Самовывоз (Норильск)", 0, "Самовывоз: Норильск"),
    "norilsk": ("🚚 Доставка: Норильск", 250, "Доставка: Норильск"),
    "talnah_bus": ("🚌 До автовокзала", 75, "Доставка: Талнах (автовокзал)"),
}


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _add_column(conn, table, column, ddl):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                rating REAL DEFAULT 5.0,
                is_courier INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                name TEXT,
                description TEXT,
                price REAL,
                photo_id TEXT
            );
            CREATE TABLE IF NOT EXISTS variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                name TEXT,
                stock INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                count INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                items_text TEXT,
                total_price REAL,
                status TEXT DEFAULT 'new',
                courier_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                product_id INTEGER,
                variant_id INTEGER,
                name TEXT,
                qty INTEGER,
                price REAL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                user_id INTEGER,
                courier_id INTEGER,
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS referrals (
                referred_id INTEGER PRIMARY KEY,
                referrer_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # миграции для старой версии shop.db
        _add_column(c, "users", "ref_code", "TEXT")
        _add_column(c, "users", "referred_by", "INTEGER DEFAULT 0")
        _add_column(c, "users", "created_at", "TIMESTAMP")
        _add_column(c, "cart", "variant_id", "INTEGER DEFAULT 0")
        _add_column(c, "orders", "username", "TEXT")
        _add_column(c, "orders", "delivery_key", "TEXT")
        _add_column(c, "orders", "delivery_label", "TEXT")
        _add_column(c, "orders", "goods_total", "REAL DEFAULT 0")
        _add_column(c, "orders", "delivery_price", "REAL DEFAULT 0")
        _add_column(c, "orders", "discount", "REAL DEFAULT 0")
        _add_column(c, "orders", "balance_used", "REAL DEFAULT 0")
        _add_column(c, "orders", "notify_chat_id", "INTEGER DEFAULT 0")
        _add_column(c, "orders", "notify_msg_id", "INTEGER DEFAULT 0")
        _add_column(c, "orders", "discount_type", "TEXT")
        for cat in ["Подики", "Одноразки", "Никотиновые пластинки (вата)",
                    "Испарители", "Шайбы", "SALE", "Жижи", "Картриджи"]:
            c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))


# ---------------- ПОЛЬЗОВАТЕЛИ ----------------

def register_user(user_id, username, ref_code=None):
    """Возвращает True, если пользователь новый."""
    with db() as c:
        row = c.execute("SELECT user_id, ref_code FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
            if not row["ref_code"]:
                c.execute("UPDATE users SET ref_code=? WHERE user_id=?",
                          (secrets.token_hex(5).upper(), user_id))
            return False
        code = secrets.token_hex(5).upper()
        c.execute("INSERT INTO users (user_id, username, ref_code, created_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
                  (user_id, username, code))
        if ref_code:
            ref = c.execute("SELECT user_id FROM users WHERE ref_code=?", (ref_code,)).fetchone()
            if ref and ref["user_id"] != user_id:
                c.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref["user_id"], user_id))
                c.execute("INSERT OR IGNORE INTO referrals (referred_id, referrer_id) VALUES (?,?)",
                          (user_id, ref["user_id"]))
        return True


def get_user(user_id):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def find_user(query):
    q = str(query).strip().lstrip("@")
    with db() as c:
        if q.isdigit():
            return c.execute("SELECT * FROM users WHERE user_id=?", (int(q),)).fetchone()
        return c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (q,)).fetchone()


def get_all_user_ids():
    with db() as c:
        return [r["user_id"] for r in c.execute("SELECT user_id FROM users")]


def get_courier_ids():
    with db() as c:
        return [r["user_id"] for r in c.execute("SELECT user_id FROM users WHERE is_courier=1")]


def update_balance(user_id, amount):
    with db() as c:
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))


def set_courier(user_id, flag):
    with db() as c:
        c.execute("UPDATE users SET is_courier=? WHERE user_id=?", (flag, user_id))


# ---------------- КАТАЛОГ ----------------

def get_categories():
    with db() as c:
        return c.execute("SELECT id, name FROM categories ORDER BY id").fetchall()


def add_category(name):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))


def rename_category(cat_id, name):
    with db() as c:
        c.execute("UPDATE categories SET name=? WHERE id=?", (name, cat_id))


def delete_category(cat_id):
    with db() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM products WHERE category_id=?", (cat_id,))]
        for pid in ids:
            c.execute("DELETE FROM variants WHERE product_id=?", (pid,))
        c.execute("DELETE FROM products WHERE category_id=?", (cat_id,))
        c.execute("DELETE FROM categories WHERE id=?", (cat_id,))


def add_product(category_id, name, description, price, photo_id, variants):
    """variants: список (название, количество)"""
    with db() as c:
        cur = c.execute(
            "INSERT INTO products (category_id, name, description, price, photo_id) VALUES (?,?,?,?,?)",
            (category_id, name, description, price, photo_id))
        pid = cur.lastrowid
        for vname, stock in variants:
            c.execute("INSERT INTO variants (product_id, name, stock) VALUES (?,?,?)", (pid, vname, stock))
        return pid


def get_products(category_id):
    with db() as c:
        return c.execute("SELECT id, name, price FROM products WHERE category_id=? ORDER BY id",
                         (category_id,)).fetchall()


def get_product(product_id):
    with db() as c:
        return c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()


def get_variants(product_id):
    with db() as c:
        return c.execute("SELECT * FROM variants WHERE product_id=? ORDER BY id", (product_id,)).fetchall()


def get_variant(variant_id):
    with db() as c:
        return c.execute("SELECT * FROM variants WHERE id=?", (variant_id,)).fetchone()


def update_product_price(product_id, price):
    with db() as c:
        c.execute("UPDATE products SET price=? WHERE id=?", (price, product_id))


def upsert_variants(product_id, variants):
    """Обновляет наличие: если вариант есть — меняет остаток, иначе создаёт."""
    with db() as c:
        for vname, stock in variants:
            row = c.execute("SELECT id FROM variants WHERE product_id=? AND name=? COLLATE NOCASE",
                            (product_id, vname)).fetchone()
            if row:
                c.execute("UPDATE variants SET stock=? WHERE id=?", (stock, row["id"]))
            else:
                c.execute("INSERT INTO variants (product_id, name, stock) VALUES (?,?,?)",
                          (product_id, vname, stock))


def delete_product(product_id):
    with db() as c:
        c.execute("DELETE FROM variants WHERE product_id=?", (product_id,))
        c.execute("DELETE FROM products WHERE id=?", (product_id,))


# ---------------- КОРЗИНА ----------------

def add_to_cart(user_id, product_id, variant_id):
    """Возвращает (ok, msg)."""
    with db() as c:
        v = c.execute("SELECT stock FROM variants WHERE id=?", (variant_id,)).fetchone()
        if not v:
            return False, "Вариант не найден"
        row = c.execute("SELECT id, count FROM cart WHERE user_id=? AND product_id=? AND variant_id=?",
                        (user_id, product_id, variant_id)).fetchone()
        have = row["count"] if row else 0
        if have + 1 > v["stock"]:
            return False, "Больше нет в наличии"
        if row:
            c.execute("UPDATE cart SET count=count+1 WHERE id=?", (row["id"],))
        else:
            c.execute("INSERT INTO cart (user_id, product_id, variant_id, count) VALUES (?,?,?,1)",
                      (user_id, product_id, variant_id))
        return True, "Добавлено!"


def get_cart(user_id):
    with db() as c:
        return c.execute(
            """SELECT c.id AS cart_id, c.count, c.product_id, c.variant_id,
                      p.name AS pname, p.price, v.name AS vname, v.stock
               FROM cart c
               JOIN products p ON p.id=c.product_id
               LEFT JOIN variants v ON v.id=c.variant_id
               WHERE c.user_id=? ORDER BY c.id""", (user_id,)).fetchall()


def remove_cart_item(cart_id, user_id):
    with db() as c:
        c.execute("DELETE FROM cart WHERE id=? AND user_id=?", (cart_id, user_id))


def clear_cart(user_id):
    with db() as c:
        c.execute("DELETE FROM cart WHERE user_id=?", (user_id,))


# ---------------- РЕФЕРАЛЫ ----------------

def active_referrals(user_id):
    with db() as c:
        return c.execute("SELECT COUNT(*) n FROM referrals WHERE referrer_id=? AND status='active'",
                         (user_id,)).fetchone()["n"]


def pending_referrals(user_id):
    with db() as c:
        return c.execute("SELECT COUNT(*) n FROM referrals WHERE referrer_id=? AND status='pending'",
                         (user_id,)).fetchone()["n"]


def list_referrals(user_id):
    with db() as c:
        return c.execute(
            """SELECT r.referred_id, r.status, u.username FROM referrals r
               LEFT JOIN users u ON u.user_id=r.referred_id
               WHERE r.referrer_id=? ORDER BY r.created_at DESC""", (user_id,)).fetchall()


def get_discount(user_id):
    """(процент, тип) — 'once' для разовых 10%, 'forever' для вечных 5%."""
    n = active_referrals(user_id)
    if n >= 10:
        return 10, "once"
    if n >= 5:
        return 5, "forever"
    return 0, None


def burn_referrals_to_five(user_id):
    with db() as c:
        rows = c.execute(
            "SELECT referred_id FROM referrals WHERE referrer_id=? AND status='active' ORDER BY created_at",
            (user_id,)).fetchall()
        extra = len(rows) - 5
        for r in rows[:max(extra, 0)]:
            c.execute("UPDATE referrals SET status='burned' WHERE referred_id=?", (r["referred_id"],))


# ---------------- ЗАКАЗЫ ----------------

def create_order(user_id, username, delivery_key):
    """Создаёт заказ из корзины. Возвращает (order_id | None, ошибка | None)."""
    label, d_price, d_text = DELIVERY[delivery_key]
    items = get_cart(user_id)
    if not items:
        return None, "Корзина пуста."
    for it in items:
        if it["vname"] is None or it["count"] > it["stock"]:
            return None, f"Товара «{it['pname']}» ({it['vname']}) уже нет в нужном количестве."
    goods = sum(it["price"] * it["count"] for it in items)
    percent, dtype = get_discount(user_id)
    discount = round(goods * percent / 100)
    user = get_user(user_id)
    to_pay = goods - discount + d_price
    balance_used = min(user["balance"] or 0, to_pay)
    total = to_pay
    items_text = ", ".join(f"{it['pname']} {it['vname']}x{it['count']}" for it in items)
    with db() as c:
        cur = c.execute(
            """INSERT INTO orders (user_id, username, items_text, total_price, status, delivery_key,
                                   delivery_label, goods_total, delivery_price, discount, balance_used, discount_type)
               VALUES (?,?,?,?, 'new', ?,?,?,?,?,?,?)""",
            (user_id, username, items_text, total, delivery_key, d_text, goods, d_price,
             discount, balance_used, dtype if discount else None))
        oid = cur.lastrowid
        for it in items:
            c.execute("INSERT INTO order_items (order_id, product_id, variant_id, name, qty, price) VALUES (?,?,?,?,?,?)",
                      (oid, it["product_id"], it["variant_id"], f"{it['pname']} ({it['vname']})", it["count"], it["price"]))
            c.execute("UPDATE variants SET stock = stock - ? WHERE id=?", (it["count"], it["variant_id"]))
        if balance_used:
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (balance_used, user_id))
        c.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    if discount and dtype == "once":
        burn_referrals_to_five(user_id)
    return oid, None


def get_order(order_id):
    with db() as c:
        return c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()


def set_order_notify(order_id, chat_id, msg_id):
    with db() as c:
        c.execute("UPDATE orders SET notify_chat_id=?, notify_msg_id=? WHERE id=?", (chat_id, msg_id, order_id))


def get_orders_by_status(status, limit=50):
    with db() as c:
        return c.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()


def get_courier_orders(courier_id):
    with db() as c:
        return c.execute("SELECT * FROM orders WHERE courier_id=? AND status='in_progress' ORDER BY id DESC",
                         (courier_id,)).fetchall()


def get_user_orders(user_id, limit=20):
    with db() as c:
        return c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()


def count_user_orders(user_id):
    with db() as c:
        return c.execute("SELECT COUNT(*) n FROM orders WHERE user_id=?", (user_id,)).fetchone()["n"]


def take_order(order_id, courier_id):
    """Атомарно: возвращает True, если заказ успешно взят."""
    with db() as c:
        cur = c.execute("UPDATE orders SET status='in_progress', courier_id=? WHERE id=? AND status='new'",
                        (courier_id, order_id))
        return cur.rowcount == 1


def complete_order(order_id):
    """Выдан. Активирует реферала при первом выданном заказе."""
    with db() as c:
        cur = c.execute("UPDATE orders SET status='completed' WHERE id=? AND status='in_progress'", (order_id,))
        if cur.rowcount != 1:
            return False
        o = c.execute("SELECT user_id FROM orders WHERE id=?", (order_id,)).fetchone()
        c.execute("UPDATE referrals SET status='active' WHERE referred_id=? AND status='pending'", (o["user_id"],))
        return True


def cancel_order(order_id, refund):
    """Отмена: возвращает товар на склад; refund=True возвращает списанный с баланса остаток."""
    with db() as c:
        o = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o or o["status"] in ("cancelled", "completed"):
            return False
        for it in c.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall():
            c.execute("UPDATE variants SET stock = stock + ? WHERE id=?", (it["qty"], it["variant_id"]))
        c.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
        if refund and o["balance_used"]:
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (o["balance_used"], o["user_id"]))
        return True


# ---------------- ОТЗЫВЫ ----------------

def add_review(order_id, user_id, courier_id, rating, comment=""):
    with db() as c:
        c.execute("INSERT INTO reviews (order_id, user_id, courier_id, rating, comment) VALUES (?,?,?,?,?)",
                  (order_id, user_id, courier_id, rating, comment))
        if courier_id:
            avg = c.execute("SELECT AVG(rating) a FROM reviews WHERE courier_id=?", (courier_id,)).fetchone()["a"]
            if avg:
                c.execute("UPDATE users SET rating=? WHERE user_id=?", (round(avg, 1), courier_id))


def order_reviewed(order_id):
    with db() as c:
        return c.execute("SELECT 1 FROM reviews WHERE order_id=?", (order_id,)).fetchone() is not None


def count_reviews():
    with db() as c:
        return c.execute("SELECT COUNT(*) n FROM reviews").fetchone()["n"]


def get_review_by_index(idx):
    """idx с нуля, от новых к старым."""
    with db() as c:
        return c.execute(
            """SELECT r.id, r.rating, r.comment, r.created_at, u.username
               FROM reviews r LEFT JOIN users u ON u.user_id=r.user_id
               ORDER BY r.id DESC LIMIT 1 OFFSET ?""", (idx,)).fetchone()


def delete_review(review_id):
    with db() as c:
        c.execute("DELETE FROM reviews WHERE id=?", (review_id,))


# ---------------- СТАТИСТИКА ----------------

def get_stats(day_only=False):
    cond = " AND DATE(created_at)=DATE('now')" if day_only else ""
    with db() as c:
        r = c.execute(f"SELECT COUNT(*) n, COALESCE(SUM(total_price),0) s FROM orders WHERE status='completed'{cond}").fetchone()
        users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        new_orders = c.execute("SELECT COUNT(*) n FROM orders WHERE status='new'").fetchone()["n"]
        return r["n"], r["s"], users, new_orders


if __name__ == "__main__":
    init_db()
