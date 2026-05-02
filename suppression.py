"""
In-memory suppression registry.
Tracks sent suppression keys with TTLs to prevent duplicate sends.
Also supports merchant-level suppression (e.g., after hostile exit).
"""

from __future__ import annotations

import time


# Default TTLs per trigger kind (seconds)
DEFAULT_TTLS: dict[str, int] = {
    "research_digest": 7 * 86400,        # 7 days
    "regulation_change": 30 * 86400,      # 30 days
    "cde_opportunity": 7 * 86400,         # 7 days
    "recall_due": 30 * 86400,             # 30 days
    "customer_lapsed_soft": 14 * 86400,   # 14 days
    "customer_lapsed_hard": 30 * 86400,   # 30 days
    "chronic_refill_due": 30 * 86400,     # 30 days
    "appointment_tomorrow": 2 * 86400,    # 2 days
    "trial_followup": 7 * 86400,          # 7 days
    "wedding_package_followup": 14 * 86400,  # 14 days
    "perf_spike": 3 * 86400,             # 3 days
    "perf_dip": 3 * 86400,               # 3 days
    "seasonal_perf_dip": 7 * 86400,      # 7 days
    "milestone_reached": 7 * 86400,      # 7 days
    "festival_upcoming": 3 * 86400,      # 3 days
    "ipl_match_today": 86400,            # 1 day
    "category_seasonal": 14 * 86400,     # 14 days
    "supply_alert": 7 * 86400,           # 7 days
    "competitor_opened": 14 * 86400,     # 14 days
    "curious_ask_due": 7 * 86400,        # 7 days
    "dormant_with_vera": 14 * 86400,     # 14 days
    "winback_eligible": 14 * 86400,      # 14 days
    "renewal_due": 3 * 86400,            # 3 days
    "active_planning_intent": 3 * 86400, # 3 days
    "gbp_unverified": 14 * 86400,        # 14 days
    "review_theme_emerged": 7 * 86400,   # 7 days
}

DEFAULT_TTL = 7 * 86400  # 7 days fallback


class SuppressionRegistry:
    """Tracks suppression keys to prevent duplicate sends."""

    def __init__(self):
        self._keys: dict[str, float] = {}  # key -> expiry timestamp
        self._merchant_suppressed: dict[str, float] = {}  # merchant_id -> expiry

    def is_suppressed(self, key: str) -> bool:
        """Check if a suppression key is active."""
        expiry = self._keys.get(key)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._keys[key]
            return False
        return True

    def suppress(self, key: str, trigger_kind: str = "") -> None:
        """Register a suppression key with TTL based on trigger kind."""
        ttl = DEFAULT_TTLS.get(trigger_kind, DEFAULT_TTL)
        self._keys[key] = time.time() + ttl

    def suppress_merchant(self, merchant_id: str, ttl_seconds: int = 30 * 86400) -> None:
        """Suppress ALL triggers for a merchant (e.g., after hostile exit)."""
        self._merchant_suppressed[merchant_id] = time.time() + ttl_seconds

    def is_merchant_suppressed(self, merchant_id: str) -> bool:
        """Check if a merchant is globally suppressed."""
        expiry = self._merchant_suppressed.get(merchant_id)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._merchant_suppressed[merchant_id]
            return False
        return True

    def clear(self) -> None:
        """Clear all suppression state."""
        self._keys.clear()
        self._merchant_suppressed.clear()
