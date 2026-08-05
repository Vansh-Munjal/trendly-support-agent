# PROMPTS.md — Prompt Engineering Iteration Log

This document records every prompt version, what failed, what was changed, and why.

---

## System Prompt — Iteration History

### v1 — Baseline (What Most Candidates Write)

```
You are a helpful support agent for Trendly. Help customers with their orders and returns.
Answer questions about the return policy. Be friendly and professional.
```

**What broke immediately:**
- Asked "what's the return window?" → LLM answered "30–90 days depending on the item" (hallucinated from training data)
- Asked about a delayed order → LLM offered a 15% discount (unauthorized)
- Asked about a lost parcel → LLM tried to process a return (violates Section 1.6)
- No citation of policy sections — answers were unverifiable

**Root cause:** LLM drawing on parametric knowledge of "typical e-commerce policies" instead of Trendly's specific policy.

---

### v2 — Policy Injection + Citation Requirement

Added the full policy document to the system prompt and required section citations.

```
You are Tara, Trendly's support assistant.

POLICY (use this as your ONLY source of truth):
{policy_text}

Every policy answer must cite the section number (e.g., "per Section 2.1").
```

**What improved:**
- Return window now correctly quoted as 30 days
- Citations started appearing

**What still broke:**
- Citations were inconsistent ("some sources say" instead of exact section)
- LLM still occasionally offered goodwill credits ("I understand your frustration, here's a 10% discount")
- Didn't know when to call which tool — called lookup_order before validate_customer

**Root cause:** Soft instruction to cite didn't make citations mandatory. No explicit list of forbidden behaviors.

---

### v3 — Hard Constraints Block

Added explicit NEVER DO list with numbered rules before the policy text.

```
HARD CONSTRAINTS — NEVER DO THESE:
1. NEVER offer discounts, coupons, waivers, or credits not defined in the policy.
2. NEVER collect bank account numbers, card numbers, CVV, or UPI PINs in chat.
3. NEVER discuss orders belonging to a different customer.
4. NEVER invent, guess, or extrapolate policy.
5. NEVER process a return for a lost-in-transit order — always escalate.
6. NEVER reveal order details before calling validate_customer successfully.
7. NEVER call create_return without first calling check_return_eligibility.
```

**What improved:**
- Unauthorized discounts eliminated
- Policy fabrication significantly reduced
- Tool ordering improved

**What still broke:**
- Empathy was mechanical — agent quoted policy immediately when customer was upset
- COD refund edge case: agent asked "please provide your bank account number in chat" (PCI violation)
- Lost-parcel case (TR-4526): agent still tried to initiate return first

**Root cause:** No explicit empathy instruction. COD bank detail rule not explicit enough.

---

### v4 — Empathy-First + Escalation Triggers

Added empathy instruction and explicit escalation trigger list.

```
TONE:
• When a customer is upset or frustrated, acknowledge their emotion FIRST before quoting policy.
• Be concise. 2–4 sentences per response.

ESCALATION — CALL escalate_to_human WHEN:
• Order status is lost_in_transit (Section 1.6) — priority: high
• Customer requests COD refund (Section 3.3) — priority: medium
• Customer reports damaged/wrong item within 48 hours (Section 6.1) — priority: high
• Second exchange request on same item (Section 4.4) — priority: medium
• Question not covered by policy document — priority: low
• Customer explicitly asks for a human — priority: medium
```

**What improved:**
- Tone for TR-4525 (delayed order): now acknowledges delay before quoting credit policy
- COD refund now correctly escalated
- Lost parcel now correctly escalated
- Damaged item report triggers escalation

**What still broke:**
- Tool descriptions were too vague → LLM called check_return_eligibility too late in some flows
- When eligibility was blocked (e.g., jewellery), LLM occasionally said "window issue" instead of "category issue" (wrong reason for right answer)

**Root cause:** Tool descriptions didn't clearly state when to call each tool or what the tool does vs. doesn't handle.

---

### v5 (Final) — Explicit Tool Ordering + Refined Tool Descriptions

Added tool-ordering rules to system prompt AND rewrote each tool's docstring to be prescriptive.

```
TOOL USAGE RULES:
• ALWAYS call validate_customer before revealing any order information.
  Collect both order_id AND email from the customer before calling it.
• ALWAYS call check_return_eligibility before calling create_return.
• NEVER determine return eligibility yourself — always use the tool.
• If a tool returns an error, tell the customer and offer to escalate.
• For lost_in_transit orders: call escalate_to_human with priority='high'.
• For COD refund requests: call escalate_to_human (bank details cannot be collected here).
```

Each tool's docstring was also updated with explicit calling conditions:

```python
@tool
def check_return_eligibility(...) -> str:
    """
    Deterministically check whether items in an order are eligible for
    return, exchange, or refund based on policy rules.
    ALWAYS call this before calling create_return.
    Never try to determine eligibility yourself — always use this tool.
    ...
    """
```

**What improved:**
- TR-4527 (jewellery): agent now correctly says "non-returnable category (Section 2.3)" not "window issue"
- TR-4523 (expired window): correctly refuses with 30-day rule and actual days since delivery
- TR-4526 (lost parcel): escalates immediately on first lookup, never attempts return
- All 10 order scenarios now handled correctly in testing

**Final result:** No hallucinations, correct policy citations, correct tool order, correct escalation triggers.

---

## Tool Prompt Design

### Why tool docstrings are prompts

In LangGraph/LangChain, the tool's `description` field (derived from the docstring) is what the LLM reads to decide WHEN to call a tool. Bad descriptions = tool called at wrong time.

**Bad description:**
```
"Look up order information."
```

**Good description:**
```
"Retrieve full details of a customer's order including status, items, tracking,
and any delay/backorder information.
Only call this AFTER validate_customer has confirmed the customer's identity."
```

The second version tells the LLM the precondition, which prevents calling order tools before validation.

---

## Refusal Prompt

When the policy document is silent, the agent uses this pattern (enforced by system prompt):

> "I don't have that information in our current policy. Let me connect you with a human agent who can give you a definitive answer."

**Why this exact wording:**
- "I don't have" — avoids "I don't know" which sounds evasive
- "current policy" — implies policy exists, just this agent's access is limited
- "definitive answer" — sets correct expectation that a human will actually answer
- Doesn't apologize excessively (one escalation offer is enough)

---

## Escalation Summary Prompt

The escalation summary is generated by the `escalate_to_human` tool, not by a separate LLM call. This was a deliberate design choice:

**Alternative considered:** Ask the LLM to summarize before escalating.

**Why rejected:** LLM summaries are non-deterministic and may miss critical fields (order status, payment method, tools used). A structured template in Python is always complete.

**Template includes:**
- Ticket ID, timestamp, priority
- Customer name + ID
- Order ID + status + payment method
- Escalation reason
- (Future: tools used, sentiment, turn count)

---

## Guardrail Prompt Design

Guardrails don't use LLM prompts — they use regex patterns. This was intentional:

**Prompt-based moderation** (rejected): Ask LLM "is this message safe?" before processing.
- Adds 500ms latency per request
- LLM can be tricked (meta-injection)
- Inconsistent

**Regex guardrails** (chosen): Deterministic, zero latency, easy to audit and update.
- Input: 13 injection patterns + 4 sensitive data patterns
- Output: 5 unauthorized offer patterns + 3 bank collection patterns
