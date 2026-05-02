"""
Versioned in-memory context store.
Idempotent by (scope, context_id, version).
Higher version replaces atomically; same/lower version is a no-op or reject.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional


class ContextStore:
    """Thread-safe versioned context store for all 4 context scopes."""

    VALID_SCOPES = {"category", "merchant", "customer", "trigger"}

    def __init__(self):
        self._data: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def store(
        self, scope: str, context_id: str, version: int, payload: dict
    ) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Store a context payload.

        Returns:
            (accepted, reason, current_version)
            - (True, None, None) on success
            - (False, "stale_version", current_version) if same or lower version
            - (False, "invalid_scope", None) if scope is invalid
        """
        if scope not in self.VALID_SCOPES:
            return False, "invalid_scope", None

        key = (scope, context_id)

        async with self._lock:
            existing = self._data.get(key)

            if existing and existing["version"] >= version:
                return False, "stale_version", existing["version"]

            self._data[key] = {
                "version": version,
                "payload": payload,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
            return True, None, None

    def get(self, scope: str, context_id: str) -> Optional[dict]:
        """Get the payload for a (scope, context_id) pair."""
        entry = self._data.get((scope, context_id))
        return entry["payload"] if entry else None

    def get_version(self, scope: str, context_id: str) -> Optional[int]:
        """Get the current version for a (scope, context_id) pair."""
        entry = self._data.get((scope, context_id))
        return entry["version"] if entry else None

    def get_merchant(self, merchant_id: str) -> Optional[dict]:
        """Shortcut to get merchant context."""
        return self.get("merchant", merchant_id)

    def get_category(self, category_slug: str) -> Optional[dict]:
        """Shortcut to get category context."""
        return self.get("category", category_slug)

    def get_category_for_merchant(self, merchant_id: str) -> Optional[dict]:
        """Resolve category context from a merchant's category_slug."""
        merchant = self.get_merchant(merchant_id)
        if not merchant:
            return None
        slug = merchant.get("category_slug", "")
        return self.get_category(slug)

    def get_customer(self, customer_id: str) -> Optional[dict]:
        """Shortcut to get customer context."""
        return self.get("customer", customer_id)

    def get_trigger(self, trigger_id: str) -> Optional[dict]:
        """Shortcut to get trigger context."""
        return self.get("trigger", trigger_id)

    def get_all(self, scope: str) -> list[dict]:
        """Get all payloads for a given scope."""
        return [
            entry["payload"]
            for (s, _), entry in self._data.items()
            if s == scope
        ]

    def counts(self) -> dict[str, int]:
        """Count of contexts per scope."""
        counts = {s: 0 for s in self.VALID_SCOPES}
        for (scope, _) in self._data:
            counts[scope] = counts.get(scope, 0) + 1
        return counts
