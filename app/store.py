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
    entity_id: str | None = None


class InMemoryStore:
    def __init__(self):
        self.sources: dict[str, SourceData] = {}
        self.results: dict[str, ReconciliationResult] = {}
        self.tie_outs: dict[str, list[TrialBalanceTieOut]] = {}
        # reconciliation_id -> entity_id, so feedback on a flag knows which
        # entity's skill file to update.
        self.result_entity: dict[str, str | None] = {}
        # reconciliation_id -> actor who ran it, so /feedback can enforce
        # segregation of duties (reviewer != preparer).
        self.result_actor: dict[str, str] = {}

    def add_source(
        self,
        bank: list[BankTransaction],
        gl: list[GLEntry],
        trial_balance: list[TrialBalanceLine],
        entity_id: str | None = None,
    ) -> str:
        source_id = new_id()
        self.sources[source_id] = SourceData(
            id=source_id,
            bank_transactions=bank,
            gl_entries=gl,
            trial_balance=trial_balance,
            entity_id=entity_id,
        )
        return source_id

    def sources_for_entity(self, entity_id: str) -> list[SourceData]:
        return [s for s in self.sources.values() if s.entity_id == entity_id]

    def gl_entries_for_entity(self, entity_id: str) -> list[GLEntry]:
        """All GL activity across every source ever uploaded/synced for this
        entity -- a period-based report (like a P&L) needs the full ledger
        for the period, not just the most recently uploaded batch.
        """
        entries: list[GLEntry] = []
        for source in self.sources_for_entity(entity_id):
            entries.extend(source.gl_entries)
        return entries


store = InMemoryStore()
