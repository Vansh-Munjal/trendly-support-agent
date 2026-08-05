"""
Tool: validate_customer

MUST be called before any order information is revealed.
Verifies the customer owns the order by matching email against our records.

Security design:
- Returns identical error message for "order not found" and "email mismatch"
  to prevent account enumeration attacks.
- Never returns the stored email in output.
"""

from langchain_core.tools import tool
from src.db.orders_store import get_order, get_customer_by_id
from src.db.session_store import current_session_id, update_session


@tool
def validate_customer(order_id: str, email: str) -> str:
    """
    Verify that a customer owns the order they're asking about.
    You MUST call this before calling lookup_order or any other order tool.

    Args:
        order_id: The order ID provided by the customer (e.g. TR-4521)
        email: The customer's registered email address
    """
    session_id = current_session_id.get()

    # --- Normalise inputs ---
    order_id = order_id.strip().upper()
    email = email.strip().lower()

    # --- Basic format check ---
    if not order_id.startswith("TR-") or not order_id[3:].isdigit():
        return (
            "That doesn't look like a valid Trendly order ID. "
            "Order IDs follow the format TR-XXXX (e.g. TR-4521). "
            "Please double-check and try again."
        )

    if "@" not in email or "." not in email:
        return "That doesn't look like a valid email address. Please provide the email you registered with Trendly."

    # --- Look up order ---
    order = get_order(order_id)
    if not order:
        # Do NOT reveal whether the order ID exists
        return (
            "I wasn't able to verify your identity with those details. "
            "Please check your order ID and registered email address and try again."
        )

    # --- Verify customer email ---
    customer = get_customer_by_id(order["customer_id"])
    if not customer or customer["email"].lower() != email:
        return (
            "I wasn't able to verify your identity with those details. "
            "Please check your order ID and registered email address and try again."
        )

    # --- Success — update session ---
    session = {
        "authenticated": True,
        "customer_id": customer["customer_id"],
        "customer_name": customer["name"],
        "validated_orders": [order_id],
    }
    update_session(session_id, session)

    return (
        f"Identity verified. Welcome, {customer['name']}! "
        f"I've confirmed you're the owner of order {order_id}. "
        "How can I help you today?"
    )
