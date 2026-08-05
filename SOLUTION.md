# SOLUTION.md — Architecture, Trade-offs, and Discovery Questions

*Trendly AI Support Agent · Yellow.ai FDE Screening Assignment*

---

## Architecture Summary

The agent is built as a **LangGraph ReAct agent** backed by **Google Gemini 1.5 Flash**.

```
User message
     │
     ▼
Input Guardrail (regex — blocks injection + sensitive data)
     │
     ▼
LangGraph ReAct Agent
  ├─ System prompt contains: persona + constraints + full policy text (5.8 KB)
  ├─ Tools: validate_customer → lookup_order → check_return_eligibility → create_return
  │                                                                    → escalate_to_human
  │                                                                    → request_store_credit
  ├─ Memory: MemorySaver (in-process, per thread_id = session_id)
  └─ Session state: ContextVar-based dict (auth, eligibility verdict, actions taken)
     │
     ▼
Output Guardrail (regex — blocks unauthorized offers + bank detail collection)
     │
     ▼
Response to user
```

**Key design decision — full policy injection vs. RAG:**  
The policy document is 5.8 KB / 107 lines. Gemini Flash has a 1M token context window. Injecting the full document eliminates retrieval errors entirely. RAG would be necessary only if the policy grew beyond ~50 KB.

**Key design decision — deterministic eligibility engine:**  
The `check_return_eligibility` tool is pure Python with 7 ordered rules. The LLM receives the verdict, never the raw data. This prevents the LLM from making sympathetic but incorrect eligibility decisions.

---

## Key Trade-offs

| Decision | What Was Chosen | What Was Rejected | Why |
|---|---|---|---|
| Agent framework | LangGraph `create_react_agent` | Custom StateGraph | Faster to build; still gives explicit tool use and checkpointing |
| Policy retrieval | Full injection | Chunked RAG | Policy is small; RAG adds retrieval errors |
| Eligibility | Deterministic Python | LLM judgment | LLMs approve returns out of sympathy |
| Session memory | In-process MemorySaver | Redis / PostgreSQL | Sufficient for demo; Redis is day-2 for prod |
| Guardrails | Regex patterns | LLM-based moderation | Zero latency, deterministic, not jailbreakable |
| Orders storage | In-memory dict (from JSON) | SQLite / PostgreSQL | Read-only data; no persistence needed |
| LLM provider | Gemini 1.5 Flash | OpenAI GPT-4o | Free tier, 1M context, strong tool calling |

---

## Known Limitations

1. **No real carrier tracking integration.** The agent returns the tracking number but cannot fetch live status from BlueDart/Delhivery APIs. In production, a `track_shipment()` tool would call the carrier's API.

2. **Session memory resets on server restart.** MemorySaver is in-process. For production, switch to `SqliteSaver` or Redis. The conversation history is lost if the server restarts mid-conversation.

3. **No real ticket system.** `escalate_to_human()` generates a ticket ID and returns it, but does not actually create a ticket in Zendesk, Freshdesk, or any CRM. In production, this would POST to the ticketing system's API.

4. **No authentication layer on the API.** The `/chat` endpoint has no API key requirement. In production, every request would require a JWT or API key for rate limiting and abuse prevention.

5. **Pincode serviceability not checked.** Section 5.2 mentions non-serviceable pincodes for reverse pickup. The agent currently assumes all pincodes are serviceable (the order data doesn't include pincode). This would need a pincode lookup API in production.

6. **48-hour damaged item window not independently tracked.** The agent can respond to a damaged item report and escalate, but it cannot independently detect that 48 hours have passed since delivery. It relies on the customer reporting in time.

---

## Five Discovery Questions for Trendly's Ops Team

These are the questions I would ask before building this for real.

**1. What is the actual SLA for human agent response after escalation, by priority level?**

The current system shows a rough estimate ("within 4 hours for medium priority") but this is guessed. The real SLAs determine what we tell customers, which directly affects satisfaction scores. Are these SLAs consistent across 9 AM–9 PM support hours, or do they differ for evening escalations?

**2. What statuses can appear in the orders database that are not in the current 10-record test file?**

The test file has 6 status values: `in_transit`, `delivered`, `delayed`, `lost_in_transit`, `cancelled`, `partially_shipped`. In production, are there others — e.g., `out_for_delivery`, `returned_to_origin`, `attempted_delivery`, `on_hold`? Each needs its own handling logic. An unexpected status currently falls through to a generic response, which may be incorrect.

**3. How frequently is the policy document updated, and what is the deployment process?**

If the policy changes (new category added to non-returnable list, return window extended to 45 days), the agent must be redeployed with the new policy text. Is there a content management workflow? Should the policy be fetched from a CMS at runtime rather than baked into the deployment? What is the notification process for ops when the policy changes?

**4. For COD refunds, what is the complete flow once a human agent collects bank details?**

Currently the agent escalates COD refund requests with medium priority. What happens next? Does the human agent use an internal tool to send the secure link? What is the average time from escalation to refund initiation? This affects how we set customer expectations in the escalation message ("a specialist will reach out within X hours with a secure link").

**5. What are the top 5 reasons customers currently escalate to a human that are NOT covered by the existing policy document?**

The policy document has a clause that says "if something is not covered here, offer a human agent." Understanding the most common uncovered cases would let us either expand the policy document or add specific handling for those scenarios (e.g., "can I change my delivery address after dispatch?" is covered in Section 1.7, but "can I combine two orders?" is not). Knowing the top gaps allows us to prioritize what to add.

---

*Submitted by: [Your Name] · Yellow.ai FDE Screening · August 2026*
