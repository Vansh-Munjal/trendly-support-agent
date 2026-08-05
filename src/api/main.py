"""
FastAPI application — single entry point for all HTTP traffic.

Endpoints:
  POST /chat      — Main conversational endpoint
  GET  /health    — Liveness probe
  GET  /          — Chat UI (served from static/index.html)

Session lifecycle:
  - session_id is set by the caller (UUID recommended)
  - LangGraph MemorySaver stores full conversation history per session_id
  - Session state (auth, eligibility) stored in memory per session_id

Guardrails:
  - Input guardrail runs before the agent
  - Output guardrail runs before the response is returned
"""

import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.db.orders_store import load_data
from src.db.returns_store import init_db
from src.policy.loader import load_policy
from src.agent.graph import run_agent, warmup
from src.guardrails.input_guard import check_input
from src.guardrails.output_guard import check_output
from src.db.session_store import current_session_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trendly")


# ─── Startup / Shutdown ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Trendly Support Agent...")
    load_data()          # Load orders.json into memory
    init_db()            # Create SQLite tables
    load_policy()        # Load policy.md into memory
    warmup()             # Initialise LLM client
    logger.info("Startup complete. API ready.")
    yield
    logger.info("Shutting down.")


# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Trendly AI Support Agent",
    description="Agentic support assistant for Trendly fashion — order status, returns, policy Q&A.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ─── Schemas ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User's message")
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Session ID. Use a stable UUID per conversation.",
    )


class ChatResponse(BaseModel):
    response: str
    session_id: str
    guardrail_triggered: bool = False


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "trendly-support-agent"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id
    message = req.message.strip()

    logger.info(f"[{session_id}] User: {message[:80]}...")

    # ── Input guardrail ─────────────────────────────────────────────────────
    input_check = check_input(message)
    if not input_check.is_safe:
        logger.warning(f"[{session_id}] Input guardrail triggered: {input_check.violation_type}")
        return ChatResponse(
            response=input_check.safe_response,
            session_id=session_id,
            guardrail_triggered=True,
        )

    # ── Set session context for tools ───────────────────────────────────────
    token = current_session_id.set(session_id)

    try:
        response_text = run_agent(message, session_id)

        # ── Output guardrail ─────────────────────────────────────────────────
        output_check = check_output(response_text)
        if not output_check.is_safe:
            logger.warning(f"[{session_id}] Output guardrail triggered: {output_check.violation_type}")
            response_text = output_check.safe_response
            guardrail_hit = True
        else:
            guardrail_hit = False

        logger.info(f"[{session_id}] Agent: {response_text[:80]}...")

        return ChatResponse(
            response=response_text,
            session_id=session_id,
            guardrail_triggered=guardrail_hit,
        )

    except Exception as e:
        logger.error(f"[{session_id}] Agent error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Something went wrong on our end.",
                "message": (
                    "I'm having trouble processing your request right now. "
                    "Please try again in a moment, or contact Trendly support directly."
                ),
            },
        )
    finally:
        current_session_id.reset(token)
