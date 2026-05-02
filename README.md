# Vera — Merchant AI Assistant Message Engine

## Approach

**Architecture**: Trigger-dispatched composition with deterministic LLM output.

The core `compose(category, merchant, trigger, customer?)` function maps 15+ trigger kinds to 7 strategy families, each with tailored prompt templates that inject real merchant data, category voice rules, and trigger payloads. The LLM (GPT-4o at temperature=0) generates only the message text; all routing, suppression, and validation logic is deterministic Python.

## Strategy Families

| Family | Triggers | Key Design |
|--------|----------|------------|
| Research/Compliance | `research_digest`, `regulation_change`, `cde_opportunity` | Source citation, clinical peer tone |
| Performance Signal | `perf_spike`, `perf_dip`, `seasonal_perf_dip`, `milestone_reached` | Real numbers, celebrate/reframe |
| Customer-Scoped | `recall_due`, `customer_lapsed_*`, `chronic_refill_due`, `appointment_tomorrow`, `trial_followup`, `wedding_package_followup` | Send as merchant_on_behalf, honor language pref |
| External Event | `festival_upcoming`, `ipl_match_today`, `category_seasonal`, `supply_alert` | Contrarian when data supports it |
| Competitive | `competitor_opened` | FYI tone, anchor on differentiator |
| Engagement/Dormancy | `curious_ask_due`, `dormant_with_vera`, `winback_eligible`, `renewal_due` | Low-stakes, reciprocity |
| Planning Intent | `active_planning_intent` | Draft complete artifact with tiered options |

## Multi-Turn Handling

Reply handler runs 4 classifiers *before* any LLM call:
1. **Auto-reply detector** — pattern matching on canned phrases; escalation: nudge → wait 24h → end
2. **Intent classifier** — detects commitment ("yes", "let's do it") and switches to action mode
3. **Hostile handler** — detects opt-out/abuse, exits gracefully, suppresses merchant 30 days
4. **Off-topic deflector** — politely declines out-of-scope asks, redirects

## Model Choice

**GPT-4o** at `temperature=0` — best balance of speed (<5s per call), quality, and determinism. The 25s timeout budget leaves room for one retry on transient failures.

## Tradeoffs

- **In-memory store** — sufficient for the judge harness (no restarts during test). Production would use Redis.
- **No retrieval/RAG** — all context fits in GPT-4o's context window. Digest items are injected directly into prompts.
- **Single LLM call per compose** — no chain-of-thought or multi-step reasoning. Speed over depth.
- **Deterministic routing, LLM text** — the judge scores decisions (routing) separately from writing (text). We keep routing pure Python for auditability.

## Running Locally

```bash
export LLM_API_KEY=sk-...
export LLM_PROVIDER=openai
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080
```

## Generating Submission

```bash
LLM_API_KEY=sk-... python generate_submission.py
```
