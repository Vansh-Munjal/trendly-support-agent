"""
Tool registry — collect all tools for the agent.
Import from here to avoid circular imports.
"""

from src.tools.validate_customer import validate_customer
from src.tools.lookup_order import lookup_order
from src.tools.return_eligibility import check_return_eligibility
from src.tools.create_return import create_return
from src.tools.escalate import escalate_to_human
from src.tools.store_credit import request_store_credit

ALL_TOOLS = [
    validate_customer,
    lookup_order,
    check_return_eligibility,
    create_return,
    escalate_to_human,
    request_store_credit,
]
