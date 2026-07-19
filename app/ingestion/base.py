"""Common interface every data source (SaaS finance app, ERP export, CSV
migration) implements. The reconciliation engine only depends on this
interface, so a new source is a new adapter, never a change to the engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import BankTransaction, GLEntry, TrialBalanceLine


class SourceAdapter(ABC):
    """One connected data source: a bank feed + a general ledger + a trial balance."""

    name: str = "base"

    @abstractmethod
    def fetch_bank_transactions(self) -> list[BankTransaction]:
        raise NotImplementedError

    @abstractmethod
    def fetch_gl_entries(self) -> list[GLEntry]:
        raise NotImplementedError

    @abstractmethod
    def fetch_trial_balance(self) -> list[TrialBalanceLine]:
        raise NotImplementedError


class NotYetImplementedAdapter(SourceAdapter):
    """Base for adapters that define the connection shape but need real
    credentials/API access to go live. Raising a clear error here is
    preferable to silently returning empty data.
    """

    def fetch_bank_transactions(self) -> list[BankTransaction]:
        raise NotImplementedError(f"{self.name}: live bank feed sync not yet implemented")

    def fetch_gl_entries(self) -> list[GLEntry]:
        raise NotImplementedError(f"{self.name}: live GL sync not yet implemented")

    def fetch_trial_balance(self) -> list[TrialBalanceLine]:
        raise NotImplementedError(f"{self.name}: live trial balance sync not yet implemented")
