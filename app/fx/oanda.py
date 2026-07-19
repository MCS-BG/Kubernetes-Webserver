"""OANDA Exchange Rates provider.

Requires an OANDA account and API key (OANDA_API_KEY). Implements the same
FXRateProvider interface as the free Frankfurter provider, so it is a
drop-in replacement once a client wants OANDA as the reference source
instead of ECB rates.

NOTE: OANDA's rates API is a paid product; this class talks to the
standard `/v2/rates/{quote}/{date}.json`-style historical endpoint. Adjust
`_base_url` if your OANDA plan uses a different host/version.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import requests

from app.config import settings
from app.fx.base import FXRateProvider


class OandaFXProvider(FXRateProvider):
    def __init__(self, api_key: str | None = None, base_url: str = "https://exchange-rates-api.oanda.com/v2"):
        self._api_key = api_key or settings.oanda_api_key
        if not self._api_key:
            raise ValueError(
                "OANDA_API_KEY is required to use OandaFXProvider. "
                "Set it in the environment or pass api_key explicitly."
            )
        self._base_url = base_url
        self._cache: dict[tuple[str, str, date], Decimal] = {}

    def get_rate(self, base_currency: str, quote_currency: str, on_date: date) -> Decimal:
        key = (base_currency, quote_currency, on_date)
        if key in self._cache:
            return self._cache[key]

        resp = requests.get(
            f"{self._base_url}/rates/spot.json",
            params={
                "base": base_currency,
                "quote": quote_currency,
                "date": on_date.isoformat(),
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        rate = Decimal(str(payload["quotes"][0]["ask"]))
        self._cache[key] = rate
        return rate
