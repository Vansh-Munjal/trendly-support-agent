"""
Tool: create_return

Registers a return or exchange request in SQLite.
Guardrail: Refuses to execute if check_return_eligibility was not called
first in this session, preventing the LLM from bypassing the policy engine.
"""

import uuid
from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool
from src.db.returns_store import insert_return
from src.db.orders_store import get_order
from src.db.session_store import current_session_id, get_session, update_session


REFUND_TIMELINES = {
    "credit_card":    "5–7 business days to your original card",
    "prepaid_card":   "5–7 business days to your original card",
    "upi":            "3–5 business days to your original UPI ID",
    "cash_on_delivery": (
        "7–10 business days via bank transfer or store credit. "
        "A human agent will contact you via a secure link to collect bank details."
    ),
    "store_credit":   "immediately as store credit",
}


@tool
def create_return(
    order_id: str,
    action_type: str,
    reason: str,
    item_skus: str = "all",
    exchange_size: str = "",
) -> str:
    """
    Create a return or exchange request for eligible items.
    You MUST call check_return_eligibility before this tool and confirm the
    eligibility result shows items are eligible.

    Args:
        order_id: The order ID (e.g. TR-4521)
        action_type: Either 'return' or 'exchange'
        reason: Customer's reason for the return/exchange
        item_skus: Comma-separated SKUs to return (e.g. 'TR-TSH-002') or 'all' for all items
        exchange_size: Required if action_type is 'exchange' (e.g. 'XL')
    """
    session_id = current_session_id.get()
    session = get_session(session_id)

    # --- Auth gate ---
    if not session["authenticated"]:
        return "Please verify your identity before creating a return."

    order_id = order_id.strip().upper()

    # --- Eligibility gate: MUST have called check_return_eligibility first ---
    elig = session.get("eligibility_result")
    elig_order = session.get("eligibility_order_id")

    if not elig:
        return (
            "I need to check return eligibility before creating a return request. "
            "Please call check_return_eligibility first."
        )

    if elig_order != order_id:
        return (
            f"The eligibility check was done for order {elig_order}, "
            f"but you're trying to create a return for order {order_id}. "
            "Please run check_return_eligibility for the correct order first."
        )

    if not elig["eligible"]:
        return (
            "The eligibility check showed this order is not eligible for a return. "
            "No return request will be created.\n\n"
            f"Reason: {elig['result']}"
        )

    if elig.get("requires_human"):
        return (
            "This case requires human escalation and cannot be processed automatically. "
            "Please use escalate_to_human instead."
        )

    # --- Validate action_type ---
    action_type = action_type.lower().strip()
    if action_type not in ("return", "exchange"):
        return "action_type must be either 'return' or 'exchange'."

    if action_type == "exchange" and not exchange_size:
        return "Please provide the exchange_size when requesting an exchange (e.g. 'XL', '32')."

    # --- Resolve SKUs ---
    order = get_order(order_id)
    all_skus = [item["sku"] for item in order["items"]]

    if item_skus.strip().lower() == "all":
        skus_to_return = all_skus
    else:
        skus_to_return = [s.strip().upper() for s in item_skus.split(",")]
        invalid = [s for s in skus_to_return if s not in all_skus]
        if invalid:
            return f"These SKUs were not found in order {order_id}: {', '.join(invalid)}. Valid SKUs: {', '.join(all_skus)}"

    # --- Insert into DB ---
    return_id = insert_return(
        order_id=order_id,
        customer_id=session["customer_id"],
        item_skus=skus_to_return,
        action_type=action_type,
        reason=reason,
        exchange_size=exchange_size if action_type == "exchange" else None,
    )

    # --- Mark as done in session ---
    update_session(session_id, {"return_created": True})

    # --- Payment method → refund timeline ---
    payment_method = order.get("payment_method", "credit_card")
    timeline = REFUND_TIMELINES.get(payment_method, "5–7 business days")

    # COD needs special note
    cod_note = ""
    if payment_method == "cash_on_delivery":
        cod_note = (
            "\n\n⚠️  Cash-on-Delivery Refund: A Trendly agent will contact you "
            "via a secure link to collect your bank details. "
            "Please never share bank details in this chat."
        )

    action_label = "Return" if action_type == "return" else f"Exchange (for size {exchange_size})"

    return (
        f"✅ {action_label} request created!\n\n"
        f"Return ID: {return_id}\n"
        f"Order: {order_id}\n"
        f"Items: {', '.join(skus_to_return)}\n"
        f"Reason: {reason}\n\n"
        f"Next steps:\n"
        f"• Free reverse pickup will be scheduled to your delivery address.\n"
        f"• The carrier will attempt pickup up to 2 times (Section 5.1).\n"
        f"• Once received and inspected (2–3 business days), "
        f"{'your refund' if action_type == 'return' else 'your exchange'} will be processed.\n"
        f"• Refund timeline: {timeline} (Section 3.1)."
        f"{cod_note}\n\n"
        f"Please keep items unworn, unwashed, with original tags and packaging (Section 2.2)."
    )
