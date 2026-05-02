"""
Multi-turn reply handler for /v1/reply.
Handles auto-reply detection, intent transitions, hostile exits, and off-topic deflection.
"""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from models import ReplyResponse
from llm_client import LLMClient
from context_store import ContextStore
from suppression import SuppressionRegistry

logger = logging.getLogger(__name__)

# Auto-reply detection patterns
AUTO_REPLY_PATTERNS = [
    "thank you for contacting",
    "our team will respond shortly",
    "we will get back to you",
    "automated assistant",
    "auto-reply",
    "auto reply",
    "aapki jaankari ke liye",
    "bahut-bahut shukriya",
    "hamari team tak pahuncha",
    "yeh sabhi baatein",
    "main ek automated assistant",
]

# Intent commitment patterns
COMMITMENT_PATTERNS = [
    r"\byes\b", r"\byes please\b", r"\bhaan\b", r"\bha\b",
    r"\blet'?s do it\b", r"\bgo ahead\b", r"\bproceed\b",
    r"\bok do it\b", r"\bconfirm\b", r"\bsend it\b",
    r"\bdraft it\b", r"\bsure\b", r"\bchalo\b",
    r"\bkar do\b", r"\bkaro\b", r"\bwhat'?s next\b",
    r"\bagree\b", r"\bapproved\b",
]

# Hostile / opt-out patterns
HOSTILE_PATTERNS = [
    r"\bstop messaging\b", r"\bstop\b", r"\bnot interested\b",
    r"\bunsubscribe\b", r"\bspam\b", r"\buseless\b",
    r"\bbothering\b", r"\bstop sending\b", r"\bdon'?t message\b",
    r"\bblock\b", r"\breport\b",
]

# Off-topic patterns
OFF_TOPIC_PATTERNS = [
    r"\bgst\b", r"\btax\b", r"\bloan\b", r"\binsurance\b",
    r"\blegal\b", r"\bcourt\b", r"\bpolice\b",
]


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    trigger_id: str = ""
    turns: list[dict] = field(default_factory=list)
    auto_reply_count: int = 0
    unanswered_nudge_count: int = 0
    mode: str = "qualifying"  # "qualifying" | "action" | "ended"
    last_bot_body: str = ""


