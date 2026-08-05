"""
Tool: request_store_credit

Issues the ₹250 delayed-order store credit defined in Section 1.5.

This is NOT a goodwill gesture — it is a policy-defined credit.
The tool enforces preconditions deterministically:
  - Order must have status 'delayed' OR be more than 3 days past expected delivery
  - Credit has not already been issued for this order
"""

from langchain_core.tools import tool
from datetime import datetime, timezone
from src.db.orders_store import get_order
from src.db.returns_store import insert_store_credit, has_store_credit
from src.db.session_store import current_session_id, get_session


STORE_CREDIT_AMOUNT = 250  # Defined in Section 1.5


@tool
def request_store_credit(order_id: str) -> str:
    """
    Request a ₹250 store credit for a delayed order.
    Only applicable when the order is more than 3 business days past its expected
    delivery date (policy Section 1.5). The customer does NOT need to cancel the order.

    Args:
        order_id: The delayed order ID (e.g. TR-4525)
    """
    session_id = current_session_id.get()
    session = get_session(session_id)

    if not session["authenticated"]:
        return "Please verify your identity before requesting store credit."

    order_id = order_id.strip().upper()
    if order_id not in session["validated_orders"]:
        return f"Order {order_id} hasn't been verified for this session."

    order = get_order(order_id)
    if not order:
        return "Order not found."

    today = datetime.now(timezone.utc).date()

    # --- Verify delay condition (Section 1.5) ---
    if order["status"] == "delivered":
        return (
            "This order has already been delivered, so a delayed-order store credit "
            "cannot be issued. Per Section 1.5, the credit applies to orders that "
            "are more than 3 business days past their expected delivery date."
        )

    if order["status"] == "cancelled":
        return "Store credits cannot be issued for cancelled orders."

    if not order.get("expected_delivery"):
        return "This order does not have an expected delivery date on record."

    expected = datetime.fromisoformat(order["expected_delivery"]).date()
    days_past = (today - expected).days

    if days_past <= 3:
        return (
            f"Order {order_id} is only {days_past} day(s) past its expected delivery date. "
            "The store credit applies when an order is more than 3 business days delayed "
            "(Section 1.5). Please check back if the delay continues."
        )

    # --- Check for duplicate credit ---
    if has_store_credit(order_id):
        return (
            f"A ₹{STORE_CREDIT_AMOUNT} store credit has already been issued for order {order_id}. "
            "Credits cannot be issued twice for the same order."
        )

    # --- Issue credit ---
    credit_id = insert_store_credit(
        order_id=order_id,
        customer_id=session["customer_id"],
        amount=STORE_CREDIT_AMOUNT,
        reason=f"Delayed order — {days_past} days past expected delivery (Section 1.5)",
    )

    return (
        f"✅ Store credit issued!\n\n"
        f"Credit ID: {credit_id}\n"
        f"Amount: ₹{STORE_CREDIT_AMOUNT}\n"
        f"Reason: Order {order_id} is {days_past} days past expected delivery\n"
        f"Applied to: Your Trendly account ({session.get('customer_name', 'your account')})\n\n"
        f"The credit is available immediately and will be applied automatically "
        f"on your next Trendly order. (Section 1.5)\n\n"
        f"Your delayed order is still on its way — you do not need to cancel it to receive this credit."
    )
