"""
SQLite store for mutable data: returns, store credits.

Orders are read-only (from JSON). This DB only tracks writes.
"""

import sqlite3
import uuid
from pathlib import Path
from src.config import DB_FILE


def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS returns (
            return_id     TEXT PRIMARY KEY,
            order_id      TEXT NOT NULL,
            customer_id   TEXT NOT NULL,
            item_skus     TEXT NOT NULL,
            action_type   TEXT NOT NULL,
            reason        TEXT,
            exchange_size TEXT,
            status        TEXT DEFAULT 'created',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS store_credits (
            credit_id   TEXT PRIMARY KEY,
            order_id    TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            amount      INTEGER NOT NULL,
            reason      TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("[returns_store] DB initialized.")


def insert_return(
    order_id: str,
    customer_id: str,
    item_skus: list[str],
    action_type: str,
    reason: str,
    exchange_size: str | None = None,
) -> str:
    """Insert a new return record. Returns the generated return_id."""
    return_id = f"RET-{uuid.uuid4().hex[:6].upper()}"
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        INSERT INTO returns
            (return_id, order_id, customer_id, item_skus, action_type, reason, exchange_size)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (return_id, order_id, customer_id, ",".join(item_skus), action_type, reason, exchange_size),
    )
    conn.commit()
    conn.close()
    return return_id


def insert_store_credit(order_id: str, customer_id: str, amount: int, reason: str) -> str:
    """Log a store credit. Returns credit_id."""
    credit_id = f"CRED-{uuid.uuid4().hex[:6].upper()}"
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        INSERT INTO store_credits (credit_id, order_id, customer_id, amount, reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (credit_id, order_id, customer_id, amount, reason),
    )
    conn.commit()
    conn.close()
    return credit_id


def has_store_credit(order_id: str) -> bool:
    """Check if a store credit has already been issued for this order."""
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT 1 FROM store_credits WHERE order_id = ?", (order_id,)
    ).fetchone()
    conn.close()
    return row is not None