class ReplyHandler:
    """Handles multi-turn conversation replies."""

    def __init__(self, store: ContextStore, suppression: SuppressionRegistry):
        self.store = store
        self.suppression = suppression
        self.conversations: dict[str, ConversationState] = {}
        self._llm: Optional[LLMClient] = None

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    def get_or_create_state(self, conv_id: str, merchant_id: str = "",
                            customer_id: str = None, trigger_id: str = "") -> ConversationState:
        if conv_id not in self.conversations:
            self.conversations[conv_id] = ConversationState(
                conversation_id=conv_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                trigger_id=trigger_id,
            )
        return self.conversations[conv_id]

    def record_bot_send(self, conv_id: str, body: str, merchant_id: str = "",
                        trigger_id: str = ""):
        """Record that the bot sent a message (from /v1/tick)."""
        state = self.get_or_create_state(conv_id, merchant_id, trigger_id=trigger_id)
        state.turns.append({"from": "vera", "body": body})
        state.last_bot_body = body

    def handle_reply(self, conv_id: str, merchant_id: str,
                     customer_id: Optional[str], from_role: str,
                     message: str, turn_number: int) -> ReplyResponse:
        """Process an incoming reply and return the bot's next action."""
        state = self.get_or_create_state(conv_id, merchant_id, customer_id)
        state.turns.append({"from": from_role, "body": message})

        if state.mode == "ended":
            return ReplyResponse(action="end", rationale="Conversation already ended.")

        msg_lower = message.lower().strip()

        # ── Classifier 1: Auto-reply detection ──
        if self._is_auto_reply(msg_lower, state):
            state.auto_reply_count += 1
            if state.auto_reply_count >= 3:
                state.mode = "ended"
                return ReplyResponse(
                    action="end",
                    rationale=f"Auto-reply detected {state.auto_reply_count}x in a row. No real engagement signal; closing."
                )
            elif state.auto_reply_count >= 2:
                return ReplyResponse(
                    action="wait",
                    wait_seconds=86400,
                    rationale="Same auto-reply twice in a row — owner not at phone. Wait 24h before retry."
                )
            else:
                return ReplyResponse(
                    action="send",
                    body="Looks like an auto-reply 😊 When the owner sees this, just reply 'Yes' to continue.",
                    cta="binary_yes_no",
                    rationale="Detected auto-reply (canned greeting phrasing). One explicit prompt for the owner."
                )

        # Reset auto-reply count on real message
        state.auto_reply_count = 0

        # ── Classifier 2: Hostile / opt-out ──
        if self._is_hostile(msg_lower):
            state.mode = "ended"
            self.suppression.suppress_merchant(merchant_id, 30 * 86400)
            return ReplyResponse(
                action="send",
                body="Apologies — I won't message again. If anything changes, you can always restart with 'Hi Vera'. 🙏",
                cta="none",
                rationale="Merchant frustration explicit. One-line acknowledgment + opt-out path; suppressing all triggers for 30 days."
            )

        # ── Classifier 3: Intent commitment ──
        if self._is_commitment(msg_lower):
            state.mode = "action"
            return self._generate_action_response(state, message)

        # ── Classifier 4: Off-topic ──
        if self._is_off_topic(msg_lower):
            return self._handle_off_topic(state, message)

        # ── Default: Continue conversation via LLM ──
        return self._generate_continuation(state, message)

    def _is_auto_reply(self, msg: str, state: ConversationState) -> bool:
        # Same message verbatim as last merchant turn
        merchant_turns = [t for t in state.turns if t["from"] != "vera"]
        if len(merchant_turns) >= 2 and merchant_turns[-1]["body"] == merchant_turns[-2]["body"]:
            return True
        # Pattern-based detection
        return any(pattern in msg for pattern in AUTO_REPLY_PATTERNS)

    def _is_hostile(self, msg: str) -> bool:
        return any(re.search(p, msg) for p in HOSTILE_PATTERNS)

    def _is_commitment(self, msg: str) -> bool:
        return any(re.search(p, msg) for p in COMMITMENT_PATTERNS)

    def _is_off_topic(self, msg: str) -> bool:
        return any(re.search(p, msg) for p in OFF_TOPIC_PATTERNS)

    def _generate_action_response(self, state: ConversationState, message: str) -> ReplyResponse:
        """Generate an action-mode response after merchant commits."""
        merchant = self.store.get_merchant(state.merchant_id) or {}
        category = self.store.get_category_for_merchant(state.merchant_id) or {}

        conv_context = "\n".join(
            f"[{t['from']}] {t['body'][:150]}" for t in state.turns[-6:]
        )

        system = (
            "You are Vera. The merchant just COMMITTED to an action. "
            "DO NOT ask any more qualifying questions. Switch to ACTION MODE immediately. "
            "Tell them what you're doing right now: drafting, sending, scheduling, creating. "
            "Be specific about scope (how many patients/customers, what content, what timeline). "
            "End with a CONFIRM CTA. Respond with ONLY JSON: {\"body\": \"...\", \"cta\": \"binary_confirm_cancel\", \"rationale\": \"...\"}"
        )

        identity = merchant.get("identity", {})
        user = (
            f"Merchant: {identity.get('name', 'Unknown')} ({identity.get('owner_first_name', '')})\n"
            f"Conversation so far:\n{conv_context}\n\n"
            f"Merchant's latest message: \"{message}\"\n\n"
            "Switch to action mode NOW. No more questions."
        )

        try:
            raw = self.llm.complete(system, user)
            return self._parse_reply_response(raw)
        except Exception as e:
            logger.error(f"Action response LLM failed: {e}")
            return ReplyResponse(
                action="send",
                body="Got it — working on it now. I'll have the draft ready in 2 minutes. Stand by.",
                cta="none",
                rationale="Merchant committed; switching to action mode. LLM fallback."
            )

    def _handle_off_topic(self, state: ConversationState, message: str) -> ReplyResponse:
        """Handle off-topic requests by redirecting."""
        # Determine what the original topic was
        original_topic = state.trigger_id.split("_", 3)[-1] if state.trigger_id else "your profile"

        return ReplyResponse(
            action="send",
            body=f"I'll have to leave that to the right team — that's outside what I can help with directly. Coming back to our earlier topic — shall I continue?",
            cta="open_ended",
            rationale=f"Out-of-scope ask politely declined; redirecting back to original trigger without losing thread."
        )

    def _generate_continuation(self, state: ConversationState, message: str) -> ReplyResponse:
        """Generate a continuation response via LLM."""
        merchant = self.store.get_merchant(state.merchant_id) or {}
        category = self.store.get_category_for_merchant(state.merchant_id) or {}

        conv_context = "\n".join(
            f"[{t['from']}] {t['body'][:150]}" for t in state.turns[-6:]
        )

        system = (
            "You are Vera. Continue this conversation naturally. "
            "If the merchant asks a question, answer it from context. "
            "If they agree to something, execute it. "
            "If they're unsure, give ONE more reason and ask again. "
            "Keep it concise — this is WhatsApp. "
            "Respond with ONLY JSON: {\"body\": \"...\", \"cta\": \"open_ended | binary_yes_no | none\", \"rationale\": \"...\"}"
        )

        identity = merchant.get("identity", {})
        offers = [o.get("title") for o in merchant.get("offers", []) if o.get("status") == "active"]

        user = (
            f"Merchant: {identity.get('name', 'Unknown')} ({category.get('slug', '')})\n"
            f"Active offers: {offers}\n"
            f"Conversation:\n{conv_context}\n\n"
            f"Merchant's latest: \"{message}\"\n\nContinue naturally."
        )

        try:
            raw = self.llm.complete(system, user)
            return self._parse_reply_response(raw)
        except Exception as e:
            logger.error(f"Continuation LLM failed: {e}")
            return ReplyResponse(
                action="send",
                body="Got it, let me work on that. Anything else you'd like me to help with?",
                cta="open_ended",
                rationale="Continuation response — LLM fallback."
            )

    def _parse_reply_response(self, raw: str) -> ReplyResponse:
        """Parse LLM response into ReplyResponse."""
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return ReplyResponse(
                    action="send",
                    body=data.get("body", ""),
                    cta=data.get("cta", "open_ended"),
                    rationale=data.get("rationale", ""),
                )
            except json.JSONDecodeError:
                pass

        return ReplyResponse(
            action="send",
            body=raw.strip()[:500],
            cta="open_ended",
            rationale="Parsed from raw LLM output",
        )
