"""Chart of accounts: classifies each GL account into a P&L/balance-sheet
category. Needed because GLEntry only carries an account_code/account_name
-- to compute a profit & loss statement we need to know whether account
"4000" is revenue, COGS, or an operating expense, and that mapping is
entity-specific (every client's chart of accounts is different).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccountType(str, Enum):
    REVENUE = "revenue"
    COGS = "cogs"
    OPERATING_EXPENSE = "operating_expense"
    OTHER_INCOME = "other_income"
    OTHER_EXPENSE = "other_expense"
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"


# Account types whose natural balance is a credit (increases with negative
# signed amounts in this codebase's positive-debit/negative-credit
# convention) -- revenue, other income, liabilities, and equity. Needed to
# present P&L amounts as positive numbers regardless of which side of the
# ledger they post to.
CREDIT_NORMAL_TYPES = {
    AccountType.REVENUE,
    AccountType.OTHER_INCOME,
    AccountType.LIABILITY,
    AccountType.EQUITY,
}

# The account types a profit & loss statement covers. Asset/liability/equity
# accounts are balance-sheet accounts and are deliberately excluded from
# P&L computation.
PL_ACCOUNT_TYPES = {
    AccountType.REVENUE,
    AccountType.COGS,
    AccountType.OPERATING_EXPENSE,
    AccountType.OTHER_INCOME,
    AccountType.OTHER_EXPENSE,
}


@dataclass
class ChartOfAccountsEntry:
    account_code: str
    account_name: str
    account_type: AccountType


class ChartOfAccounts:
    def __init__(self):
        self._entries: dict[str, dict[str, ChartOfAccountsEntry]] = {}

    def set_account(
        self, entity_id: str, account_code: str, account_name: str, account_type: AccountType
    ) -> ChartOfAccountsEntry:
        entry = ChartOfAccountsEntry(
            account_code=account_code, account_name=account_name, account_type=account_type
        )
        self._entries.setdefault(entity_id, {})[account_code] = entry
        return entry

    def get(self, entity_id: str, account_code: str) -> ChartOfAccountsEntry | None:
        return self._entries.get(entity_id, {}).get(account_code)

    def accounts_for(self, entity_id: str) -> list[ChartOfAccountsEntry]:
        return list(self._entries.get(entity_id, {}).values())


chart_of_accounts = ChartOfAccounts()
