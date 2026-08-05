# Trendly AI Support Agent

**Yellow.ai · Forward Deployed Engineer Screening Assignment**

An agentic support assistant for Trendly (fashion e-commerce) that handles order lookups, return/exchange eligibility, policy Q&A, and human escalation — built with LangGraph + Gemini.

---

## Quick Start (One Command)

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd trendly-support-agent

# 2. Add your free Gemini API key
cp .env.example .env
# Edit .env → set GOOGLE_API_KEY=your_key_here
# Free key: https://aistudio.google.com/apikey

# 3. Install and run
pip install -r requirements.txt && python3 -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000** for the chat UI.  
API docs: **http://127.0.0.1:8000/docs**

---

## API Usage

```bash
# Send a message
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-001", "message": "I want to check my order TR-4521"}'
```

Response:
```json
{
  "response": "I'd be happy to help! Could you please provide your registered email address so I can verify your identity?",
  "session_id": "test-001",
  "guardrail_triggered": false
}
```

**Base URL**: `http://localhost:8000`  
**Endpoints**: `POST /chat`, `GET /health`, `GET /` (UI)

---

## What the Agent Can Do

| Capability | How It Works |
|---|---|
| Order lookup | `lookup_order()` tool — retrieves status, tracking, items |
| Policy Q&A | Full policy injected in system prompt — all answers cite sections |
| Return eligibility | Deterministic Python engine (7 rules) — LLM never guesses |
| Create returns | `create_return()` — only callable after eligibility confirmed |
| Store credit | `request_store_credit()` — ₹250 for delayed orders per §1.5 |
| Escalation | `escalate_to_human()` — structured handoff with ticket ID |
| Safety | Input + output guardrails block injections, discounts, data leakage |

---

## Test Orders (from `orders.json`)

| Order | Customer | Scenario |
|---|---|---|
| TR-4521 | ananya.rao@example.com | In transit — cannot return yet |
| TR-4522 | marcus.bell@example.com | Tee eligible, socks (innerwear) blocked |
| TR-4523 | priya.nair@example.com | **30-day window expired** |
| TR-4524 | ananya.rao@example.com | Partially shipped, backorder |
| TR-4525 | diego.ramos@example.com | **Delayed** — qualifies for ₹250 credit |
| TR-4526 | marcus.bell@example.com | **Lost in transit** — must escalate |
| TR-4527 | priya.nair@example.com | **Jewellery** — non-returnable |
| TR-4528 | diego.ramos@example.com | **Final sale** — exchange only |
| TR-4529 | ananya.rao@example.com | **Cancelled** — no return possible |
| TR-4530 | marcus.bell@example.com | ✅ Clean happy-path return |

---

## Project Structure

```
trendly-support-agent/
├── data/
│   ├── orders.json          # 10 fixed test orders (do not edit)
│   └── trendly_policy.md    # Policy — single source of truth
├── src/
│   ├── agent/
│   │   ├── graph.py         # LangGraph ReAct agent
│   │   └── prompts.py       # System prompt with full policy injection
│   ├── api/
│   │   └── main.py          # FastAPI app, /chat endpoint, guardrail integration
│   ├── db/
│   │   ├── orders_store.py  # In-memory orders (loaded from JSON)
│   │   ├── returns_store.py # SQLite returns + credits
│   │   └── session_store.py # Per-session auth state (ContextVar)
│   ├── guardrails/
│   │   ├── input_guard.py   # Injection + sensitive data detection
│   │   └── output_guard.py  # Unauthorized offer + bank detail detection
│   ├── policy/
│   │   └── loader.py        # Policy document loader
│   └── tools/
│       ├── validate_customer.py    # Identity verification (always first)
│       ├── lookup_order.py         # Order details with computed fields
│       ├── return_eligibility.py   # Deterministic 7-rule eligibility engine
│       ├── create_return.py        # Return/exchange registration
│       ├── escalate.py             # Human handoff with structured summary
│       ├── store_credit.py         # ₹250 delayed-order credit
│       └── registry.py             # Collects all tools for agent
├── static/
│   └── index.html           # Chat UI (dark mode, served at GET /)
├── requirements.txt
├── Makefile
├── PROMPTS.md
└── SOLUTION.md
```

---

## AI Usage Note

This project was built with AI assistance (Claude by Anthropic) for:
- Architecture design and code scaffolding
- Tool schema design
- Prompt engineering (see PROMPTS.md for full iteration log)

All code has been reviewed, understood, and is explainable line-by-line. The deterministic eligibility engine, guardrail patterns, and session state design were designed by the author and implemented with AI assistance. The author can modify any part of this code in a live technical interview.

---

## Requirements

- Python 3.11+
- Google Gemini API key (free tier — https://aistudio.google.com/apikey)
- No paid services required
