"""
Tool: check_return_eligibility

THE MOST IMPORTANT TOOL IN THIS SYSTEM.

Applies policy rules deterministically in Python — the LLM NEVER decides
eligibility. The LLM only receives the final verdict and communicates it.

Rule evaluation order (first matching rule wins):
  1. Cancelled order          → BLOCKED  (Section 2.6)
  2. Not yet delivered        → BLOCKED  (cannot return undelivered item)
  3. Lost in transit          → ESCALATE (Section 1.6 — not a return)
  4. 30-day window expired    → BLOCKED  (Section 2.1)
  5. Non-returnable category  → BLOCKED  (Section 2.3)
  6. Final sale + refund req  → EXCHANGE ONLY (Section 2.4)
  7. Footwear                 → NOTE ₹300 box deduction (Section 2.5)
  → ELIGIBLE
"""

from datetime import datetime, timezone
from langchain_core.tools import tool
from src.db.orders_store import get_order
from src.db.session_store import current_session_id, get_session, update_session

# Non-returnable categories per Section 2.3
NON_RETURNABLE_CATEGORIES = {
    "innerwear",
    "jewellery",
    "beauty",
    "fragrance",
    "face_masks",
    "gift_cards",
}

RETURN_WINDOW_DAYS = 30


@tool
def check_return_eligibility(order_id: str, action: str = "return") -> str:
    """
    Deterministically check whether items in an order are eligible for
    return, exchange, or refund based on policy rules.
    ALWAYS call this before calling create_return.
    Never try to determine eligibility yourself — always use this tool.

    Args:
        order_id: The order ID to check (e.g. TR-4521)
        action: One of 'return', 'exchange', or 'refund' (default: 'return')
    """
    session_id = current_session_id.get()
    session = get_session(session_id)

    # --- Auth gate ---
    if not session["authenticated"]:
        return "Please verify your identity first before checking return eligibility."

    order_id = order_id.strip().upper()
    if order_id not in session["validated_orders"]:
        return f"Order {order_id} hasn't been verified for this session. Please validate first."

    order = get_order(order_id)
    if not order:
        return "Order not found."

    today = datetime.now(timezone.utc).date()
    action = action.lower().strip()

    item_verdicts = []

    # ── RULE 1: Cancelled order (Section 2.6) ──────────────────────────────
    if order["status"] == "cancelled":
        result = (
            "❌ INELIGIBLE — Order Cancelled\n"
            "This order has been cancelled. No return can be raised against a cancelled order.\n"
            "Reference: Section 2.6\n"
            "Action: None available."
        )
        _save_verdict(session_id, order_id, eligible=False, result=result)
        return result

    # ── RULE 2: Lost in transit (Section 1.6) — check BEFORE not-delivered ──
    if order["status"] == "lost_in_transit":
        result = (
            "🚨 ESCALATION REQUIRED — Lost Parcel\n"
            "This parcel has been marked as lost by the carrier. This is a lost-parcel CLAIM, "
            "not a return request, and cannot be processed by the automated system.\n"
            "Reference: Section 1.6\n"
            "Action: Must be escalated to a human agent. Resolution within 5 business days "
            "(replacement or full refund at your choice)."
        )
        _save_verdict(session_id, order_id, eligible=False, result=result, requires_human=True)
        return result

    # ── RULE 3: Not yet delivered ───────────────────────────────────────────
    if not order.get("delivered_at"):
        status = order["status"].replace("_", " ")
        result = (
            f"❌ INELIGIBLE — Not Yet Delivered\n"
            f"Order status is '{status}'. Returns can only be initiated after delivery.\n"
            "Reference: Section 2.1 (30-day window starts from delivery date)\n"
            "Action: Please wait until the order is delivered."
        )
        _save_verdict(session_id, order_id, eligible=False, result=result)
        return result

    # ── RULE 4: 30-day window (Section 2.1) ────────────────────────────────
    delivered_date = datetime.fromisoformat(
        order["delivered_at"].replace("Z", "+00:00")
    ).date()
    days_since = (today - delivered_date).days

    if days_since > RETURN_WINDOW_DAYS:
        result = (
            f"❌ INELIGIBLE — Return Window Expired\n"
            f"Your order was delivered {days_since} days ago. "
            f"Trendly's return window is {RETURN_WINDOW_DAYS} calendar days from the delivery date.\n"
            f"Delivered on: {delivered_date}\n"
            f"Window closed on: {delivered_date.replace(day=delivered_date.day + RETURN_WINDOW_DAYS) if delivered_date.day + RETURN_WINDOW_DAYS <= 28 else 'see policy'}\n"
            "Reference: Section 2.1\n"
            "Action: Return requests after 30 days are not eligible under any circumstance."
        )
        _save_verdict(session_id, order_id, eligible=False, result=result)
        return result

    # ── Per-item evaluation ─────────────────────────────────────────────────
    all_blocked = True
    any_eligible = False

    for item in order["items"]:
        sku = item["sku"]
        name = item["name"]
        category = item.get("category", "").lower()

        # RULE 5: Non-returnable category (Section 2.3)
        if category in NON_RETURNABLE_CATEGORIES:
            item_verdicts.append(
                f"❌ {name} (SKU: {sku})\n"
                f"   INELIGIBLE — {category.title()} cannot be returned or exchanged "
                f"for hygiene/safety reasons.\n"
                f"   Reference: Section 2.3"
            )
            continue

        # RULE 6: Final sale (Section 2.4)
        if item.get("final_sale"):
            if action in ("return", "refund"):
                item_verdicts.append(
                    f"⚠️  {name} (SKU: {sku})\n"
                    f"   EXCHANGE ONLY — This item was marked Final Sale. "
                    f"No refunds or store credit are available.\n"
                    f"   Eligible action: Size exchange only (within 30-day window).\n"
                    f"   Reference: Section 2.4"
                )
                all_blocked = False
                any_eligible = True
            else:
                # action == "exchange" — allowed for final sale
                item_verdicts.append(
                    f"✅ {name} (SKU: {sku})\n"
                    f"   ELIGIBLE FOR SIZE EXCHANGE (Final Sale item).\n"
                    f"   Note: No refund available — size exchange only.\n"
                    f"   Reference: Section 2.4"
                )
                all_blocked = False
                any_eligible = True
            continue

        # RULE 7: Footwear box deduction (Section 2.5)
        if category == "footwear":
            item_verdicts.append(
                f"✅ {name} (SKU: {sku})\n"
                f"   ELIGIBLE for {action}.\n"
                f"   ⚠️  Important: Footwear must be returned in its original shoe box. "
                f"Returns without the box incur a ₹300 deduction from the refund.\n"
                f"   Reference: Section 2.5"
            )
            all_blocked = False
            any_eligible = True
            continue

        # Default: eligible
        item_verdicts.append(
            f"✅ {name} (SKU: {sku})\n"
            f"   ELIGIBLE for {action}. Item is within the 30-day window "
            f"({days_since} days since delivery) and in a returnable category."
        )
        all_blocked = False
        any_eligible = True

    # ── Build final summary ─────────────────────────────────────────────────
    verdict_text = "\n\n".join(item_verdicts)

    if any_eligible:
        summary = (
            f"RETURN/EXCHANGE ELIGIBILITY CHECK — Order {order_id}\n"
            f"{'─' * 50}\n"
            f"{verdict_text}\n\n"
            f"Days since delivery: {days_since} of {RETURN_WINDOW_DAYS} allowed\n"
            f"Payment method: {order['payment_method'].replace('_', ' ').title()}\n"
            f"Action: You may proceed with eligible items."
        )
        _save_verdict(session_id, order_id, eligible=True, result=summary)
    else:
        summary = (
            f"RETURN/EXCHANGE ELIGIBILITY CHECK — Order {order_id}\n"
            f"{'─' * 50}\n"
            f"{verdict_text}\n\n"
            "None of the items in this order are eligible."
        )
        _save_verdict(session_id, order_id, eligible=False, result=summary)

    return summary


def _save_verdict(
    session_id: str,
    order_id: str,
    eligible: bool,
    result: str,
    requires_human: bool = False,
) -> None:
    """Persist eligibility result to session so create_return can verify it was called."""
    update_session(session_id, {
        "eligibility_result": {"eligible": eligible, "result": result, "requires_human": requires_human},
        "eligibility_order_id": order_id,
    })
