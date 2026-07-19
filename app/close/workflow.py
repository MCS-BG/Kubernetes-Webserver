"""Month-end close workflow: tracks each legal entity's close status per
period through an explicit state machine, rather than as tribal knowledge.

    not_started -> in_progress -> pending_review -> approved
                                                   -> rejected -> (resubmit) -> pending_review

Submitting for review is blocked while any CRITICAL flag on the linked
reconciliation run is still open -- the same signal Ledge already computes,
now gating the workflow instead of just being visible in isolation. That
gate is the concrete answer to "why didn't month-end close": either it was
never started, it's sitting in someone's queue, or it's blocked by N
unresolved critical exceptions on a specific reconciliation run.

Segregation of duties (reviewer != preparer) is deliberately NOT enforced
here -- this store only tracks state, it has no notion of "the current
caller." That check belongs at the API layer, exactly like /feedback
already does it (see app/api/routes.py), so this module stays testable
without an HTTP request or auth context.
"""
from __future__ import annotations

from datetime import date

from app.close.models import ClosePeriod, CloseStatus, CloseTransition
from app.models import FlagSeverity, ReconciliationResult


class CloseWorkflowError(Exception):
    """Raised for an invalid state transition or a blocked readiness gate."""


class CloseWorkflowStore:
    def __init__(self):
        self._periods: dict[str, ClosePeriod] = {}

    def get(self, close_id: str) -> ClosePeriod | None:
        return self._periods.get(close_id)

    def find(self, entity_id: str, period_start: date, period_end: date) -> ClosePeriod | None:
        for period in self._periods.values():
            if (
                period.entity_id == entity_id
                and period.period_start == period_start
                and period.period_end == period_end
            ):
                return period
        return None

    def list_for_entity(self, entity_id: str) -> list[ClosePeriod]:
        return [p for p in self._periods.values() if p.entity_id == entity_id]

    def start(self, entity_id: str, period_start: date, period_end: date, actor: str) -> ClosePeriod:
        """Idempotent: re-calling for the same entity+period returns the
        existing period untouched, whatever status it's already in."""
        existing = self.find(entity_id, period_start, period_end)
        if existing:
            return existing
        period = ClosePeriod(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            status=CloseStatus.IN_PROGRESS,
        )
        period.history.append(
            CloseTransition(
                actor=actor, from_status=CloseStatus.NOT_STARTED, to_status=CloseStatus.IN_PROGRESS
            )
        )
        self._periods[period.id] = period
        return period

    def submit_for_review(
        self,
        close_id: str,
        reconciliation_id: str,
        result: ReconciliationResult,
        actor: str,
    ) -> ClosePeriod:
        period = self._require(close_id)
        if period.status not in (CloseStatus.IN_PROGRESS, CloseStatus.REJECTED):
            raise CloseWorkflowError(
                f"Cannot submit for review from status '{period.status.value}' -- "
                "must be in_progress or rejected."
            )
        # Record which run this submission attempt is against *before* the
        # gate check below -- so a blocked attempt still leaves a pointer a
        # status check (including the chat tool) can use to explain why.
        period.reconciliation_id = reconciliation_id
        open_critical = [f for f in result.flags if f.severity == FlagSeverity.CRITICAL]
        if open_critical:
            raise CloseWorkflowError(
                f"{len(open_critical)} unresolved critical exception(s) on this reconciliation "
                "-- resolve or suppress them (see POST /feedback) before submitting for review."
            )
        self._transition(period, CloseStatus.PENDING_REVIEW, actor)
        period.prepared_by = actor
        period.rejection_reason = None
        return period

    def approve(self, close_id: str, actor: str) -> ClosePeriod:
        period = self._require(close_id)
        if period.status != CloseStatus.PENDING_REVIEW:
            raise CloseWorkflowError(
                f"Cannot approve from status '{period.status.value}' -- must be pending_review."
            )
        self._transition(period, CloseStatus.APPROVED, actor)
        period.reviewed_by = actor
        return period

    def reject(self, close_id: str, actor: str, reason: str) -> ClosePeriod:
        period = self._require(close_id)
        if period.status != CloseStatus.PENDING_REVIEW:
            raise CloseWorkflowError(
                f"Cannot reject from status '{period.status.value}' -- must be pending_review."
            )
        self._transition(period, CloseStatus.REJECTED, actor, note=reason)
        period.reviewed_by = actor
        period.rejection_reason = reason
        return period

    def _transition(
        self, period: ClosePeriod, to_status: CloseStatus, actor: str, note: str = ""
    ) -> None:
        period.history.append(
            CloseTransition(actor=actor, from_status=period.status, to_status=to_status, note=note)
        )
        period.status = to_status

    def _require(self, close_id: str) -> ClosePeriod:
        period = self._periods.get(close_id)
        if not period:
            raise CloseWorkflowError(f"No close period found with id {close_id}")
        return period


close_workflow = CloseWorkflowStore()
