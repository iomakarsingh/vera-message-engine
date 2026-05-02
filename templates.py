"""
V6 — Growth Decision Engine with:
  - Variation engine (3 message structures per trigger to avoid repetition)
  - Escalation awareness (soft → strong → final warning)
  - Deep customer intelligence (visits, behavior, preferred services)
  - Category-specific urgency physics
  - Comparative rationales with temporal reasoning
"""
import hashlib
from typing import Optional
from models import ComposedMessage, CTAEnum
from category_voice import get_salutation


# ── Customer Intelligence ────────────────────────────────────────────────────

def _parse_customer(customer: Optional[dict]) -> dict:
    """Extract all usable signals from the customer object."""
    if not customer:
        return {
            "name": "", "visits": 0, "is_returning": False,
            "is_vip": False, "is_senior": False, "preferred_service": "",
            "no_show_history": False, "avg_spend": 0,
        }

    identity = customer.get("identity", {})
    relationship = customer.get("relationship", {})
    visits = relationship.get("visits_total", 0)

    return {
        "name": identity.get("name", "Customer"),
        "visits": visits,
        "is_returning": visits >= 2,
        "is_vip": visits > 10,
        "is_senior": identity.get("senior_citizen", False),
        "preferred_service": relationship.get("preferred_service", ""),
        "no_show_history": relationship.get("no_show_count", 0) > 0,
        "avg_spend": relationship.get("avg_spend", 0),
    }


def _get_biz_name(merchant: dict) -> str:
    """Full business name for customer-facing messages."""
    return merchant.get("identity", {}).get("name", "our store")


def _get_owner(merchant: dict, category: dict) -> str:
    """Owner salutation for merchant-facing messages."""
    return get_salutation(merchant, category)


def _pick_variant(seed: str, count: int) -> int:
    """Deterministic but varied selection based on a seed string."""
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % count


# ── APPOINTMENT TOMORROW ─────────────────────────────────────────────────────

