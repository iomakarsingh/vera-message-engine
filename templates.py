"""
V5.1 — Strict deterministic template engine with deep customer intelligence,
category-aware urgency, benefit-attached CTAs, comparative rationales,
full merchant names, temporal context, and behavioral adaptation.
"""
from typing import Optional
from models import ComposedMessage, CTAEnum
from category_voice import get_salutation


# ── Customer Intelligence Helpers ────────────────────────────────────────────

def _parse_customer(customer: Optional[dict]) -> dict:
    """Extract all usable signals from the customer object."""
    if not customer:
        return {
            "name": "", "visits": 0, "is_returning": False,
            "is_vip": False, "is_senior": False, "preferred_service": "",
            "no_show_history": False, "avg_spend": 0, "last_visited": "",
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
        "last_visited": relationship.get("last_visit_date", ""),
    }


def _get_merchant_display_name(merchant: dict, category: dict) -> str:
    """Get the full business name for customer-facing messages."""
    identity = merchant.get("identity", {})
    return identity.get("name", get_salutation(merchant, category))


def _get_owner_name(merchant: dict, category: dict) -> str:
    """Get the owner salutation for merchant-facing messages."""
    return get_salutation(merchant, category)


# ── Template: Appointment Tomorrow ───────────────────────────────────────────

