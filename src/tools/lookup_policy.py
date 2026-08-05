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
    return get_policy()
