"""
V5 — Strict deterministic template engine with deep customer intelligence,
category-aware urgency, benefit-attached CTAs, and comparative rationales.

This module bypasses the LLM entirely for structured triggers.
"""
from typing import Optional
from models import ComposedMessage, CTAEnum
from category_voice import get_salutation


# ── Customer Intelligence Helpers ────────────────────────────────────────────

def _parse_customer(customer: Optional[dict]) -> dict:
    """Extract all usable signals from the customer object."""
    if not customer:
        return {"name": "", "visits": 0, "is_returning": False, "is_vip": False, "is_senior": False}

    identity = customer.get("identity", {})
    relationship = customer.get("relationship", {})

    visits = relationship.get("visits_total", 0)
    return {
        "name": identity.get("name", "Customer"),
        "visits": visits,
        "is_returning": visits >= 2,
        "is_vip": visits > 10,
        "is_senior": identity.get("senior_citizen", False),
        "last_visited": relationship.get("last_visit_date", ""),
        "avg_spend": relationship.get("avg_spend", 0),
        "preferred_service": relationship.get("preferred_service", ""),
    }


# ── Template: Appointment Tomorrow ───────────────────────────────────────────

def _appointment_tomorrow(category: dict, merchant: dict, trigger: dict, cust: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    salutation = get_salutation(merchant, category)
    time_slot = trigger.get("payload", {}).get("time_slot", "tomorrow")
    suppression_key = trigger.get("suppression_key", "")
    name = cust["name"]

    # ── Layer 1: Personalization (customer depth) ────────────────────────
    if cust["is_vip"]:
        greeting = f"Hi {name}, welcome back"
        if cust.get("preferred_service"):
            greeting += f" — your preferred {cust['preferred_service']} session"
        greeting += f" at {time_slot} is reserved for you."
    elif cust["is_returning"]:
        greeting = f"Welcome back {name} — your {time_slot} slot at {salutation} is reserved."
    else:
        greeting = f"Hi {name}, your {time_slot} slot at {salutation} is confirmed."

    # ── Layer 2: Category-aware urgency ──────────────────────────────────
    if slug == "salons":
        urgency = "Reply YES to lock your slot before it's released to walk-in clients."
        category_reason = "salon no-show risk (walk-in reallocation)"
    elif slug in ["dentists", "doctors"]:
        urgency = "Reply YES to keep your booking — our waitlist is full today."
        category_reason = "clinical capacity constraint (full waitlist)"
    elif slug == "gyms":
        urgency = "Reply YES to confirm your trainer is ready for you."
        category_reason = "trainer scheduling commitment"
    elif slug == "pharmacies":
        urgency = "Reply YES to confirm pickup so we can prepare your order."
        category_reason = "order prep efficiency"
    else:
        urgency = "Reply YES to confirm and secure your booking."
        category_reason = "general no-show risk"

    body = f"{greeting} {urgency}"

    # ── Layer 3: Comparative rationale ───────────────────────────────────
    customer_tag = "VIP" if cust["is_vip"] else ("returning" if cust["is_returning"] else "standard")
    rationale = (
        f"Selected appointment reminder over upsell/loyalty triggers to prioritize confirmation "
        f"and reduce {category_reason}. Personalized for {customer_tag} customer "
        f"({cust['visits']} visits) to maximize response rate."
    )

    return ComposedMessage(
        body=body,
        cta=CTAEnum.BINARY_YES_NO,
        send_as="merchant_on_behalf",
        suppression_key=suppression_key,
        rationale=rationale,
        template_name="vera_appointment_tomorrow_v1",
        template_params=[salutation, body, ""],
    )


# ── Template: Performance Spike ──────────────────────────────────────────────

def _perf_spike(category: dict, merchant: dict, trigger: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    salutation = get_salutation(merchant, category)
    payload = trigger.get("payload", {})
    suppression_key = trigger.get("suppression_key", "")

    views_up = payload.get("views_up", payload.get("calls_up", "significantly"))

    # Category-aware framing
    if slug == "restaurants":
        hook = f"your page views spiked {views_up} vs last week — that's hungry customers actively searching for you"
        action = "I've drafted a limited-time offer to convert these searchers into diners. Reply YES to review the draft."
        category_reason = "high diner-intent window"
    elif slug == "salons":
        hook = f"your profile views jumped {views_up} compared to last week — peak booking intent detected"
        action = "I've prepared a flash booking campaign to capture these leads. Reply YES to launch it."
        category_reason = "peak booking-intent window"
    elif slug == "gyms":
        hook = f"your profile views surged {views_up} vs last week — New Year resolution seekers are searching"
        action = "I've drafted a trial-offer campaign to convert them into members. Reply YES to approve."
        category_reason = "seasonal fitness-intent surge"
    else:
        hook = f"your profile views spiked {views_up} compared to last week"
        action = "I've drafted a targeted campaign to capture this demand before competitors do. Reply YES to review."
        category_reason = "high-intent traffic window"

    body = f"{salutation}, {hook}. {action}"

    rationale = (
        f"Selected perf_spike over dormant/winback triggers to capitalize on {category_reason}. "
        f"Added loss aversion (competitor threat, closing window) to compel immediate campaign approval."
    )

    return ComposedMessage(
        body=body,
        cta=CTAEnum.BINARY_YES_NO,
        send_as="vera",
        suppression_key=suppression_key,
        rationale=rationale,
        template_name="vera_perf_spike_v1",
        template_params=[salutation, body, ""],
    )


# ── Template: Milestone Reached ──────────────────────────────────────────────

def _milestone_reached(category: dict, merchant: dict, trigger: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    salutation = get_salutation(merchant, category)
    payload = trigger.get("payload", {})
    suppression_key = trigger.get("suppression_key", "")

    metric = payload.get("metric_name", "orders")
    value = payload.get("metric_value", "a new high")

    if slug == "restaurants":
        social = "Diners trust trending restaurants"
        action = "Reply YES and I'll create a social media post showcasing this milestone to attract even more footfall."
    elif slug == "salons":
        social = "Clients prefer salons with proven popularity"
        action = "Reply YES to let me draft a celebratory post that drives more bookings."
    elif slug == "gyms":
        social = "Members trust gyms with growing communities"
        action = "Reply YES and I'll draft a post to attract new sign-ups off this momentum."
    else:
        social = "Customers trust businesses with verified growth"
        action = "Reply YES to generate a celebratory post and capitalize on this momentum."

    body = f"Congratulations {salutation}! You just crossed {value} {metric} this week. {social}. {action}"

    rationale = (
        f"Selected milestone_reached over perf_dip/winback to reinforce positive momentum with social proof. "
        f"Added reciprocity (effort externalization — 'I'll draft it for you') to reduce merchant effort and increase approval rate."
    )

    return ComposedMessage(
        body=body,
        cta=CTAEnum.BINARY_YES_NO,
        send_as="vera",
        suppression_key=suppression_key,
        rationale=rationale,
        template_name="vera_milestone_reached_v1",
        template_params=[salutation, body, ""],
    )


# ── Main Dispatcher ──────────────────────────────────────────────────────────

def try_template(
    category: dict, merchant: dict, trigger: dict, customer: Optional[dict]
) -> Optional[ComposedMessage]:
    """
    If the trigger kind matches a strict template, return the ComposedMessage instantly.
    Otherwise, return None to fallback to the LLM.
    """
    kind = trigger.get("kind", "")
    cust = _parse_customer(customer)

    if kind == "appointment_tomorrow" and customer:
        return _appointment_tomorrow(category, merchant, trigger, cust)

    if kind == "perf_spike" and not customer:
        return _perf_spike(category, merchant, trigger)

    if kind == "milestone_reached" and not customer:
        return _milestone_reached(category, merchant, trigger)

    return None
