"""SQLite persistence for OrderPilot — conversations, messages and orders.

The schema is created on first use and seeded with a few obviously-fictional
sample orders/conversations so the admin dashboard has something to show before
you place your first simulated order.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from . import config

ORDER_STATUSES = ["new", "confirmed", "preparing", "done", "cancelled"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    channel       TEXT NOT NULL DEFAULT 'simulator',
    customer_name TEXT,
    state         TEXT NOT NULL DEFAULT 'IDLE',
    context       TEXT NOT NULL DEFAULT '{}',
    handoff       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    sender          TEXT NOT NULL,           -- 'customer' | 'bot'
    text            TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,        -- e.g. ORD-1001
    conversation_id TEXT REFERENCES conversations(id),
    customer_name   TEXT NOT NULL,
    phone           TEXT,
    address         TEXT,
    items           TEXT NOT NULL,           -- JSON list of line items
    total           REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
    channel         TEXT NOT NULL DEFAULT 'simulator',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""


def init_db(seed: bool = True) -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        already = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    if seed and not already:
        _seed()


def reset_db() -> None:
    """Drop everything and re-seed — used by the 'Reset sample data' button."""
    with connect() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS messages;"
            "DROP TABLE IF EXISTS orders;"
            "DROP TABLE IF EXISTS conversations;"
        )
    init_db(seed=True)


# --- order id allocation ------------------------------------------------------

def next_order_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT id FROM orders ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return "ORD-1001"
    last = int(row["id"].split("-")[1])
    return f"ORD-{last + 1}"


# --- conversations ------------------------------------------------------------

def get_conversation(conn: sqlite3.Connection, conv_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()


def ensure_conversation(conn: sqlite3.Connection, conv_id: str,
                        channel: str = "simulator") -> sqlite3.Row:
    row = get_conversation(conn, conv_id)
    if row is None:
        ts = _now()
        conn.execute(
            "INSERT INTO conversations (id, channel, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (conv_id, channel, ts, ts),
        )
        row = get_conversation(conn, conv_id)
    return row


def update_conversation(conn: sqlite3.Connection, conv_id: str, *,
                        state: str | None = None, context: dict | None = None,
                        customer_name: str | None = None,
                        handoff: bool | None = None) -> None:
    sets, params = ["updated_at = ?"], [_now()]
    if state is not None:
        sets.append("state = ?"); params.append(state)
    if context is not None:
        sets.append("context = ?"); params.append(json.dumps(context))
    if customer_name is not None:
        sets.append("customer_name = ?"); params.append(customer_name)
    if handoff is not None:
        sets.append("handoff = ?"); params.append(1 if handoff else 0)
    params.append(conv_id)
    conn.execute(
        f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?", params
    )


def add_message(conn: sqlite3.Connection, conv_id: str, sender: str,
                text: str) -> None:
    conn.execute(
        "INSERT INTO messages (conversation_id, sender, text, created_at) "
        "VALUES (?, ?, ?, ?)",
        (conv_id, sender, text, _now()),
    )


def get_messages(conn: sqlite3.Connection, conv_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,)
    ).fetchall()


def list_conversations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT c.*, "
        "  (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS msg_count "
        "FROM conversations c ORDER BY c.updated_at DESC"
    ).fetchall()


# --- orders -------------------------------------------------------------------

def create_order(conn: sqlite3.Connection, *, conversation_id: str,
                 customer_name: str, phone: str, address: str,
                 items: list[dict], channel: str = "simulator") -> str:
    order_id = next_order_id(conn)
    total = round(sum(i["price"] * i["qty"] for i in items), 2)
    ts = _now()
    conn.execute(
        "INSERT INTO orders (id, conversation_id, customer_name, phone, address, "
        "items, total, status, channel, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)",
        (order_id, conversation_id, customer_name, phone, address,
         json.dumps(items), total, channel, ts, ts),
    )
    return order_id


def get_order(conn: sqlite3.Connection, order_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM orders WHERE id = ?", (order_id.strip().upper(),)
    ).fetchone()


def list_orders(conn: sqlite3.Connection,
                status: str | None = None) -> list[sqlite3.Row]:
    if status and status in ORDER_STATUSES:
        return conn.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC"
    ).fetchall()


def set_order_status(conn: sqlite3.Connection, order_id: str, status: str) -> bool:
    if status not in ORDER_STATUSES:
        return False
    cur = conn.execute(
        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), order_id),
    )
    return cur.rowcount > 0


def stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT status, total, created_at FROM orders").fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    by_status = {s: 0 for s in ORDER_STATUSES}
    orders_today = 0
    revenue = 0.0
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        if r["created_at"][:10] == today:
            orders_today += 1
        if r["status"] != "cancelled":
            revenue += r["total"]
    return {
        "total_orders": len(rows),
        "orders_today": orders_today,
        "revenue": round(revenue, 2),
        "by_status": by_status,
    }


# --- demo seed data -----------------------------------------------------------

def _seed() -> None:
    """Insert a handful of clearly-fictional conversations + orders."""
    now = datetime.now(timezone.utc)

    def ago(hours: float) -> str:
        return (now - timedelta(hours=hours)).isoformat(timespec="seconds")

    samples = [
        {
            "conv": "sample-seed-1",
            "name": "Alice Example",
            "phone": "+1-555-0142",
            "address": "742 Evergreen Terrace, Springfield",
            "items": [
                {"sku": "CAP", "name": "Cappuccino", "price": 4.50, "qty": 2},
                {"sku": "CRS", "name": "Butter Croissant", "price": 3.25, "qty": 1},
            ],
            "status": "preparing",
            "hours": 1.5,
        },
        {
            "conv": "sample-seed-2",
            "name": "Bob Globex",
            "phone": "+1-555-0177",
            "address": "1 Initech Plaza, Springfield",
            "items": [
                {"sku": "CLD", "name": "Cold Brew", "price": 5.00, "qty": 1},
            ],
            "status": "done",
            "hours": 26,
        },
        {
            "conv": "sample-seed-3",
            "name": "Carol Initech",
            "phone": "+1-555-0190",
            "address": "500 Acme Road, Springfield",
            "items": [
                {"sku": "LAT", "name": "Caffè Latte", "price": 4.75, "qty": 3},
                {"sku": "MUF", "name": "Blueberry Muffin", "price": 3.50, "qty": 2},
            ],
            "status": "new",
            "hours": 0.4,
        },
    ]

    with connect() as conn:
        for s in samples:
            ts = ago(s["hours"])
            conn.execute(
                "INSERT INTO conversations (id, channel, customer_name, state, "
                "context, handoff, created_at, updated_at) "
                "VALUES (?, 'simulator', ?, 'IDLE', '{}', ?, ?, ?)",
                (s["conv"], s["name"], 1 if s["conv"] == "sample-seed-3" else 0,
                 ts, ts),
            )
            for sender, text in [
                ("customer", "hi"),
                ("bot", f"Welcome to {config.SHOP_NAME}! How can I help?"),
                ("customer", "I'd like to order"),
                ("bot", "Sure — here's our menu…"),
            ]:
                add_message(conn, s["conv"], sender, text)
            order_id = next_order_id(conn)
            total = round(sum(i["price"] * i["qty"] for i in s["items"]), 2)
            conn.execute(
                "INSERT INTO orders (id, conversation_id, customer_name, phone, "
                "address, items, total, status, channel, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'simulator', ?, ?)",
                (order_id, s["conv"], s["name"], s["phone"], s["address"],
                 json.dumps(s["items"]), total, s["status"], ts, ts),
            )
            if s["conv"] == "sample-seed-3":
                update_conversation(conn, s["conv"], handoff=True)
