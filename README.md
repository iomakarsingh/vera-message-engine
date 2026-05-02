# Vera AI Message Engine — magicpin Challenge

**Keywords:** `deterministic AI`, `message engine`, `growth automation`, `LLM routing`, `FastAPI`

Vera is a deterministic, context-aware message engine designed for magicpin's merchant growth assistant. It routes structured triggers into highly specific, high-compulsion WhatsApp messages while honoring category-specific voices and merchant constraints.

## 🧠 Approach & Architecture

The system is built on a **"Template First, LLM Second"** philosophy to guarantee 100% determinism while maintaining flexibility. Decisions about *what* to say and *when* to send are handled in strict Python logic, completely bypassing the LLM for structured triggers.

### Core Pipeline (The `compose()` Function)
Every tick trigger goes through a strict 5-step pipeline:

1. **Fatigue & Suppression Checks:** Verifies if the merchant is globally suppressed, fatigued from recent messages, or if the specific trigger key has already been fired.
2. **Strategy Dispatch & Scoring:** Triggers are scored based on urgency and category multipliers. The single highest-scoring trigger is selected.
3. **Template Engine (LLM Bypass):** If the trigger matches a strict Python template (e.g., `perf_spike`), the message is instantly composed deterministically. If no template exists, it falls back to the LLM (running at `temperature=0`).
4. **Validation & Fallbacks:** Output is scanned for numeric grounding and taboo words.
5. **Suppression Registration:** If successful, a 24-hour fatigue cooldown is applied to the merchant.

### Multi-turn Reply Handling
Before the LLM even sees a merchant's reply, the message passes through 4 classifiers:
- **Auto-reply Detection:** Regex patterns catch "Out of office" or "Our team will respond shortly". Repeated auto-replies escalate from `wait` to `end`.
- **Hostile Exit:** Strong opt-outs ("Stop spamming me") trigger an immediate `end` action and place a 30-day global suppression on the merchant.
- **Intent Classification:** Detects when a merchant transitions from qualifying ("what does it cost?") to commitment ("let's do it").
- **Off-topic Deflection:** Keeps the conversation anchored to business growth.

## 🛠 Tech Stack

- **Server:** FastAPI + Uvicorn (async, high-throughput)
- **Data Models:** Pydantic (strict schema validation matching the judge contract)
- **State Management:** Thread-safe, versioned in-memory dictionary.
- **LLM Abstraction:** Built-in support for OpenAI, Anthropic, Gemini, DeepSeek, and Groq via simple environment variables.

## ⚠️ Important Note: Rate Limits & The Judge Simulator

This deployment is currently configured to use **Groq** (`llama-3.3-70b-versatile`) as the LLM provider due to its extremely fast inference speeds. 

**However, there is a known limitation with Groq's Free Tier Rate Limits:**
- The free tier limits requests to roughly ~30 per minute.
- The `judge_simulator` (and the actual magicpin judge harness) sends up to 10 requests per second under heavy load (20 actions per tick).
- Under this load, the Groq API will return HTTP 429 (Too Many Requests).
- **Graceful Degradation:** When Vera encounters a 429 error (even after its exponential backoff retries), it gracefully degrades to the deterministic fallback composition (e.g., *"Hi Dr. Meera, I have an update for you..."*). 

**How to get maximum scores:**
To prevent fallback degradation and ensure the LLM generates 100% of the messages during the intense 60-minute judge evaluation, you simply need to switch the provider to one with higher rate limits (like OpenAI with funded credits, or DeepSeek). 

You can do this by simply changing the environment variables in your deployment dashboard (Render/Railway):
```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_API_KEY=sk-your-funded-openai-key
```
No code changes are required.

## 🚀 How to Run Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your environment variables:
   ```bash
   export LLM_PROVIDER=groq
   export LLM_API_KEY=gsk_your_key_here
   ```
3. Start the server:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8080
   ```

## 📊 Performance on Canonical Test Pairs

When rate limits are not exceeded (using `generate_submission.py` with 3-second pacing), Vera achieved:
- **30/30 Test Pairs Composed Successfully**
- **0 Fallbacks**
- Judge Simulator Score (sampled): **38/50 (76% - GOOD)**

*Team Vera - Built for the magicpin AI Challenge*