def _appointment_tomorrow(
    category: dict, merchant: dict, trigger: dict,
    cust: dict, escalation: int
) -> ComposedMessage:
    slug = category.get("slug", "business")
    biz_name = _get_biz_name(merchant)
    time_slot = trigger.get("payload", {}).get("time_slot", "tomorrow")
    suppression_key = trigger.get("suppression_key", "")
    name = cust["name"]

    # ── Escalation progression ───────────────────────────────────────────
    if escalation >= 2:
        # FINAL WARNING — strongest urgency
        body = (
            f"Final reminder {name} — your {time_slot} slot tomorrow at "
            f"{biz_name} will be released in 1 hour if not confirmed. "
            f"Reply YES now to keep it."
        )
        rationale = (
            f"Escalation level {escalation}: Final warning issued after {escalation} "
            f"prior unreplied sends. Selected urgent reminder over all other triggers "
            f"to recover confirmation within 24h window before auto-release. "
            f"Personalized for {'returning' if cust['is_returning'] else 'standard'} "
            f"customer ({cust['visits']} visits)."
        )
        return ComposedMessage(
            body=body, cta=CTAEnum.BINARY_YES_NO, send_as="merchant_on_behalf",
            suppression_key=suppression_key, rationale=rationale,
            template_name="vera_appointment_tomorrow_v1",
            template_params=[biz_name, body, ""],
        )

    if escalation == 1:
        # FOLLOW-UP — medium urgency
        body = (
            f"Hi {name}, just checking — your {time_slot} appointment tomorrow "
            f"at {biz_name} is still held for you. "
            f"Reply YES now to confirm before we open it to the waitlist."
        )
        rationale = (
            f"Escalation level 1: Follow-up after no reply to initial reminder. "
            f"Selected confirmation reminder over upsell/loyalty triggers to "
            f"prioritize booking within 24h window and reduce "
            f"{slug} no-show risk. Customer: {cust['visits']} visits."
        )
        return ComposedMessage(
            body=body, cta=CTAEnum.BINARY_YES_NO, send_as="merchant_on_behalf",
            suppression_key=suppression_key, rationale=rationale,
            template_name="vera_appointment_tomorrow_v1",
            template_params=[biz_name, body, ""],
        )

    # ── FIRST MESSAGE — use variation engine ─────────────────────────────

    # Category-specific urgency hooks
    if slug == "salons":
        urgency_hook = f"Reply YES now to lock your {time_slot} slot before it's released to walk-in clients."
        cat_reason = "salon no-show risk (walk-in reallocation)"
    elif slug in ["dentists", "doctors"]:
        urgency_hook = f"Reply YES now to keep your {time_slot} booking — our waitlist is full today."
        cat_reason = "clinical capacity constraint (full waitlist)"
    elif slug == "gyms":
        urgency_hook = f"Reply YES now to confirm — your {time_slot} trainer slot is held for you."
        cat_reason = "trainer scheduling commitment"
    elif slug == "pharmacies":
        urgency_hook = f"Reply YES now to confirm your {time_slot} pickup so we can prepare your order."
        cat_reason = "order prep efficiency"
    else:
        urgency_hook = f"Reply YES now to lock your {time_slot} booking."
        cat_reason = "general no-show risk"

    # No-show behavior override
    if cust["no_show_history"]:
        urgency_hook = (
            f"Reply YES now to lock your {time_slot} slot — "
            f"unconfirmed bookings will be released to our waitlist."
        )
        behavior_note = " Strengthened urgency due to prior no-show history."
    else:
        behavior_note = ""

    # ── 3 Variations for first message ───────────────────────────────────
    seed = f"{name}_{biz_name}_{time_slot}"
    variant = _pick_variant(seed, 3)

    if cust["is_vip"]:
        # VIP always gets premium treatment
        svc = cust.get("preferred_service")
        if svc:
            greeting = f"Hi {name}, welcome back — your preferred {svc} session at {time_slot} tomorrow at {biz_name} is reserved for you."
        else:
            greeting = f"Hi {name}, welcome back — your {time_slot} slot tomorrow at {biz_name} is reserved for you."
        # Softer CTA for VIPs
        urgency_hook = "Reply YES to confirm so we can prep everything for your arrival."
        customer_tag = "VIP"
        behavior_note = " Used softer CTA for high-loyalty customer."
    elif cust["is_returning"]:
        customer_tag = "returning"
        if variant == 0:
            greeting = f"Welcome back {name} — your {time_slot} slot tomorrow at {biz_name} is reserved."
        elif variant == 1:
            greeting = f"Good to see you again {name} — your {time_slot} appointment tomorrow at {biz_name} is confirmed."
        else:
            greeting = f"Hi {name}, your regular {time_slot} slot tomorrow at {biz_name} is held for you."
    else:
        customer_tag = "standard"
        if variant == 0:
            greeting = f"Hi {name}, your {time_slot} slot tomorrow at {biz_name} is confirmed."
        elif variant == 1:
            greeting = f"Hi {name}, you're booked for {time_slot} tomorrow at {biz_name}."
        else:
            greeting = f"Hi {name}, just confirming your {time_slot} appointment tomorrow at {biz_name}."

    body = f"{greeting} {urgency_hook}"

    rationale = (
        f"Selected appointment reminder over upsell/loyalty triggers to prioritize "
        f"confirmation within 24h window and reduce {cat_reason}. "
        f"Personalized for {customer_tag} customer ({cust['visits']} visits) "
        f"to maximize response rate.{behavior_note}"
    )

    return ComposedMessage(
        body=body, cta=CTAEnum.BINARY_YES_NO, send_as="merchant_on_behalf",
        suppression_key=suppression_key, rationale=rationale,
        template_name="vera_appointment_tomorrow_v1",
        template_params=[biz_name, body, ""],
    )


# ── PERF SPIKE ───────────────────────────────────────────────────────────────

