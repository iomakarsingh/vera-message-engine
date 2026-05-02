"""
Vera Message Engine — FastAPI Server
Exposes the 5 endpoints required by the judge harness:
  GET  /v1/healthz
  GET  /v1/metadata
  POST /v1/context
  POST /v1/tick
  POST /v1/reply
"""

from __future__ import annotations

import os
import time
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from models import (
    ContextPushRequest, TickRequest, TickResponse, TickAction,
    ReplyRequest, ReplyResponse, HealthResponse, MetadataResponse,
)
from context_store import ContextStore
from composer import compose
from reply_handler import ReplyHandler
from suppression import SuppressionRegistry
from scoring import rank_triggers

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vera")

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Vera Message Engine", version="1.0.0")
START_TIME = time.time()

# ── Shared state ─────────────────────────────────────────────────────────────
store = ContextStore()
suppression = SuppressionRegistry()
reply_handler = ReplyHandler(store, suppression)


# ── GET /v1/healthz ──────────────────────────────────────────────────────────

@app.get("/v1/healthz")
async def healthz():
    counts = store.counts()
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts,
    }


# ── GET /v1/metadata ─────────────────────────────────────────────────────────

@app.get("/v1/metadata")
async def metadata():
    provider = os.environ.get("LLM_PROVIDER", "groq")
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o")
    return {
        "team_name": os.environ.get("TEAM_NAME", "Team Vera"),
        "team_members": [os.environ.get("TEAM_MEMBER", "Omkar Singh")],
        "model": f"{provider}/{model}",
        "approach": "Trigger-dispatched composition: 15+ trigger kinds mapped to 7 strategy families with category-specific voice rules. Deterministic LLM (temp=0) for text, rule-based routing for decisions. Auto-reply detection via pattern matching, intent classification before LLM.",
        "contact_email": os.environ.get("TEAM_EMAIL", "omkar@example.com"),
        "version": "1.0.0",
        "submitted_at": "2026-05-02T08:00:00Z",
    }


# ── POST /v1/context ─────────────────────────────────────────────────────────

@app.post("/v1/context")
async def push_context(body: ContextPushRequest):
    accepted, reason, current_version = await store.store(
        body.scope, body.context_id, body.version, body.payload
    )

    if accepted:
        logger.info(f"Context stored: {body.scope}/{body.context_id} v{body.version}")
        return JSONResponse(
            status_code=200,
            content={
                "accepted": True,
                "ack_id": f"ack_{body.context_id}_v{body.version}",
                "stored_at": datetime.now(timezone.utc).isoformat() + "Z",
            },
        )

    if reason == "stale_version":
        logger.info(f"Context stale: {body.scope}/{body.context_id} v{body.version} (current: v{current_version})")
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": current_version,
            },
        )

    # invalid_scope or other
    return JSONResponse(
        status_code=400,
        content={
            "accepted": False,
            "reason": reason or "invalid_request",
            "details": f"Scope must be one of: {', '.join(ContextStore.VALID_SCOPES)}",
        },
    )


# ── POST /v1/tick ─────────────────────────────────────────────────────────────

@app.post("/v1/tick")
async def tick(body: TickRequest):
    actions: list[dict] = []
    
    # 1. Rank all triggers by urgency and category relevance
    ranked_trigger_ids = rank_triggers(body.available_triggers, store)
    
    # 2. Track which conversations we've already messaged in this tick
    processed_convs = set()

    for trigger_id in ranked_trigger_ids:
        if len(actions) >= 20:  # Cap per spec
            break

        trigger = store.get_trigger(trigger_id)
        if not trigger:
            logger.warning(f"Trigger {trigger_id} not found in store")
            continue

        merchant_id = trigger.get("merchant_id", "")
        customer_id = trigger.get("customer_id")
        
        # Define conversation scope
        conv_key = f"{merchant_id}_{customer_id}" if customer_id else merchant_id
        
        # Only process ONE best trigger per conversation per tick
        if conv_key in processed_convs:
            continue

        merchant = store.get_merchant(merchant_id)
        if not merchant:
            continue

        category_slug = merchant.get("category_slug", "")
        category = store.get_category(category_slug)
        if not category:
            continue

        customer = store.get_customer(customer_id) if customer_id else None

        # Compose
        try:
            result = compose(category, merchant, trigger, customer, suppression)
        except Exception as e:
            logger.error(f"Compose failed for {trigger_id}: {e}")
            continue

        if result is None:
            continue  # Suppressed
            
        processed_convs.add(conv_key)

        # Build conversation ID
        conv_id = f"conv_{merchant_id}_{trigger_id}"
        if customer_id:
            conv_id = f"conv_{customer_id}_{trigger.get('kind', 'msg')}"

        # Record in reply handler for conversation continuity
        reply_handler.record_bot_send(conv_id, result.body, merchant_id, trigger_id)

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": result.send_as,
            "trigger_id": trigger_id,
            "template_name": result.template_name,
            "template_params": result.template_params,
            "body": result.body,
            "cta": result.cta,
            "suppression_key": result.suppression_key,
            "rationale": result.rationale,
        })

        logger.info(f"Action composed: {trigger_id} → {len(result.body)} chars")

    return {"actions": actions}


# ── POST /v1/reply ────────────────────────────────────────────────────────────

@app.post("/v1/reply")
async def reply(body: ReplyRequest):
    logger.info(f"Reply received: conv={body.conversation_id} turn={body.turn_number} msg='{body.message[:80]}'")

    response = reply_handler.handle_reply(
        conv_id=body.conversation_id,
        merchant_id=body.merchant_id or "",
        customer_id=body.customer_id,
        from_role=body.from_role,
        message=body.message,
        turn_number=body.turn_number,
    )

    result = {"action": response.action, "rationale": response.rationale}
    if response.body:
        result["body"] = response.body
    if response.cta:
        result["cta"] = response.cta
    if response.wait_seconds:
        result["wait_seconds"] = response.wait_seconds

    return result


# ── Optional: POST /v1/teardown ───────────────────────────────────────────────

@app.post("/v1/teardown")
async def teardown():
    """Wipe all state — called at end of test."""
    global store, suppression, reply_handler
    store = ContextStore()
    suppression = SuppressionRegistry()
    reply_handler = ReplyHandler(store, suppression)
    logger.info("State wiped via teardown")
    return {"status": "wiped"}
