"""
Input guardrail — scans user messages before they reach the agent.

Catches:
  1. Prompt injection attempts
  2. Sensitive financial data (card numbers, bank account numbers)
  3. Attempts to extract system internals

Returns a tuple: (is_safe: bool, reason: str, safe_response: str | None)
"""

import re
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    is_safe: bool
    violation_type: str | None = None
    safe_response: str | None = None


# ─── Pattern definitions ────────────────────────────────────────────────────

INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all|prior|the\s+above|your)\s+(instructions?|rules?|constraints?|guidelines?|training)",
    r"ignore\s+all\s+",
    r"you\s+are\s+now\s+",
    r"pretend\s+(you\s+are|to\s+be)",
    r"(system\s+prompt|system\s+message)",
    r"jailbreak",
    r"\bDAN\s+mode\b",
    r"forget\s+(all\s+)?(your\s+)?(instructions?|rules?|constraints?|guidelines?|training)",
    r"override\s+(policy|instructions?|rules?)",
    r"as\s+(the\s+)?(admin|administrator|developer|root)",
    r"(reveal|show|print|output|display)\s+(your\s+)?(system\s+prompt|instructions?|source\s+code)",
    r"translate\s+your\s+instructions?\s+to",
    r"what\s+are\s+your\s+(system\s+)?instructions?",
    r"do\s+anything\s+now",
    r"unlimited\s+(power|access|authority)",
    r"disregard\s+(all\s+)?(previous|prior|your)\s+",
    r"new\s+instructions?:",
]

SENSITIVE_DATA_PATTERNS = [
    # Credit/debit card numbers (any 13-16 digit sequence, with/without separators)
    r"\b(?:\d[ -]?){13,16}\b",
    # CVV
    r"\bCVV\s*[:\-]?\s*\d{3,4}\b",
    # UPI PIN
    r"\bUPI\s*PIN\s*[:\-]?\s*\d{4,6}\b",
    # IFSC code pattern
    r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
    # Bank account numbers (9-18 digits in context)
    r"(?:account\s+(?:no|number|#)\s*[:\-]?\s*)(\d{9,18})",
]

COMPILED_INJECTION = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
COMPILED_SENSITIVE = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_DATA_PATTERNS]


def check_input(message: str) -> GuardrailResult:
    """
    Check a user message for safety violations.
    Returns GuardrailResult with is_safe=False if a violation is detected.
    """
    # Check for prompt injection
    for pattern in COMPILED_INJECTION:
        if pattern.search(message):
            return GuardrailResult(
                is_safe=False,
                violation_type="prompt_injection",
                safe_response=(
                    "I'm Tara, Trendly's support assistant. "
                    "I can help you with order status, returns, exchanges, and policy questions. "
                    "How can I assist you today?"
                ),
            )

    # Check for sensitive financial data
    for pattern in COMPILED_SENSITIVE:
        if pattern.search(message):
            return GuardrailResult(
                is_safe=False,
                violation_type="sensitive_data",
                safe_response=(
                    "⚠️  Please don't share sensitive financial information in this chat. "
                    "Trendly never asks for card numbers, CVV, UPI PINs, or bank account numbers. "
                    "If you need help with a refund for a cash-on-delivery order, "
                    "our team will contact you via a secure link — not through chat."
                ),
            )

    return GuardrailResult(is_safe=True)
