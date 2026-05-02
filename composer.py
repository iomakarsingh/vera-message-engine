"""
Core compose() function — the heart of Vera's message engine.
Takes (category, merchant, trigger, customer?) and returns ComposedMessage.
"""

from __future__ import annotations

import json
import re
import logging
import time
from typing import Optional

from models import ComposedMessage
from llm_client import LLMClient
from category_voice import validate_taboos, get_salutation, get_language_instruction
from prompt_templates import build_prompt
from suppression import SuppressionRegistry

logger = logging.getLogger(__name__)

# Singleton LLM client — initialized lazily
_llm: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


from templates import try_template

def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
    suppression: Optional[SuppressionRegistry] = None,
) -> Optional[ComposedMessage]:
    """
    Compose a WhatsApp message from the 4 contexts.

    Returns ComposedMessage or None if the message should be suppressed.
    """
    trigger_kind = trigger.get("kind", "")
    suppression_key = trigger.get("suppression_key", "")
    merchant_id = trigger.get("merchant_id", merchant.get("merchant_id", ""))

    # ── Step 1: Pre-flight checks ────────────────────────────────────────
    if suppression:
        if suppression.is_merchant_suppressed(merchant_id):
            logger.info(f"Merchant {merchant_id} is globally suppressed, skipping")
            return None
        
        # Check Fatigue
        # Allow high urgency triggers (like supply_alert) to bypass fatigue
        if trigger.get("urgency") != "high" and suppression.is_merchant_fatigued(merchant_id):
            logger.info(f"Merchant {merchant_id} is fatigued, skipping {trigger_kind}")
            return None

        if suppression_key and suppression.is_suppressed(suppression_key):
            logger.info(f"Suppression key {suppression_key} is active, skipping")
            return None

    # ── Step 2: Template Engine (LLM Bypass) ─────────────────────────────
    template_match = try_template(category, merchant, trigger, customer)
    if template_match:
        logger.info(f"Template matched for {trigger_kind}. Bypassing LLM.")
        if suppression and suppression_key:
            suppression.suppress(suppression_key, trigger_kind)
            suppression.suppress_merchant_fatigue(merchant_id)
        return template_match

    # ── Step 3: Build prompt via trigger dispatch ────────────────────────
    system_prompt, user_prompt = build_prompt(category, merchant, trigger, customer)

    # ── Step 3: LLM call ─────────────────────────────────────────────────
    try:
        llm = get_llm()
        raw_response = llm.complete(system_prompt, user_prompt, max_retries=2)
        result = _parse_llm_response(raw_response, trigger, customer)
        # Rate-limit buffer for providers like Groq
        time.sleep(0.5)
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        result = _fallback_compose(category, merchant, trigger, customer)

    # ── Step 4: Validation ───────────────────────────────────────────────
    violations = validate_taboos(result.body, category)
    if violations:
        logger.warning(f"Taboo violations found: {violations}. Re-prompting.")
        try:
            fix_prompt = (
                f"Your previous message contained forbidden vocabulary: {violations}. "
                f"Rewrite the message WITHOUT these words/phrases. Keep everything else the same.\n\n"
                f"Previous message: {result.body}"
            )
            raw_fix = get_llm().complete(system_prompt, fix_prompt)
            result = _parse_llm_response(raw_fix, trigger, customer)
        except Exception:
            pass  # Keep the original if re-prompt fails

    # Numeric Grounding Enforcement
    if not re.search(r'\d+', result.body):
        logger.warning("No numbers found in composed message. Re-prompting for numeric grounding.")
        try:
            num_prompt = (
                f"Your previous message completely failed to include any specific numbers. "
                f"You MUST rewrite it to include at least one concrete number (e.g. %, ₹, dates) "
                f"from the context payload. \n\n"
                f"Previous message: {result.body}"
            )
            raw_num_fix = get_llm().complete(system_prompt, num_prompt)
            result = _parse_llm_response(raw_num_fix, trigger, customer)
        except Exception:
            pass

    # Ensure send_as is correct for customer-scoped triggers
    if customer and trigger.get("scope") == "customer":
        result.send_as = "merchant_on_behalf"

    # Set suppression key from trigger
    result.suppression_key = suppression_key

    # Build template params
    sal = get_salutation(merchant, category)
    result.template_name = f"vera_{trigger_kind}_v1"
    result.template_params = _build_template_params(result.body, sal)

    # ── Step 5: Register suppression ─────────────────────────────────────
    if suppression and suppression_key:
        suppression.suppress(suppression_key, trigger_kind)
        suppression.suppress_merchant_fatigue(merchant_id)

    return result


from models import ComposedMessage, CTAEnum

def _parse_llm_response(raw: str, trigger: dict, customer: Optional[dict]) -> ComposedMessage:
    """Parse structured JSON from LLM response."""
    # Try to find JSON block
    json_match = re.search(r'\{[\s\S]*\}', raw)
    body = raw.strip()
    cta_str = "open_ended"
    rationale = "LLM response parsing failed — using raw text"
    
    if json_match:
        try:
            data = json.loads(json_match.group())
            body = data.get("body", raw)
            cta_str = data.get("cta", "open_ended")
            rationale = data.get("rationale", "")
        except json.JSONDecodeError:
            pass

    # Normalize CTA
    valid_ctas = {e.value for e in CTAEnum}
    if cta_str not in valid_ctas:
        cta_str = CTAEnum.OPEN_ENDED.value

    return ComposedMessage(
        body=body,
        cta=CTAEnum(cta_str),
        send_as="merchant_on_behalf" if customer else "vera",
        suppression_key=trigger.get("suppression_key", ""),
        rationale=rationale,
    )


def _fallback_compose(
    category: dict, merchant: dict, trigger: dict, customer: Optional[dict]
) -> ComposedMessage:
    """Deterministic fallback when LLM is unavailable."""
    identity = merchant.get("identity", {})
    name = identity.get("owner_first_name", identity.get("name", "there"))
    kind = trigger.get("kind", "update")
    slug = category.get("slug", "business")

    if slug == "dentists":
        name = f"Dr. {name}"

    body = f"Hi {name}, I have an update for you regarding {kind.replace('_', ' ')}. Would you like to hear more?"

    return ComposedMessage(
        body=body,
        cta=CTAEnum.OPEN_ENDED,
        send_as="merchant_on_behalf" if customer else "vera",
        suppression_key=trigger.get("suppression_key", ""),
        rationale=f"Fallback composition for {kind} trigger — LLM unavailable",
    )


def _build_template_params(body: str, salutation: str) -> list[str]:
    """Extract template parameters from the composed body."""
    # Split body into ~3 segments for WhatsApp template params
    sentences = body.split(". ")
    if len(sentences) >= 3:
        return [salutation, ". ".join(sentences[:2]) + ".", ". ".join(sentences[2:])]
    elif len(sentences) >= 2:
        return [salutation, sentences[0] + ".", ". ".join(sentences[1:])]
    return [salutation, body, ""]
