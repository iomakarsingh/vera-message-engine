import logging
from typing import Optional

logger = logging.getLogger(__name__)


def rank_triggers(available_triggers: list[str], store) -> list[str]:
    """
    Given a list of trigger IDs, returns them sorted by score (highest first).
    """
    scored = []
    for tid in available_triggers:
        trigger = store.get_trigger(tid)
        if not trigger:
            continue

        merchant_id = trigger.get("merchant_id", "")
        merchant = store.get_merchant(merchant_id)
        if not merchant:
            continue

        category = store.get_category(merchant.get("category_slug", ""))
        
        score = _score_trigger(trigger, merchant, category)
        scored.append((score, tid))
        logger.debug(f"Trigger {tid} scored {score}")

    # Sort descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [tid for score, tid in scored]


def _score_trigger(trigger: dict, merchant: dict, category: Optional[dict]) -> int:
    """
    Score a trigger based on urgency, kind, and category multipliers.
    """
    score = 0
    kind = trigger.get("kind", "")
    urgency = trigger.get("urgency", "low")
    
    # Base urgency score
    if urgency == "high":
        score += 10
    elif urgency == "medium":
        score += 5
    else:
        score += 1

    if not category:
        return score

    slug = category.get("slug", "")

    # Category-specific multipliers
    if slug in ["dentists", "pharmacies"]:
        if kind in ["recall_due", "regulation_change", "chronic_refill_due"]:
            score += 5
    elif slug == "restaurants":
        if kind in ["perf_spike", "ipl_match_today", "festival_upcoming"]:
            score += 5
    elif slug == "gyms":
        if kind in ["customer_lapsed_hard", "winback_eligible", "seasonal_perf_dip"]:
            score += 5
    elif slug == "salons":
        if kind in ["wedding_package_followup", "appointment_tomorrow", "perf_dip"]:
            score += 5

    return score
