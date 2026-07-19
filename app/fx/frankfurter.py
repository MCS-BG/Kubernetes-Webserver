"""Free, no-API-key FX reference source, backed by the Frankfurter API
(https://frankfurter.dev), which republishes daily ECB reference rates.

This is the default provider so the platform works out of the box with zero
account setup. Swap to OANDA (or any other provider) by setting
FX_PROVIDER=oanda plus credentials -- the reconciliation engine code does
not change.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import requests

from app.fx.base import FXRateProvider

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


class FrankfurterFXProvider(FXRateProvider):
    def __init__(self, base_url: str = FRANKFURTER_BASE_URL, timeout: float = 10.0):
        self._base_url = base_url
        self._timeout = timeout
        self._cache: dict[tuple[str, str, date], Decimal] = {}

    def get_rate(self, base_currency: str, quote_currency: str, on_date: date) -> Decimal:
        key = (base_currency, quote_currency, on_date)
        if key in self._cache:
            return self._cache[key]

        url = f"{self._base_url}/{on_date.isoformat()}"
        resp = requests.get(
            url,
            params={"base": base_currency, "symbols": quote_currency},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        rate = Decimal(str(payload["rates"][quote_currency]))
        self._cache[key] = rate
        return rate
