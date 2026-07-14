"""Core domain models for the reconciliation platform."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


@dataclass
class BankTransaction:
    """A single line from a bank statement / feed."""

    id: str = field(default_factory=new_id)
    date: date = None
    amount: Decimal = Decimal("0")
    currency: str = "USD"
    description: str = ""
    reference: str = ""
    account: str = ""
    source_system: str = "csv"


@dataclass
class GLEntry:
    """A single journal/ledger line from the accounting system."""

    id: str = field(default_factory=new_id)
    date: date = None
    amount: Decimal = Decimal("0")  # signed: positive = debit, negative = credit
    currency: str = "USD"
    account_code: str = ""
    account_name: str = ""
    description: str = ""
    reference: str = ""
    source_system: str = "csv"
    # Rate actually used to post this entry to the base/functional currency,
    # expressed as units of base currency per 1 unit of `currency`. Only set
    # for multi-currency entries; used to detect FX posting errors against
    # an independent reference rate (see app.reconciliation.flags).
    booked_fx_rate: Optional[Decimal] = None


@dataclass
class TrialBalanceLine:
    """One account's reported ending balance, as exported from the ERP/GL."""

    account_code: str
    account_name: str
    reported_debit: Decimal = Decimal("0")
    reported_credit: Decimal = Decimal("0")


class FlagType(str, Enum):
    UNMATCHED_BANK = "unmatched_bank"
    UNMATCHED_GL = "unmatched_gl"
    AMOUNT_MISMATCH = "amount_mismatch"
    DUPLICATE_TRANSACTION = "duplicate_transaction"
    FX_RATE_MISMATCH = "fx_rate_mismatch"
    ACCOUNT_TIE_OUT_MISMATCH = "account_tie_out_mismatch"
    TRIAL_BALANCE_OUT_OF_BALANCE = "trial_balance_out_of_balance"


class FlagSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Flag:
    """A single reviewable exception surfaced by the engine."""

    type: FlagType
    severity: FlagSeverity
    message: str
    entry_ids: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


@dataclass
class MatchedPair:
    bank_txn_id: str
    gl_entry_id: str
    confidence: float
    method: str  # e.g. "exact", "date_window", "fuzzy_description"


@dataclass
class ReconciliationResult:
    id: str = field(default_factory=new_id)
    matched_pairs: list[MatchedPair] = field(default_factory=list)
    unmatched_bank_ids: list[str] = field(default_factory=list)
    unmatched_gl_ids: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    def summary(self) -> dict:
        by_severity: dict[str, int] = {}
        for f in self.flags:
            by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1
        return {
            "matched": len(self.matched_pairs),
            "unmatched_bank": len(self.unmatched_bank_ids),
            "unmatched_gl": len(self.unmatched_gl_ids),
            "flags_total": len(self.flags),
            "flags_by_severity": by_severity,
        }


@dataclass
class TrialBalanceTieOut:
    account_code: str
    account_name: str
    computed_debit: Decimal
    computed_credit: Decimal
    reported_debit: Decimal
    reported_credit: Decimal
    debit_variance: Decimal
    credit_variance: Decimal
    tied_out: bool
