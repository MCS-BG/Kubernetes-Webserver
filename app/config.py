"""Application settings, loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _decimal_env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # Reconciliation matching tolerances
    match_date_window_days: int = int(os.environ.get("MATCH_DATE_WINDOW_DAYS", "3"))
    match_amount_tolerance: str = _decimal_env("MATCH_AMOUNT_TOLERANCE", "0.01")
    fuzzy_description_threshold: float = float(
        os.environ.get("FUZZY_DESCRIPTION_THRESHOLD", "0.6")
    )

    # Trial balance tie-out tolerance (absolute currency units)
    tie_out_tolerance: str = _decimal_env("TIE_OUT_TOLERANCE", "0.01")

    # FX
    fx_provider: str = os.environ.get("FX_PROVIDER", "frankfurter")  # or "oanda"
    fx_mismatch_tolerance_bps: int = int(os.environ.get("FX_MISMATCH_TOLERANCE_BPS", "50"))
    oanda_api_key: str | None = os.environ.get("OANDA_API_KEY")
    oanda_account_id: str | None = os.environ.get("OANDA_ACCOUNT_ID")
    base_currency: str = os.environ.get("BASE_CURRENCY", "USD")


settings = Settings()
