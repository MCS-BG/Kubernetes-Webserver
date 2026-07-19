from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.coa import AccountType


class ChartOfAccountsEntryRequest(BaseModel):
    account_code: str
    account_name: str
    account_type: AccountType


class FeedbackRequest(BaseModel):
    reconciliation_id: str
    flag_index: int
    match_text: str
    note: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ReconciliationRequest(BaseModel):
    source_id: str
    date_window_days: int | None = None
    amount_tolerance: str | None = None
    fuzzy_threshold: float | None = None
    check_fx: bool = True
    base_currency: str | None = None
    # GL account code(s) that represent the actual bank/cash account(s) this
    # feed belongs to. Strongly recommended: without it, matching runs
    # against every GL account, which can produce false matches against an
    # unrelated expense/revenue leg that happens to share the same amount.
    cash_account_codes: list[str] | None = None


class StartCloseRequest(BaseModel):
    entity_id: str
    period_start: date
    period_end: date


class SubmitCloseRequest(BaseModel):
    close_id: str
    reconciliation_id: str


class ApproveCloseRequest(BaseModel):
    close_id: str


class RejectCloseRequest(BaseModel):
    close_id: str
    reason: str
