"""Generic CSV/Excel adapter for ERP data migrations and one-off exports.

Column names are configurable per-source since every bank and every ERP
export uses different headers, but a sensible default mapping is provided
that matches common QuickBooks/Xero/NetSuite CSV export column names.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from app.ingestion.base import SourceAdapter
from app.models import BankTransaction, GLEntry, TrialBalanceLine

DEFAULT_BANK_COLUMNS = {
    "date": "date",
    "amount": "amount",
    "currency": "currency",
    "description": "description",
    "reference": "reference",
    "account": "account",
}

DEFAULT_GL_COLUMNS = {
    "date": "date",
    "amount": "amount",
    "currency": "currency",
    "account_code": "account_code",
    "account_name": "account_name",
    "description": "description",
    "reference": "reference",
}

DEFAULT_TRIAL_BALANCE_COLUMNS = {
    "account_code": "account_code",
    "account_name": "account_name",
    "debit": "debit",
    "credit": "credit",
}


def _read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _to_date(value):
    if hasattr(value, "date"):
        return value.date()
    return datetime.fromisoformat(str(value)).date()


class CSVExcelAdapter(SourceAdapter):
    """Reads bank/GL/trial-balance data from local CSV or Excel files.

    Used both for one-time ERP data migrations (client exports their books,
    we ingest a snapshot) and as a manual fallback when a live API
    integration isn't available yet for a given system.
    """

    name = "csv_excel"

    def __init__(
        self,
        bank_file: str | Path | None = None,
        gl_file: str | Path | None = None,
        trial_balance_file: str | Path | None = None,
        bank_columns: dict[str, str] | None = None,
        gl_columns: dict[str, str] | None = None,
        trial_balance_columns: dict[str, str] | None = None,
        default_currency: str = "USD",
    ):
        self._bank_file = bank_file
        self._gl_file = gl_file
        self._trial_balance_file = trial_balance_file
        self._bank_columns = bank_columns or DEFAULT_BANK_COLUMNS
        self._gl_columns = gl_columns or DEFAULT_GL_COLUMNS
        self._tb_columns = trial_balance_columns or DEFAULT_TRIAL_BALANCE_COLUMNS
        self._default_currency = default_currency

    def fetch_bank_transactions(self) -> list[BankTransaction]:
        if not self._bank_file:
            return []
        df = _read_table(self._bank_file)
        cols = self._bank_columns
        out = []
        for _, row in df.iterrows():
            out.append(
                BankTransaction(
                    date=_to_date(row[cols["date"]]),
                    amount=_to_decimal(row[cols["amount"]]),
                    currency=str(row.get(cols["currency"], self._default_currency) or self._default_currency),
                    description=str(row.get(cols["description"], "") or ""),
                    reference=str(row.get(cols["reference"], "") or ""),
                    account=str(row.get(cols["account"], "") or ""),
                    source_system=self.name,
                )
            )
        return out

    def fetch_gl_entries(self) -> list[GLEntry]:
        if not self._gl_file:
            return []
        df = _read_table(self._gl_file)
        cols = self._gl_columns
        out = []
        for _, row in df.iterrows():
            out.append(
                GLEntry(
                    date=_to_date(row[cols["date"]]),
                    amount=_to_decimal(row[cols["amount"]]),
                    currency=str(row.get(cols["currency"], self._default_currency) or self._default_currency),
                    account_code=str(row.get(cols["account_code"], "") or ""),
                    account_name=str(row.get(cols["account_name"], "") or ""),
                    description=str(row.get(cols["description"], "") or ""),
                    reference=str(row.get(cols["reference"], "") or ""),
                    source_system=self.name,
                )
            )
        return out

    def fetch_trial_balance(self) -> list[TrialBalanceLine]:
        if not self._trial_balance_file:
            return []
        df = _read_table(self._trial_balance_file)
        cols = self._tb_columns
        out = []
        for _, row in df.iterrows():
            out.append(
                TrialBalanceLine(
                    account_code=str(row[cols["account_code"]]),
                    account_name=str(row.get(cols["account_name"], "") or ""),
                    reported_debit=_to_decimal(row.get(cols["debit"], 0)),
                    reported_credit=_to_decimal(row.get(cols["credit"], 0)),
                )
            )
        return out
