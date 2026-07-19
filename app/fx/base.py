"""Pluggable FX rate provider interface.

Any currency reference source (OANDA, Open Exchange Rates, ECB/Frankfurter,
XE, a client's own treasury rate table) implements this interface. The
reconciliation engine only ever depends on `FXRateProvider`, never on a
specific vendor, so swapping providers is a config change, not a code change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


class FXRateProvider(ABC):
    @abstractmethod
    def get_rate(self, base_currency: str, quote_currency: str, on_date: date) -> Decimal:
        """Return units of quote_currency per 1 unit of base_currency on the given date."""
        raise NotImplementedError

    def convert(
        self, amount: Decimal, from_currency: str, to_currency: str, on_date: date
    ) -> Decimal:
        if from_currency == to_currency:
            return amount
        rate = self.get_rate(from_currency, to_currency, on_date)
        return amount * rate
