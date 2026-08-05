"""
Manual ReAct agent loop — replaces LangGraph's create_react_agent.

Why we switched from create_react_agent:
  - LangGraph's prebuilt raises an internal ValueError when the LLM
    returns an empty response (happens on Groq free-tier 429 bursts).
    This error fires INSIDE LangGraph's node execution, before any
    try/except in our API code can catch it.
  - A manual loop gives us full control: we catch empty responses,
    retry cleanly, and degrade gracefully.
  - Conceptually identical: Reason → Act (call tool) → Observe (tool result)
    → Reason again. This IS ReAct, just implemented directly.

History management:
  - Stored in-process per session_id (same as MemorySaver did).
  - Trimmed to last MAX_HISTORY_MESSAGES to prevent token buildup on
    Groq's free tier (32K context limit per model).
"""

import logging
from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage,
)
from src.config import (
    GOOGLE_API_KEY, GROQ_API_KEY,
    GROQ_MODEL, GEMINI_MODEL, LLM_PROVIDER, LLM_TEMPERATURE,
)
from src.tools.registry import ALL_TOOLS
from src.agent.prompts import build_system_prompt

logger = logging.getLogger("trendly")

# Keep last N turns of history (1 turn = 1 human + 1 AI + N tool messages)
MAX_HISTORY_MESSAGES = 16
MAX_TOOL_ITERATIONS  = 8      # max tool calls per user turn

# ── In-memory message history per session ───────────────────────────────────
_histories: dict[str, list] = {}

def _get_history(session_id: str) -> list:
    return _histories.get(session_id, [])

def _save_history(session_id: str, messages: list) -> None:
    # Keep the system message (index 0) + last MAX_HISTORY_MESSAGES
    if len(messages) > MAX_HISTORY_MESSAGES + 1:
        messages = [messages[0]] + messages[-(MAX_HISTORY_MESSAGES):]
    _histories[session_id] = messages


# ── Tool map ─────────────────────────────────────────────────────────────────
_tool_map = {t.name: t for t in ALL_TOOLS}


# ── LLM construction ─────────────────────────────────────────────────────────
_llm = None

def _get_llm():
    global _llm
    if _llm is not None:
        return _llm

    provider = LLM_PROVIDER.lower()

    if provider == "groq" and GROQ_API_KEY:
        from langchain_groq import ChatGroq
        logger.info(f"[agent] Using Groq — {GROQ_MODEL}")
        _llm = ChatGroq(model=GROQ_MODEL, groq_api_key=GROQ_API_KEY,
                        temperature=LLM_TEMPERATURE)

    elif provider == "gemini" and GOOGLE_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info(f"[agent] Using Gemini — {GEMINI_MODEL}")
        _llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL,
                                      google_api_key=GOOGLE_API_KEY,
                                      temperature=LLM_TEMPERATURE)

    elif GROQ_API_KEY:
        from langchain_groq import ChatGroq
        logger.info(f"[agent] Auto-detected Groq — {GROQ_MODEL}")
        _llm = ChatGroq(model=GROQ_MODEL, groq_api_key=GROQ_API_KEY,
                        temperature=LLM_TEMPERATURE)

    elif GOOGLE_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info(f"[agent] Auto-detected Gemini — {GEMINI_MODEL}")
        _llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL,
                                      google_api_key=GOOGLE_API_KEY,
                                      temperature=LLM_TEMPERATURE)
    else:
        raise EnvironmentError(
            "No LLM API key found. Set GROQ_API_KEY or GOOGLE_API_KEY in .env\n"
            "  Groq (free): https://console.groq.com\n"
            "  Gemini (free): https://aistudio.google.com/apikey"
        )

    return _llm


def _get_llm_with_tools():
    return _get_llm().bind_tools(ALL_TOOLS)


# ── Main agent entry point ────────────────────────────────────────────────────

def run_agent(message: str, session_id: str) -> str:
    """
    Run one turn of the ReAct loop for the given session.
    Returns the agent's final text response.
    """
    llm = _get_llm_with_tools()
    system_prompt = build_system_prompt()

    # Load or initialise history
    history = _get_history(session_id)
    if not history:
        history = [SystemMessage(content=system_prompt)]

    history.append(HumanMessage(content=message))

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = None
        for retry in range(3):
            try:
                response = llm.invoke(history)
                break
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate_limit" in err_str:
                    import time
                    logger.warning(f"[{session_id}] 429 rate limit hit, retrying in 1s (attempt {retry+1}/3)...")
                    time.sleep(1)
                else:
                    logger.error(f"[{session_id}] LLM call failed (iter {iteration}): {e}")
                    break



        if not response:
            return (
                "I'm experiencing a brief interruption. "
                "Could you please repeat your message? I'm ready to help."
            )


        # Empty content AND no tool calls → graceful retry message
        if not response.content and not getattr(response, "tool_calls", None):
            logger.warning(f"[{session_id}] LLM returned empty output on iteration {iteration}")
            return (
                "I didn't quite catch that. Could you please repeat your request?"
            )

        history.append(response)

        # ── No tool calls → final text response ────────────────────────────
        if not getattr(response, "tool_calls", None):
            _save_history(session_id, history)
            return response.content

        # ── Execute each tool call ──────────────────────────────────────────
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args  = tool_call.get("args", {})
            call_id    = tool_call.get("id", tool_name)

            logger.info(f"[{session_id}] Tool call: {tool_name}({tool_args})")

            if tool_name in _tool_map:
                try:
                    result = _tool_map[tool_name].invoke(tool_args)
                    result_str = str(result)
                except Exception as e:
                    result_str = f"Tool '{tool_name}' encountered an error: {e}"
                    logger.error(f"[{session_id}] Tool error — {tool_name}: {e}")
            else:
                result_str = f"Unknown tool: {tool_name}"

            logger.info(f"[{session_id}] Tool result: {result_str[:100]}...")
            history.append(ToolMessage(content=result_str, tool_call_id=call_id))

    # Exceeded max iterations
    _save_history(session_id, history)
    return (
        "I wasn't able to complete all the steps needed to answer your request. "
        "Let me connect you with a human agent who can help directly."
    )


def warmup() -> None:
    """Called at startup to initialise the LLM client."""
    _get_llm()
    logger.info(f"[agent] Manual ReAct loop ready with {len(ALL_TOOLS)} tools.")
