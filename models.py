"""
Pydantic models for all API request/response contracts.
Matches the judge harness specification from challenge-testing-brief.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from enum import Enum
from pydantic import BaseModel, Field

class CTAEnum(str, Enum):
    BINARY_YES_NO = "binary_yes_no"
    OPEN_ENDED = "open_ended"
    NONE = "none"
    BINARY_CONFIRM_CANCEL = "binary_confirm_cancel"
    MULTI_CHOICE_SLOT = "multi_choice_slot"

# ── /v1/context ──────────────────────────────────────────────────────────────

class ContextPushRequest(BaseModel):
    scope: str  # "category" | "merchant" | "customer" | "trigger"
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class ContextPushAccepted(BaseModel):
    accepted: bool = True
    ack_id: str
    stored_at: str


class ContextPushRejected(BaseModel):
    accepted: bool = False
    reason: str
    current_version: Optional[int] = None
    details: Optional[str] = None


# ── /v1/tick ─────────────────────────────────────────────────────────────────

class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: str  # "vera" | "merchant_on_behalf"
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: CTAEnum
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction] = Field(default_factory=list)


# ── /v1/reply ────────────────────────────────────────────────────────────────

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str  # "merchant" | "customer"
    message: str
    received_at: str
    turn_number: int


class ReplyResponse(BaseModel):
    action: str  # "send" | "wait" | "end"
    body: Optional[str] = None
    cta: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: str = ""


# ── /v1/healthz ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int = 0
    contexts_loaded: dict[str, int] = Field(default_factory=dict)


# ── /v1/metadata ─────────────────────────────────────────────────────────────

class MetadataResponse(BaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str


# ── Internal: compose() output ───────────────────────────────────────────────

class ComposedMessage(BaseModel):
    body: str
    cta: CTAEnum
    send_as: str
    suppression_key: str
    rationale: str
    template_name: str = "vera_generic_v1"
    template_params: list[str] = Field(default_factory=list)
