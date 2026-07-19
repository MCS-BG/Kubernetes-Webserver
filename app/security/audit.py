"""Immutable audit trail: who did what, when, to which entity's data.

This is a SOX-aligned control (internal controls over financial
reporting expect a traceable record of who ran or approved a close-related
action), not a claim of SOX certification -- that requires an actual audit
engagement, not code. See COMPLIANCE.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models import new_id
from app.security.pii import mask_account_number


@dataclass(frozen=True)
class AuditEntry:
    id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str = ""
    action: str = ""
    entity_id: str | None = None
    details: dict = field(default_factory=dict)


def _sanitize(details: dict) -> dict:
    return {
        key: (mask_account_number(value) if isinstance(value, str) else value)
        for key, value in details.items()
    }


class AuditLog:
    """Append-only by design: there is deliberately no update or delete
    method. If an entry needs to be corrected, record a new entry that
    references it -- never mutate history.
    """

    def __init__(self):
        self._entries: list[AuditEntry] = []

    def record(
        self,
        actor: str,
        action: str,
        entity_id: str | None = None,
        details: dict | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            actor=actor, action=action, entity_id=entity_id, details=_sanitize(details or {})
        )
        self._entries.append(entry)
        return entry

    def list(self, entity_id: str | None = None) -> list[AuditEntry]:
        if entity_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.entity_id == entity_id]


audit_log = AuditLog()