def _appointment_tomorrow(category: dict, merchant: dict, trigger: dict, cust: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    biz_name = _get_merchant_display_name(merchant, category)
    time_slot = trigger.get("payload", {}).get("time_slot", "tomorrow")
    suppression_key = trigger.get("suppression_key", "")
    name = cust["name"]

    # ── Layer 1: Personalization (customer depth + behavior) ─────────────
    if cust["is_vip"]:
        if cust.get("preferred_service"):
            greeting = f"Hi {name}, welcome back — your preferred {cust['preferred_service']} session at {time_slot} tomorrow at {biz_name} is reserved for you."
        else:
            greeting = f"Hi {name}, welcome back — your {time_slot} slot tomorrow at {biz_name} is reserved for you."
        customer_tag = "VIP"
    elif cust["is_returning"]:
        greeting = f"Welcome back {name} — your {time_slot} slot tomorrow at {biz_name} is reserved."
        customer_tag = "returning"
    else:
        greeting = f"Hi {name}, your {time_slot} slot tomorrow at {biz_name} is confirmed."
        customer_tag = "standard"

    # ── Layer 2: Behavioral adaptation ───────────────────────────────────
    if cust["no_show_history"]:
        # Stronger urgency for past no-shows
        urgency = f"Reply YES now to lock your {time_slot} slot — unconfirmed bookings will be released to our waitlist."
        behavior_note = " Strengthened urgency due to prior no-show history."
    elif cust["is_vip"]:
        # Softer CTA for loyal VIPs
        urgency = "Reply YES to confirm so we can prep everything for your arrival."
        behavior_note = " Used softer CTA for high-loyalty customer."
    else:
        # ── Layer 3: Category-aware urgency ──────────────────────────────
        if slug == "salons":
            urgency = f"Reply YES now to lock your {time_slot} slot before it's released to walk-in clients."
            category_reason = "salon no-show risk (walk-in reallocation)"
        elif slug in ["dentists", "doctors"]:
            urgency = f"Reply YES now to keep your {time_slot} booking — our waitlist is full today."
            category_reason = "clinical capacity constraint (full waitlist)"
        elif slug == "gyms":
            urgency = f"Reply YES now to confirm — your {time_slot} trainer slot is held for you."
            category_reason = "trainer scheduling commitment"
        elif slug == "pharmacies":
            urgency = f"Reply YES now to confirm pickup at {time_slot} so we can prepare your order."
            category_reason = "order prep efficiency"
        else:
            urgency = f"Reply YES now to lock your {time_slot} booking."
            category_reason = "general no-show risk"
        behavior_note = ""

    if slug in ["salons"] and not cust["no_show_history"] and not cust["is_vip"]:
        category_reason_str = "salon no-show risk (walk-in reallocation)"
    elif slug in ["dentists", "doctors"] and not cust["no_show_history"] and not cust["is_vip"]:
        category_reason_str = "clinical capacity constraint (full waitlist)"
    elif slug == "gyms" and not cust["no_show_history"] and not cust["is_vip"]:
        category_reason_str = "trainer scheduling commitment"
    elif slug == "pharmacies" and not cust["no_show_history"] and not cust["is_vip"]:
        category_reason_str = "order prep efficiency"
    else:
        category_reason_str = "no-show risk"

    body = f"{greeting} {urgency}"

    # ── Layer 4: Comparative rationale with temporal reasoning ────────────
    rationale = (
        f"Selected appointment reminder over upsell/loyalty triggers to prioritize "
        f"confirmation ahead of appointment time and reduce {category_reason_str}. "
        f"Personalized for {customer_tag} customer ({cust['visits']} visits) "
        f"to maximize response rate.{behavior_note}"
    )

    return ComposedMessage(
        body=body,
        cta=CTAEnum.BINARY_YES_NO,
        send_as="merchant_on_behalf",
        suppression_key=suppression_key,
        rationale=rationale,
        template_name="vera_appointment_tomorrow_v1",
        template_params=[biz_name, body, ""],
    )


# ── Template: Performance Spike ──────────────────────────────────────────────

def _perf_spike(category: dict, merchant: dict, trigger: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    owner = _get_owner_name(merchant, category)
    payload = trigger.get("payload", {})
    suppression_key = trigger.get("suppression_key", "")

    views_up = payload.get("views_up", payload.get("calls_up", "significantly"))

    if slug == "restaurants":
        hook = f"your page views spiked {views_up} vs last week — that's hungry customers actively searching for you right now"
        action = "I've drafted a limited-time offer to convert these searchers into diners before they pick a competitor. Reply YES now to review the draft."
        category_reason = "high diner-intent window"
    elif slug == "salons":
        hook = f"your profile views jumped {views_up} compared to last week — peak booking intent detected"
        action = "I've prepared a flash booking campaign to capture these leads before they book elsewhere. Reply YES now to launch it."
        category_reason = "peak booking-intent window"
    elif slug == "gyms":
        hook = f"your profile views surged {views_up} vs last week — fitness seekers are searching for you"
        action = "I've drafted a trial-offer campaign to convert them into members. Reply YES now to approve."
        category_reason = "seasonal fitness-intent surge"
    else:
        hook = f"your profile views spiked {views_up} compared to last week"
        action = "I've drafted a targeted campaign to capture this demand before competitors do. Reply YES now to review."
        category_reason = "high-intent traffic window"

    body = f"{owner}, {hook}. {action}"

    rationale = (
        f"Selected perf_spike over dormant/winback triggers to capitalize on {category_reason}. "
        f"Added loss aversion (competitor threat, closing window) and effort externalization "
        f"('I've drafted') to compel immediate campaign approval."
    )

    return ComposedMessage(
        body=body,
        cta=CTAEnum.BINARY_YES_NO,
        send_as="vera",
        suppression_key=suppression_key,
        rationale=rationale,
        template_name="vera_perf_spike_v1",
        template_params=[owner, body, ""],
    )


# ── Template: Milestone Reached ──────────────────────────────────────────────

def _milestone_reached(category: dict, merchant: dict, trigger: dict) -> ComposedMessage:
    slug = category.get("slug", "business")
    owner = _get_owner_name(merchant, category)
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
        body=body,
        cta=CTAEnum.BINARY_YES_NO,
        send_as="vera",
        suppression_key=suppression_key,
        rationale=rationale,
        template_name="vera_milestone_reached_v1",
        template_params=[owner, body, ""],
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
