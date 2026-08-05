"""
In-memory orders store.

Loads orders.json once at startup; all reads hit this in-memory dict.
Orders are read-only — they come from the evaluation harness file.
"""

import json
from typing import Optional
from src.config import ORDERS_FILE

# ─── Module-level singletons ───────────────────────────────────────────────
_orders: dict[str, dict] = {}    # order_id → order
_customers: dict[str, dict] = {} # customer_id → customer


def load_data() -> None:
    """Called once at application startup."""
    with open(ORDERS_FILE) as f:
        data = json.load(f)

    for customer in data["customers"]:
        _customers[customer["customer_id"]] = customer

    for order in data["orders"]:
        _orders[order["order_id"]] = order

    print(f"[orders_store] Loaded {len(_orders)} orders, {len(_customers)} customers.")


def get_order(order_id: str) -> Optional[dict]:
    return _orders.get(order_id.strip().upper())


def get_customer_by_id(customer_id: str) -> Optional[dict]:
    return _customers.get(customer_id)


def get_customer_by_email(email: str) -> Optional[dict]:
    email = email.strip().lower()
    for c in _customers.values():
        if c["email"].lower() == email:
            return c
    return None


def all_orders() -> list[dict]:
    return list(_orders.values())
