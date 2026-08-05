"""
Tool: lookup_order

Retrieves full order details for an authenticated customer.
Computes derived fields (delay status, days since delivery) in Python —
never asks the LLM to do date arithmetic.
"""

from datetime import datetime, timezone
from langchain_core.tools import tool
from src.db.orders_store import get_order
from src.db.session_store import current_session_id, get_session, update_session


@tool
def lookup_order(order_id: str) -> str:
    """
    Retrieve full details of a customer's order including status, items,
    tracking, and any delay/backorder information.
    Only call this AFTER validate_customer has confirmed the customer's identity.

    Args:
        order_id: The order ID to look up (e.g. TR-4521)
    """
    session_id = current_session_id.get()
    session = get_session(session_id)

    # --- Auth gate ---
    if not session["authenticated"]:
        return (
            "I need to verify your identity first before I can show order details. "
            "Please provide your order ID and registered email."
        )

    order_id = order_id.strip().upper()

    # --- Security: only allow validated orders ---
    if order_id not in session["validated_orders"]:
        return (
            f"Order {order_id} hasn't been verified for this session. "
            "Please call validate_customer with this order ID and your email first."
        )

    order = get_order(order_id)
    if not order:
        return "Order not found."

    today = datetime.now(timezone.utc).date()

    # ── Compute delivery info ───────────────────────────────────────────────
    delivered_at = None
    days_since_delivery = None
    if order.get("delivered_at"):
        delivered_at = datetime.fromisoformat(
            order["delivered_at"].replace("Z", "+00:00")
        ).date()
        days_since_delivery = (today - delivered_at).days

    is_delayed = False
    days_past_expected = None
    expected_date = None
    if order.get("expected_delivery"):
        expected_date = datetime.fromisoformat(order["expected_delivery"]).date()
        if order["status"] not in ("delivered", "cancelled") and today > expected_date:
            days_past_expected = (today - expected_date).days
            # Policy 1.5: delayed once > 3 business days past expected
            is_delayed = days_past_expected > 3

    # Store delay status in session for the store credit tool
    if is_delayed:
        update_session(session_id, {"last_looked_up_order_delayed": order_id})

    # ── Format items ────────────────────────────────────────────────────────
    item_lines = []
    for item in order["items"]:
        flags = []
        if item.get("final_sale"):
            flags.append("FINAL SALE — exchange only")
        if item["category"] in ("innerwear", "jewellery"):
            flags.append(f"NON-RETURNABLE ({item['category']})")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        shipped_str = ""
        if "shipped" in item:
            shipped_str = " ✓ Shipped" if item["shipped"] else f" ⏳ Backordered (ETA: {item.get('backorder_eta', 'TBD')})"
        item_lines.append(
            f"  • {item['name']} | SKU: {item['sku']} | Size: {item['size']} "
            f"| Qty: {item['qty']} | ₹{item['price']}{flag_str}{shipped_str}"
        )

    # ── Build response ──────────────────────────────────────────────────────
    status_display = order["status"].replace("_", " ").title()
    lines = [
        f"📦 Order {order_id} — {status_display}",
        f"Carrier: {order.get('carrier', 'N/A')}  |  Tracking: {order.get('tracking_number', 'N/A')}",
        f"Payment: {order['payment_method'].replace('_', ' ').title()}  |  Total: ₹{order['total']}",
        "",
        "Items:",
        *item_lines,
        "",
        f"Expected delivery: {expected_date or 'N/A'}",
        f"Delivered on: {delivered_at or 'Not yet delivered'}",
    ]

    if days_since_delivery is not None:
        lines.append(f"Days since delivery: {days_since_delivery}")

    # ── Special status annotations ──────────────────────────────────────────
    if is_delayed:
        lines += [
            "",
            f"⚠️  DELAYED: {days_past_expected} days past the expected delivery date.",
            "Per policy Section 1.5, this order qualifies for a ₹250 store credit on request.",
        ]

    if order["status"] == "lost_in_transit":
        lines += [
            "",
            "🚨 LOST IN TRANSIT: The carrier has marked this parcel as lost.",
            "Per Section 1.6, this is a lost-parcel claim — NOT a return.",
            "It must be handled by a human support agent.",
        ]

    if order["status"] == "cancelled":
        refund_status = order.get("refund_status", "unknown")
        lines += [
            "",
            f"❌ CANCELLED on {order.get('cancelled_at', 'N/A')}.",
            f"Refund status: {refund_status}.",
            "Per Section 2.6, no return can be raised against a cancelled order.",
        ]

    if order["status"] == "partially_shipped":
        lines += [
            "",
            "📦 PARTIAL SHIPMENT: Some items are backordered.",
            "Per Section 1.4, remaining items ship when back in stock at no extra shipping charge.",
        ]

    return "\n".join(lines)
