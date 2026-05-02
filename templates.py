"""
Strict deterministic template engine to bypass LLMs for highly structured triggers.
"""
from typing import Optional
from models import ComposedMessage, CTAEnum
from category_voice import get_salutation


def try_template(
    category: dict, merchant: dict, trigger: dict, customer: Optional[dict]
) -> Optional[ComposedMessage]:
    """
    If the trigger kind matches a strict template, return the ComposedMessage instantly.
    Otherwise, return None to fallback to the LLM.
    """
    kind = trigger.get("kind", "")
    payload = trigger.get("payload", {})
    suppression_key = trigger.get("suppression_key", "")
    send_as = "merchant_on_behalf" if customer else "vera"

    salutation = get_salutation(merchant, category)
    
    if customer:
        cust_name = customer.get("identity", {}).get("name", "Customer")
    else:
        cust_name = ""

    # -- 1. Appointment Tomorrow (Customer-facing)
    if kind == "appointment_tomorrow" and customer:
        time_slot = payload.get("time_slot", "tomorrow")
        body = f"Hi {cust_name}, this is a reminder for your appointment at {salutation} {time_slot}. Please reply YES to confirm."
        return ComposedMessage(
            body=body,
            cta=CTAEnum.BINARY_YES_NO,
            send_as=send_as,
            suppression_key=suppression_key,
            rationale=f"Template match for {kind}. Bypassed LLM for guaranteed determinism.",
            template_name=f"vera_{kind}_v1",
            template_params=[salutation, body, ""]
        )

    # -- 2. Performance Spike (Merchant-facing)
    if kind == "perf_spike" and not customer:
        views_up = payload.get("views_up", payload.get("calls_up", "a significant amount"))
        body = f"{salutation}, your profile views spiked {views_up} this week compared to your usual average! I've drafted a new campaign to double down on this momentum. Should I send you the draft?"
        return ComposedMessage(
            body=body,
            cta=CTAEnum.BINARY_YES_NO,
            send_as=send_as,
            suppression_key=suppression_key,
            rationale=f"Template match for {kind}. Bypassed LLM for guaranteed determinism.",
            template_name=f"vera_{kind}_v1",
            template_params=[salutation, body, ""]
        )

    # -- 3. Milestone Reached (Merchant-facing)
    if kind == "milestone_reached" and not customer:
        metric = payload.get("metric_name", "orders")
        value = payload.get("metric_value", "a new high")
        body = f"Congratulations {salutation}! You just crossed {value} {metric} this week. Should I generate a celebratory social media post for you?"
        return ComposedMessage(
            body=body,
            cta=CTAEnum.BINARY_YES_NO,
            send_as=send_as,
            suppression_key=suppression_key,
            rationale=f"Template match for {kind}. Bypassed LLM for guaranteed determinism.",
            template_name=f"vera_{kind}_v1",
            template_params=[salutation, body, ""]
        )

    return None
