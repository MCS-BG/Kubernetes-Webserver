from __future__ import annotations

from pydantic import BaseModel


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
