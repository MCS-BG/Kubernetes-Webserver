"""Profit & loss (income statement) computation -- live from GL activity,
not a static report. Every figure is recomputed from the underlying
GLEntry records for the requested period each time this is called; there
is no cached/stale "last month's P&L" sitting around.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.coa import PL_ACCOUNT_TYPES, AccountType, CREDIT_NORMAL_TYPES, ChartOfAccounts
from app.models import GLEntry

_TYPE_TO_BUCKET = {
    AccountType.REVENUE: "revenue_lines",
    AccountType.COGS: "cogs_lines",
    AccountType.OPERATING_EXPENSE: "operating_expense_lines",
    AccountType.OTHER_INCOME: "other_income_lines",
    AccountType.OTHER_EXPENSE: "other_expense_lines",
}


@dataclass
class PLLine:
    account_code: str
    account_name: str
    amount: Decimal  # always a positive "natural" P&L number, regardless of debit/credit side


@dataclass
class ProfitAndLossReport:
    entity_id: str
    period_start: date
    period_end: date
    revenue_lines: list[PLLine] = field(default_factory=list)
    cogs_lines: list[PLLine] = field(default_factory=list)
    operating_expense_lines: list[PLLine] = field(default_factory=list)
    other_income_lines: list[PLLine] = field(default_factory=list)
    other_expense_lines: list[PLLine] = field(default_factory=list)
    # Account codes with GL activity in the period but no chart-of-accounts
    # entry. Never silently folded into a total -- a real classification
    # gap should show up as a visible flag, not a quietly wrong Net Income.
    unclassified_account_codes: list[str] = field(default_factory=list)

    @property
    def total_revenue(self) -> Decimal:
        return sum((l.amount for l in self.revenue_lines), Decimal("0"))

    @property
    def total_cogs(self) -> Decimal:
        return sum((l.amount for l in self.cogs_lines), Decimal("0"))

    @property
    def gross_profit(self) -> Decimal:
        return self.total_revenue - self.total_cogs

    @property
    def total_operating_expenses(self) -> Decimal:
        return sum((l.amount for l in self.operating_expense_lines), Decimal("0"))

    @property
    def operating_income(self) -> Decimal:
        return self.gross_profit - self.total_operating_expenses

    @property
    def total_other_income(self) -> Decimal:
        return sum((l.amount for l in self.other_income_lines), Decimal("0"))

    @property
    def total_other_expense(self) -> Decimal:
        return sum((l.amount for l in self.other_expense_lines), Decimal("0"))

    @property
    def net_income(self) -> Decimal:
        return self.operating_income + self.total_other_income - self.total_other_expense


def compute_profit_and_loss(
    gl_entries: list[GLEntry],
    chart_of_accounts: ChartOfAccounts,
    entity_id: str,
    period_start: date,
    period_end: date,
) -> ProfitAndLossReport:
    totals: dict[str, tuple[Decimal, str]] = {}
    for entry in gl_entries:
        if not (period_start <= entry.date <= period_end):
            continue
        signed_sum, name = totals.get(entry.account_code, (Decimal("0"), ""))
        totals[entry.account_code] = (signed_sum + entry.amount, name or entry.account_name)

    report = ProfitAndLossReport(entity_id=entity_id, period_start=period_start, period_end=period_end)

    for account_code, (signed_sum, account_name) in sorted(totals.items()):
        coa_entry = chart_of_accounts.get(entity_id, account_code)
        if coa_entry is None:
            report.unclassified_account_codes.append(account_code)
            continue
        if coa_entry.account_type not in PL_ACCOUNT_TYPES:
            continue  # balance-sheet account (asset/liability/equity) -- not part of a P&L

        natural_amount = -signed_sum if coa_entry.account_type in CREDIT_NORMAL_TYPES else signed_sum
        line = PLLine(
            account_code=account_code,
            account_name=coa_entry.account_name or account_name,
            amount=natural_amount,
        )
        getattr(report, _TYPE_TO_BUCKET[coa_entry.account_type]).append(line)

    return report
