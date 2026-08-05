"""
Policy loader.

The policy document (5.8 KB, 107 lines) is small enough to inject in full
into every LLM context. This is more reliable than chunked RAG because it
eliminates retrieval errors entirely.
"""

from src.config import POLICY_FILE

_policy_text: str = ""


def load_policy() -> str:
    global _policy_text
    with open(POLICY_FILE, encoding="utf-8") as f:
        _policy_text = f.read()
    print(f"[policy_loader] Loaded policy ({len(_policy_text)} bytes).")
    return _policy_text


def get_policy() -> str:
    """Return the policy text, loading from disk if needed."""
    if not _policy_text:
        load_policy()
    return _policy_text
