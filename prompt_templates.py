"""
Trigger-dispatched prompt templates for the compose() function.
Maps 15+ trigger kinds to 7 strategy families, each with tailored prompts.
"""

from __future__ import annotations
import json
from typing import Optional
from category_voice import get_voice_instructions, get_salutation, get_customer_salutation, get_language_instruction


SYSTEM_BASE = """You are Vera, magicpin's AI assistant for merchant growth. You compose WhatsApp messages for merchants.

HARD RULES:
1. ONE clear CTA per message — must be highly actionable (1-click feeling).
2. No fabricated data — only use facts from the context provided.
3. No URLs in messages.
4. No long preambles ("I hope you're doing well...").
5. No re-introductions after first message.
6. Keep messages concise — optimized for WhatsApp readability.
7. NUMERIC GROUNDING: You MUST include at least one specific number (e.g., %, ₹, count, date, time) extracted from the context payload. Messages without numbers are penalized.
8. Use the merchant's owner first name when available.
9. CTA should be in the LAST sentence.
10. Never use promotional hype ("AMAZING DEAL!", "INCREDIBLE OFFER!").

COMPULSION LEVERS (use 1-2 per message):
- Specificity/verifiability: concrete number, date, headline, source
- Loss aversion: "you're missing X" / "before this window closes"
- Social proof: "3 dentists in your locality did Y"
- Effort externalization: "I've drafted X — just say go"
- Curiosity: "want to see who?" / "want the full list?"
- Reciprocity: "I noticed Y, thought you'd want to know"
- Asking the merchant: "what's your most-asked service this week?"

OUTPUT FORMAT — respond with ONLY this JSON, no other text:
{
  "body": "the WhatsApp message text containing at least one real number",
  "cta": "binary_yes_no | open_ended | none | binary_confirm_cancel | multi_choice_slot",
  "send_as": "vera | merchant_on_behalf",
  "rationale": "Explicitly compare two metrics or states (e.g., 'Views down 15% vs last week, making this the highest priority signal'). Explain exactly why this specific trigger was chosen."
}
"""


