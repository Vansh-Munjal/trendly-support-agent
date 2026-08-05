"""
Tool: escalate_to_human

Transfers the conversation to a human agent with a structured handoff summary.

Mandatory escalation triggers (agent MUST call this):
  - Order status is lost_in_transit          (Section 1.6)
  - COD refund requires bank detail collection (Section 3.3)
  - Second exchange request on same item     (Section 4.4)
  - Damaged/wrong item reported              (Section 6.1)
  - Policy question not covered by document
  - Customer explicitly requests human agent
  - Prompt injection detected

The summary generated here is what the human agent reads first.
It must be concise, factual, and actionable — no fluff.
"""

import uuid
from datetime import datetime, timezone
from langchain_core.tools import tool
from src.db.orders_store import get_order
from src.db.session_store import current_session_id, get_session, update_session


@tool
def escalate_to_human(
    reason: str,
    priority: str = "medium",
    order_id: str = "",
) -> str:
    """
    Escalate this conversation to a human support agent with a full summary.
    Use this when:
    - The order is lost in transit (Section 1.6)
    - Customer needs COD refund (bank details required, Section 3.3)
    - Customer reports a damaged or incorrect item (Section 6.1)
    - Second exchange request on same item (Section 4.4)
    - Question is not covered in the policy document
    - Customer explicitly asks for a human
    - Any situation you cannot resolve safely

    Args:
        reason: Why you're escalating (be specific)
        priority: 'low', 'medium', 'high', or 'urgent'
        order_id: The relevant order ID if applicable
    """
    session_id = current_session_id.get()
    session = get_session(session_id)

    # Mark as escalated to prevent further tool calls
    update_session(session_id, {"escalated": True})

    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    priority = priority.lower()
    wait_times = {
        "low": "within 24 hours",
        "medium": "within 4 hours",
        "high": "within 1 hour",
        "urgent": "as soon as possible (within 30 minutes)",
    }
    wait_msg = wait_times.get(priority, "within 4 hours")

    # Build order context if available
    order_context = ""
    if order_id:
        order = get_order(order_id.strip().upper())
        if order:
            order_context = (
                f"\nOrder: {order_id} | Status: {order['status'].replace('_', ' ').title()}"
                f" | Payment: {order['payment_method'].replace('_', ' ').title()}"
                f" | Total: ₹{order['total']}"
            )

    # Internal summary for the human agent
    handoff_summary = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"TRENDLY SUPPORT HANDOFF\n"
        f"Ticket: {ticket_id} | Priority: {priority.upper()} | {timestamp}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Customer: {session.get('customer_name', 'Unknown')} "
        f"(ID: {session.get('customer_id', 'Not verified')})"
        f"{order_context}\n"
        f"Escalation reason: {reason}\n"
        f"Priority: {priority.upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"[Agent: Full conversation context preserved in session {session_id}]"
    )

    # Customer-facing message
    return (
        f"I've connected you with a Trendly support specialist who can help resolve this.\n\n"
        f"🎫 Ticket ID: **{ticket_id}**\n"
        f"⏱️  Expected response: {wait_msg}\n\n"
        f"Our team operates 9:00 AM – 9:00 PM IST, 7 days a week.\n"
        f"Your specialist will have the full context of our conversation, "
        f"so you won't need to repeat anything.\n\n"
        f"---\n"
        f"[INTERNAL HANDOFF NOTE]\n"
        f"{handoff_summary}"
    )
