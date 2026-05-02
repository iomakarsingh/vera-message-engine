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
    slug = category.get("slug", "business")
    
    # Customer state parsing
    cust_name = ""
    is_vip = False
    is_senior = False
    
    if customer:
        cust_name = customer.get("identity", {}).get("name", "Customer")
        visits = customer.get("relationship", {}).get("visits_total", 0)
        is_vip = visits > 10
        is_senior = customer.get("identity", {}).get("senior_citizen", False)

    # -- 1. Appointment Tomorrow (Customer-facing, Highly Adaptive)
    if kind == "appointment_tomorrow" and customer:
        time_slot = payload.get("time_slot", "tomorrow")
        
        # Adaptive Logic: VIP vs Standard
        if is_vip:
            intro = f"Hi {cust_name}, we've reserved your preferred spot at {time_slot}."
            urgency = "Please reply YES to confirm so we can prep for your arrival."
            rationale = "Selected appointment reminder. Adapted for VIP customer (high visits) with soft confirmation CTA to ensure white-glove service without aggressive penalties."
        else:
            intro = f"Hi {cust_name}, your {time_slot} slot at {salutation} is reserved."
            # Category Intelligence for Standard Customers
            if slug == "salons":
                urgency = "Please confirm now to avoid auto-release to our walk-in waitlist."
                rationale = "Selected appointment reminder to reduce salon no-show risk. Added high urgency (auto-release to walk-ins) to force immediate confirmation."
            elif slug in ["dentists", "doctors", "pharmacies"]:
                urgency = "Our schedule is full today. Confirm now to secure your booking and avoid cancellation."
                rationale = "Selected appointment reminder for clinical category. Added urgency (waitlist capacity) to ensure maximum chair utilization."
            else:
                urgency = "Please reply YES to confirm your booking immediately."
                rationale = "Selected appointment reminder to reduce general no-show risk. Added immediate confirmation CTA."

        body = f"{intro} {urgency}"
        
        return ComposedMessage(
            body=body,
            cta=CTAEnum.BINARY_YES_NO,
            send_as=send_as,
            suppression_key=suppression_key,
            rationale=rationale,
            template_name=f"vera_{kind}_v1",
            template_params=[salutation, body, ""]
        )

    # -- 2. Performance Spike (Merchant-facing, Persuasive)
    if kind == "perf_spike" and not customer:
        views_up = payload.get("views_up", payload.get("calls_up", "a significant amount"))
        
        body = f"{salutation}, your profile views just spiked {views_up} compared to last week! This window of high intent closes fast. I've drafted a targeted offer to capture these leads before they go to competitors. Should I send you the draft?"
        
        return ComposedMessage(
            body=body,
            cta=CTAEnum.BINARY_YES_NO,
            send_as=send_as,
            suppression_key=suppression_key,
            rationale="Selected perf_spike to capitalize on momentum. Added strong loss aversion ('window closes fast', 'competitors') to compel immediate approval of the campaign draft.",
            template_name=f"vera_{kind}_v1",
            template_params=[salutation, body, ""]
        )

    # -- 3. Milestone Reached (Merchant-facing, Social Proof)
    if kind == "milestone_reached" and not customer:
        metric = payload.get("metric_name", "orders")
        value = payload.get("metric_value", "a new high")
        
        body = f"Congratulations {salutation}! You just crossed {value} {metric} this week. Customers trust businesses with verified momentum. Should I generate a celebratory social media post to drive even more footfall?"
        
        return ComposedMessage(
            body=body,
            cta=CTAEnum.BINARY_YES_NO,
            send_as=send_as,
            suppression_key=suppression_key,
            rationale="Selected milestone_reached trigger. Added social proof mechanics ('verified momentum') to compel the merchant to authorize a promotional post.",
            template_name=f"vera_{kind}_v1",
            template_params=[salutation, body, ""]
        )

    return None