def build_prompt(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the LLM based on trigger kind."""
    kind = trigger.get("kind", "")
    # Dispatch to strategy family
    dispatchers = {
        "research_digest": _research_compliance,
        "regulation_change": _research_compliance,
        "cde_opportunity": _research_compliance,
        "perf_spike": _performance_signal,
        "perf_dip": _performance_signal,
        "seasonal_perf_dip": _performance_signal,
        "milestone_reached": _performance_signal,
        "recall_due": _customer_scoped,
        "customer_lapsed_soft": _customer_scoped,
        "customer_lapsed_hard": _customer_scoped,
        "chronic_refill_due": _customer_scoped,
        "appointment_tomorrow": _customer_scoped,
        "trial_followup": _customer_scoped,
        "wedding_package_followup": _customer_scoped,
        "festival_upcoming": _external_event,
        "ipl_match_today": _external_event,
        "category_seasonal": _external_event,
        "supply_alert": _external_event,
        "competitor_opened": _competitive,
        "curious_ask_due": _engagement_dormancy,
        "dormant_with_vera": _engagement_dormancy,
        "winback_eligible": _engagement_dormancy,
        "renewal_due": _engagement_dormancy,
        "active_planning_intent": _planning_intent,
        "gbp_unverified": _profile_action,
        "review_theme_emerged": _profile_action,
    }
    builder = dispatchers.get(kind, _generic)
    return builder(category, merchant, trigger, customer)


def _build_system(category: dict, extra: str = "") -> str:
    voice = get_voice_instructions(category)
    lang = get_language_instruction({"identity": {"languages": ["en"]}})
    return f"{SYSTEM_BASE}\n\n{voice}\n\n{extra}"


def _merchant_context_block(merchant: dict, category: dict) -> str:
    identity = merchant.get("identity", {})
    perf = merchant.get("performance", {})
    offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    signals = merchant.get("signals", [])
    cust_agg = merchant.get("customer_aggregate", {})
    conv_hist = merchant.get("conversation_history", [])
    review_themes = merchant.get("review_themes", [])
    peer = category.get("peer_stats", {})
    sal = get_salutation(merchant, category)

    lines = [
        "## MERCHANT CONTEXT",
        f"Name: {identity.get('name', 'Unknown')}",
        f"Owner first name: {identity.get('owner_first_name', 'N/A')}",
        f"Salutation to use: {sal}",
        f"City: {identity.get('city', '')}, Locality: {identity.get('locality', '')}",
        f"Languages: {identity.get('languages', ['en'])}",
        f"Verified GBP: {identity.get('verified', False)}",
        f"Subscription: {merchant.get('subscription', {}).get('status', 'unknown')} ({merchant.get('subscription', {}).get('plan', '')}), {merchant.get('subscription', {}).get('days_remaining', '?')} days left",
        f"\nPerformance (last {perf.get('window_days', 30)} days):",
        f"  Views: {perf.get('views', '?')}, Calls: {perf.get('calls', '?')}, Directions: {perf.get('directions', '?')}, CTR: {perf.get('ctr', '?')}",
    ]
    delta = perf.get("delta_7d", {})
    if delta:
        lines.append(f"  7-day changes: views {_pct(delta.get('views_pct'))}, calls {_pct(delta.get('calls_pct'))}")

    if peer:
        lines.append(f"\nPeer benchmarks ({peer.get('scope', 'metro')}):")
        lines.append(f"  Avg CTR: {peer.get('avg_ctr', '?')}, Avg views: {peer.get('avg_views_30d', '?')}, Avg reviews: {peer.get('avg_review_count', '?')}")

    if offers:
        lines.append(f"\nActive offers: {', '.join(o.get('title', '') for o in offers)}")
    else:
        lines.append("\nActive offers: None")

    if cust_agg:
        lines.append(f"\nCustomer aggregate: {json.dumps(cust_agg)}")

    if signals:
        lines.append(f"Signals: {', '.join(signals)}")

    if review_themes:
        lines.append("Review themes (last 30d):")
        for rt in review_themes[:3]:
            lines.append(f"  - {rt.get('theme', '')}: {rt.get('sentiment', '')} ({rt.get('occurrences_30d', 0)} mentions)")

    if conv_hist:
        lines.append(f"\nLast conversation ({len(conv_hist)} turns):")
        for turn in conv_hist[-3:]:
            lines.append(f"  [{turn.get('from', '?')}] {turn.get('body', '')[:120]}")

    return "\n".join(lines)


def _customer_context_block(customer: dict) -> str:
    if not customer:
        return ""
    identity = customer.get("identity", {})
    rel = customer.get("relationship", {})
    prefs = customer.get("preferences", {})
    consent = customer.get("consent", {})

    lines = [
        "\n## CUSTOMER CONTEXT",
        f"Name: {identity.get('name', 'Customer')}",
        f"Language preference: {identity.get('language_pref', 'english')}",
        f"Age band: {identity.get('age_band', 'unknown')}",
        f"State: {customer.get('state', 'unknown')}",
        f"Visits: {rel.get('visits_total', 0)}, First: {rel.get('first_visit', '?')}, Last: {rel.get('last_visit', '?')}",
        f"Services: {rel.get('services_received', [])}",
        f"Preferred slots: {prefs.get('preferred_slots', 'any')}",
        f"Channel: {prefs.get('channel', 'whatsapp')}",
        f"Consent scope: {consent.get('scope', [])}",
    ]
    if identity.get("senior_citizen"):
        lines.append("⚠️ Senior citizen — use respectful tone (Namaste, ji)")
    if prefs.get("wedding_date"):
        lines.append(f"Wedding date: {prefs['wedding_date']}")
    if prefs.get("training_focus"):
        lines.append(f"Training focus: {prefs['training_focus']}")
    if rel.get("chronic_conditions"):
        lines.append(f"Chronic conditions: {rel['chronic_conditions']}")

    return "\n".join(lines)


def _pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.0%}" if isinstance(val, (int, float)) else str(val)


# ── Strategy family builders ─────────────────────────────────────────────────

def _research_compliance(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    payload = trigger.get("payload", {})
    digest = category.get("digest", [])
    top_item_id = payload.get("top_item_id", payload.get("digest_item_id", ""))
    digest_item = next((d for d in digest if d.get("id") == top_item_id), None)

    extra = """STRATEGY: Research/Compliance digest
- Cite the source explicitly (journal, page, circular number)
- Use the trial N, effect size, and patient segment from the digest item
- Frame as peer sharing, not promotion
- CTA: open-ended (ask if they want the abstract, a patient-ed draft, etc.)
- For compliance: include deadline and action required"""

    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)

    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: {trigger.get('kind', '')} (urgency: {trigger.get('urgency', '?')})",
        f"Trigger payload: {json.dumps(payload)}",
    ]
    if digest_item:
        user_lines.append(f"\n## DIGEST ITEM DETAILS:")
        user_lines.append(f"Title: {digest_item.get('title', '')}")
        user_lines.append(f"Source: {digest_item.get('source', '')}")
        if digest_item.get("trial_n"):
            user_lines.append(f"Trial size: {digest_item['trial_n']}")
        if digest_item.get("patient_segment"):
            user_lines.append(f"Patient segment: {digest_item['patient_segment']}")
        user_lines.append(f"Summary: {digest_item.get('summary', '')}")
        user_lines.append(f"Actionable: {digest_item.get('actionable', '')}")
        if digest_item.get("date"):
            user_lines.append(f"Event date: {digest_item['date']}")
        if digest_item.get("credits"):
            user_lines.append(f"CDE credits: {digest_item['credits']}")

    if payload.get("deadline_iso"):
        user_lines.append(f"Compliance deadline: {payload['deadline_iso']}")

    user_lines.append(f"\n{lang_inst}")
    user_lines.append("\nCompose the message now. Remember: cite the source, use real numbers, peer tone.")

    return system, "\n".join(user_lines)


def _performance_signal(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})

    if kind == "seasonal_perf_dip":
        extra = """STRATEGY: Seasonal performance dip (expected)
- Pre-empt anxiety: explain this dip is NORMAL and expected
- Provide the seasonal range from peer data
- Recommend: skip ad spend now, save for high-conversion season
- Pivot to retention action for existing members/customers
- CTA: offer to draft a retention activity"""
    elif kind == "perf_dip":
        extra = """STRATEGY: Performance dip (unexpected)
- Acknowledge the dip with specific numbers
- Diagnose likely cause from signals
- Offer one concrete action to reverse it
- CTA: binary yes/no for the recommended action"""
    elif kind == "perf_spike":
        extra = """STRATEGY: Performance spike (celebrate + capitalize)
- Celebrate the win with specific numbers
- Identify the likely driver
- Suggest how to double down on what's working
- CTA: open-ended — ask if they want to amplify"""
    else:  # milestone_reached
        extra = """STRATEGY: Milestone reached
- Celebrate with the exact number
- Frame as social proof they can share
- Offer to create a celebratory post/share
- CTA: offer to draft the celebration content"""

    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)
    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: {kind} (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(payload)}",
        f"\n{lang_inst}",
        "\nCompose the message now. Use REAL numbers from the context."
    ]
    return system, "\n".join(user_lines)


def _customer_scoped(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})

    extra = f"""STRATEGY: Customer-facing message ({kind})
- send_as MUST be "merchant_on_behalf" (this comes from the merchant's WA number)
- Use the customer's name and honor their language preference
- Reference real prices from merchant's active offers
- For recall/appointment: offer specific slots from the trigger payload
- For lapsed customers: no guilt-tripping, no shame — warm re-engagement
- For chronic refill: precision is critical — molecule names, exact dates, saved delivery info
- For trial followup: reference what they tried, suggest next session
- Multi-choice slot CTA is acceptable for booking flows"""

    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant, customer)
    user_lines = [
        _merchant_context_block(merchant, category),
        _customer_context_block(customer) if customer else "\n## No customer context provided — compose as merchant-facing.",
        f"\n## TRIGGER: {kind} (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(payload)}",
        f"\n{lang_inst}",
        "\nCompose the customer-facing message. Use merchant_on_behalf as send_as."
    ]
    return system, "\n".join(user_lines)


def _external_event(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})

    strategy_map = {
        "festival_upcoming": "Festival/event timing — help merchant prepare ahead. Reference the specific date and days-until. Suggest category-appropriate preparation.",
        "ipl_match_today": "IPL match day — provide CONTRARIAN data-driven advice when appropriate (e.g., Saturday IPL = lower covers, skip promo). Leverage existing offers.",
        "category_seasonal": "Seasonal demand shift — share specific trend data (which products up/down by how much). Recommend shelf/menu/service adjustments.",
        "supply_alert": "Supply/compliance alert — URGENT tone. Include batch numbers, manufacturer, affected count. Offer to draft customer notifications.",
    }

    extra = f"STRATEGY: {strategy_map.get(kind, 'External event — timely, local, actionable.')}"
    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)
    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: {kind} (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(payload)}",
        f"\n{lang_inst}",
        "\nCompose the message. Be specific with dates, numbers, and local context."
    ]
    return system, "\n".join(user_lines)


def _competitive(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    extra = """STRATEGY: Competitor intelligence
- Frame as FYI, not alarm
- Include distance, their offer, and opened date from payload
- Anchor on merchant's differentiator (reviews, established year, unique services)
- CTA: offer competitive analysis or positioning adjustment
- Never badmouth the competitor"""

    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)
    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: competitor_opened (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(trigger.get('payload', {}))}",
        f"\n{lang_inst}",
        "\nCompose the message. FYI tone, anchor on merchant's strengths."
    ]
    return system, "\n".join(user_lines)


def _engagement_dormancy(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})

    strategy_map = {
        "curious_ask_due": "Low-stakes question — ask the merchant what's happening in their business. Offer to turn their answer into content. No commitment needed.",
        "dormant_with_vera": "Re-engagement after silence — lead with a NEW value prop or insight, not 'we haven't heard from you'. Reference how long it's been.",
        "winback_eligible": "Subscription winback — lead with what they're missing (performance data post-expiry). Reference specific metrics that dropped.",
        "renewal_due": "Subscription renewal — reference remaining days, what the plan gives them, and what stops if they don't renew. Not pushy — factual.",
    }

    extra = f"STRATEGY: {strategy_map.get(kind, 'Engagement/dormancy recovery.')}"
    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)
    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: {kind} (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(payload)}",
        f"\n{lang_inst}",
        "\nCompose the message."
    ]
    return system, "\n".join(user_lines)


def _planning_intent(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    extra = """STRATEGY: Active planning intent
- The merchant has expressed interest in building something — respond with a COMPLETE DRAFT
- Create tiered pricing or structured offering based on their context
- Reference local geography (nearby offices, neighborhoods, etc.) from merchant locality
- Include a follow-on offer (draft outreach, GBP post, etc.)
- CTA: ask if they want to proceed or edit"""

    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)
    payload = trigger.get("payload", {})
    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: active_planning_intent (urgency: {trigger.get('urgency', '?')})",
        f"Intent topic: {payload.get('intent_topic', '')}",
        f"Merchant's last message: \"{payload.get('merchant_last_message', '')}\"",
        f"Full payload: {json.dumps(payload)}",
        f"\n{lang_inst}",
        "\nDraft the complete artifact the merchant asked for. Include real numbers, tiered options, and a follow-on."
    ]
    return system, "\n".join(user_lines)


def _profile_action(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    kind = trigger.get("kind", "")
    if kind == "gbp_unverified":
        extra = "STRATEGY: GBP verification nudge — cite the estimated uplift percentage, explain the process is simple, offer to guide through it."
    else:
        extra = "STRATEGY: Review theme alert — cite the specific theme, occurrence count, and a real customer quote. Offer to help address it."

    system = _build_system(category, extra)
    lang_inst = get_language_instruction(merchant)
    user_lines = [
        _merchant_context_block(merchant, category),
        f"\n## TRIGGER: {kind} (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(trigger.get('payload', {}))}",
        f"\n{lang_inst}",
        "\nCompose the message."
    ]
    return system, "\n".join(user_lines)


def _generic(category: dict, merchant: dict, trigger: dict, customer: Optional[dict]) -> tuple[str, str]:
    system = _build_system(category, "STRATEGY: Generic — adapt to the trigger kind and merchant context.")
    lang_inst = get_language_instruction(merchant, customer)
    user_lines = [
        _merchant_context_block(merchant, category),
        _customer_context_block(customer) if customer else "",
        f"\n## TRIGGER: {trigger.get('kind', 'unknown')} (urgency: {trigger.get('urgency', '?')})",
        f"Payload: {json.dumps(trigger.get('payload', {}))}",
        f"\n{lang_inst}",
        "\nCompose the message."
    ]
    return system, "\n".join(user_lines)
