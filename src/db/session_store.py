"""
In-memory session state, keyed by session_id (= LangGraph thread_id).

Tracks per-conversation context that tools need:
  - authentication status
  - validated customer identity
  - eligibility verdicts (so create_return can verify the check was done)
  - which actions have already been taken (idempotency)

Uses a contextvars.ContextVar so tools can read the session_id
without it being passed explicitly through every call chain.
"""

from contextvars import ContextVar
from typing import Optional

# Set at API request boundary; read by tools via .get()
current_session_id: ContextVar[str] = ContextVar("session_id", default="default")

# ─── In-memory store ────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}


def _default_state() -> dict:
    return {
        "authenticated": False,
        "customer_id": None,
        "customer_name": None,
        "validated_orders": [],          # list of order_ids verified this session
        "eligibility_result": None,      # last eligibility verdict
        "eligibility_order_id": None,    # which order it was for
        "return_created": False,
        "store_credit_issued_for": [],   # order_ids already credited
        "escalated": False,
        "injection_attempts": 0,
    }


def get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = _default_state()
    return _sessions[session_id]


def update_session(session_id: str, updates: dict) -> None:
    state = get_session(session_id)
    state.update(updates)


def reset_session(session_id: str) -> None:
    _sessions[session_id] = _default_state()
