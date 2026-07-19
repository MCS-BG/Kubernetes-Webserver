"""Domain model for the month-end close workflow: an explicit state machine
per legal entity + period, so "why hasn't month-end closed" has a real,
queryable answer instead of living only in someone's head or inbox.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum

from app.models import new_id


class CloseStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class CloseTransition:
    """One state change in a close period's history -- the append-only
    record that answers "who moved this, when, and why" (same idea as
    app.security.audit.AuditLog, scoped to a single close period)."""

    id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str = ""
    from_status: CloseStatus = CloseStatus.NOT_STARTED
    to_status: CloseStatus = CloseStatus.NOT_STARTED
    note: str = ""


@dataclass
class ClosePeriod:
    id: str = field(default_factory=new_id)
    entity_id: str = ""
    period_start: date = None
    period_end: date = None
    status: CloseStatus = CloseStatus.NOT_STARTED
    # The reconciliation run this close was last submitted against -- lets a
    # blocked/rejected close point back at exactly which exceptions to fix.
    reconciliation_id: str | None = None
    prepared_by: str | None = None
    reviewed_by: str | None = None
    rejection_reason: str | None = None
    history: list[CloseTransition] = field(default_factory=list)
