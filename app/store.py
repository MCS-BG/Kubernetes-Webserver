"""In-memory persistence for the MVP.

Deliberately not a database: this scaffold is about proving out the
ingestion -> reconciliation -> exceptions pipeline. Swap this module for a
Postgres-backed store (sources, reconciliation_runs, flags tables) before
running this against real client data across multiple processes/restarts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import BankTransaction, GLEntry, ReconciliationResult, TrialBalanceLine, TrialBalanceTieOut, new_id


@dataclass
class SourceData:
    id: str
    bank_transactions: list[BankTransaction] = field(default_factory=list)
    gl_entries: list[GLEntry] = field(default_factory=list)
    trial_balance: list[TrialBalanceLine] = field(default_factory=list)


class InMemoryStore:
    def __init__(self):
        self.sources: dict[str, SourceData] = {}
        self.results: dict[str, ReconciliationResult] = {}
        self.tie_outs: dict[str, list[TrialBalanceTieOut]] = {}

    def add_source(
        self,
        bank: list[BankTransaction],
        gl: list[GLEntry],
        trial_balance: list[TrialBalanceLine],
    ) -> str:
        source_id = new_id()
        self.sources[source_id] = SourceData(
            id=source_id, bank_transactions=bank, gl_entries=gl, trial_balance=trial_balance
        )
        return source_id


store = InMemoryStore()