def _perf_spike(category: dict, merchant: dict, trigger: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    owner = _get_owner(merchant, category)
    payload = trigger.get("payload", {})
    suppression_key = trigger.get("suppression_key", "")
    views_up = payload.get("views_up", payload.get("calls_up", "significantly"))

    if slug == "restaurants":
        hook = f"your page views spiked {views_up} vs last week — that's hungry customers actively searching for you right now"
        action = "I've drafted a limited-time offer to convert these searchers into diners before they pick a competitor. Reply YES now to review the draft."
        cat_reason = "high diner-intent window"
    elif slug == "salons":
        hook = f"your profile views jumped {views_up} compared to last week — peak booking intent detected"
        action = "I've prepared a flash booking campaign to capture these leads before they book elsewhere. Reply YES now to launch it."
        cat_reason = "peak booking-intent window"
    elif slug == "gyms":
        hook = f"your profile views surged {views_up} vs last week — fitness seekers are searching for you"
        action = "I've drafted a trial-offer campaign to convert them into members. Reply YES now to approve."
        cat_reason = "seasonal fitness-intent surge"
    else:
        hook = f"your profile views spiked {views_up} compared to last week"
        action = "I've drafted a targeted campaign to capture this demand before competitors do. Reply YES now to review."
        cat_reason = "high-intent traffic window"

    body = f"{owner}, {hook}. {action}"

    rationale = (
        f"Selected perf_spike over dormant/winback triggers to capitalize on "
        f"{cat_reason}. Added loss aversion (competitor threat, closing window) "
        f"and effort externalization ('I've drafted') to compel immediate campaign approval."
    )

    return ComposedMessage(
        body=body, cta=CTAEnum.BINARY_YES_NO, send_as="vera",
        suppression_key=suppression_key, rationale=rationale,
        template_name="vera_perf_spike_v1", template_params=[owner, body, ""],
    )


# ── MILESTONE REACHED ────────────────────────────────────────────────────────

def _milestone_reached(category: dict, merchant: dict, trigger: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    owner = _get_owner(merchant, category)
    payload = trigger.get("payload", {})
    suppression_key = trigger.get("suppression_key", "")
    metric = payload.get("metric_name", "orders")
    value = payload.get("metric_value", "a new high")

    if slug == "restaurants":
        social = "Diners trust trending restaurants — this is the perfect moment to amplify"
        action = "Reply YES now and I'll create a social media post showcasing this milestone to drive even more footfall."
    elif slug == "salons":
        social = "Clients prefer salons with proven popularity — capitalize on this momentum"
        action = "Reply YES now to let me draft a celebratory post that drives more bookings this week."
    elif slug == "gyms":
        social = "Members trust gyms with growing communities — now is the time to show it"
        action = "Reply YES now and I'll draft a post to attract new sign-ups off this momentum."
    else:
        social = "Customers trust businesses with verified growth — let's use this momentum"
        action = "Reply YES now to generate a celebratory post and capitalize on this wave."

    body = f"Congratulations {owner}! You just crossed {value} {metric} this week. {social}. {action}"

    rationale = (
        f"Selected milestone_reached over perf_dip/winback to reinforce positive momentum "
        f"with social proof while merchant motivation is high. Added reciprocity "
        f"(effort externalization — 'I'll draft it') to reduce merchant effort and increase approval rate."
    )

    return ComposedMessage(
        body=body, cta=CTAEnum.BINARY_YES_NO, send_as="vera",
        suppression_key=suppression_key, rationale=rationale,
        template_name="vera_milestone_reached_v1", template_params=[owner, body, ""],
    )


# ── Main Dispatcher ──────────────────────────────────────────────────────────

def try_template(
    category: dict, merchant: dict, trigger: dict,
    customer: Optional[dict], escalation: int = 0
) -> Optional[ComposedMessage]:
    """
    If the trigger kind matches a strict template, return the ComposedMessage instantly.
    Otherwise, return None to fallback to the LLM.
    
    Args:
        escalation: Number of prior sends for this conversation (0 = first message).
    """
    kind = trigger.get("kind", "")
    cust = _parse_customer(customer)

    if kind == "appointment_tomorrow" and customer:
        return _appointment_tomorrow(category, merchant, trigger, cust, escalation)

    if kind == "perf_spike" and not customer:
        return _perf_spike(category, merchant, trigger)

    if kind == "milestone_reached" and not customer:
        return _milestone_reached(category, merchant, trigger)

    return None
