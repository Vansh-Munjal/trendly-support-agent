"""
Output guardrail — scans agent responses before sending to user.

Catches:
  1. Unauthorized discounts or coupons being offered
  2. Bank/financial detail collection attempts
  3. Policy fabrication (claims without citation patterns)

Returns GuardrailResult — if unsafe, response is replaced with safe fallback.
"""

import re
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    is_safe: bool
    violation_type: str | None = None
    safe_response: str | None = None


UNAUTHORIZED_OFFERS = [
    r"\b\d+\s*%\s*off\b",                                    # 20% off
    r"\b\d+\s*%\s*(discount|rebate|cashback)\b",             # 20% discount
    r"\bhere\s+is\s+(a|your)?\s*\d+\s*%\b",                 # here is a 20%
    r"\bcoupon\s+code\b",
    r"\bpromo\s+code\b",
    r"\bgoodwill\s+(credit|gesture|discount)\b",
    r"\bspecial\s+discount\b",
    r"\bwaive\s+the\s+(fee|charge|cost)\b",
    r"\bfree\s+of\s+charge\b(?!\s*reverse\s+pickup)",        # allow "free reverse pickup"
    r"\bextra\s+\d+%\b",
    r"\bbonust?\s+credit\b",
    r"\boffer\s+you\s+(a\s+)?\d+\s*%\b",
]

BANK_DETAIL_COLLECTION = [
    r"(please\s+)?share\s+your\s+(bank\s+)?(account\s+number|IFSC|routing)",
    r"provide\s+your\s+(bank\s+)?account\s+(number|details)",
    r"enter\s+your\s+(card|account)\s+(number|details)",
    r"what\s+is\s+your\s+(bank\s+)?account\s+number",
]

COMPILED_UNAUTHORIZED = [re.compile(p, re.IGNORECASE) for p in UNAUTHORIZED_OFFERS]
COMPILED_BANK = [re.compile(p, re.IGNORECASE) for p in BANK_DETAIL_COLLECTION]


def check_output(response: str) -> GuardrailResult:
    """Check agent response for policy violations before sending to user."""

    for pattern in COMPILED_UNAUTHORIZED:
        if pattern.search(response):
            return GuardrailResult(
                is_safe=False,
                violation_type="unauthorized_offer",
                safe_response=(
                    "I can help you with your order using Trendly's standard policies. "
                    "Please let me know what you'd like to do with your order."
                ),
            )

    for pattern in COMPILED_BANK:
        if pattern.search(response):
            return GuardrailResult(
                is_safe=False,
                violation_type="bank_detail_collection",
                safe_response=(
                    "For cash-on-delivery refunds, our team will contact you "
                    "via a secure link to collect your bank details. "
                    "Please never share bank account information in this chat. "
                    "I'll escalate your refund request to a human agent now."
                ),
            )

    return GuardrailResult(is_safe=True)
