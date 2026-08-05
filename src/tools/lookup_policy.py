"""
Tool: lookup_policy

Returns policy guidelines for general policy questions.
"""

from langchain_core.tools import tool
from src.policy.loader import get_policy


@tool
def lookup_policy(query: str = "") -> str:
    """
    Look up Trendly's policy rules, shipping details, return window, or category rules.
    Use this to answer general customer policy questions.

    Args:
        query: Optional policy topic (e.g. 'returns', 'shipping', 'exchange')
    """
    return (
        "TRENDLY POLICY SUMMARY:\n"
        "• Return Window: 30 calendar days from delivery date (§2.1).\n"
        "• Item Condition: Unworn, unwashed, original tags & packaging (§2.2).\n"
        "• Non-Returnable Items: Innerwear, socks, jewellery, beauty, fragrance, face masks, gift cards (§2.3).\n"
        "• Final Sale Items: Size exchange only within 30 days. No refunds (§2.4).\n"
        "• Footwear: Must include original shoe box or ₹300 box deduction applies (§2.5).\n"
        "• Refund Timelines: Prepaid/Credit Card (5-7 days), UPI (3-5 days), Store Credit (instant) (§3.1).\n"
        "• Shipping: Standard 3-5 business days across India. Free shipping over ₹1,499; ₹99 below (§1.1).\n"
        "• Delayed Orders (>3 days late): Eligible for ₹250 store credit (§1.5)."
    )

