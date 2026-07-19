from datetime import date
from decimal import Decimal

from app.fx.base import FXRateProvider
from app.models import FlagType, GLEntry
from app.reconciliation.flags import check_fx_rates


class FakeFXProvider(FXRateProvider):
    """Deterministic reference rate for tests -- no network calls."""

    def __init__(self, rate: Decimal):
        self._rate = rate

    def get_rate(self, base_currency: str, quote_currency: str, on_date: date) -> Decimal:
        return self._rate


def test_no_flag_when_booked_rate_within_tolerance():
    gl = [
        GLEntry(
            date=date(2026, 6, 30),
            amount=Decimal("1000.00"),
            currency="EUR",
            account_code="1000",
            booked_fx_rate=Decimal("1.0800"),
        )
    ]
    provider = FakeFXProvider(rate=Decimal("1.0805"))  # ~4.6 bps off

    flags = check_fx_rates(gl, provider, base_currency="USD", tolerance_bps=50)

    assert flags == []


def test_flag_when_booked_rate_diverges_beyond_tolerance():
    gl = [
        GLEntry(
            date=date(2026, 6, 30),
            amount=Decimal("1000.00"),
            currency="EUR",
            account_code="1000",
            account_name="Intercompany Receivable",
            booked_fx_rate=Decimal("1.1500"),  # booked at a stale/wrong rate
        )
    ]
    provider = FakeFXProvider(rate=Decimal("1.0800"))  # ~648 bps off

    flags = check_fx_rates(gl, provider, base_currency="USD", tolerance_bps=50)

    assert len(flags) == 1
    assert flags[0].type == FlagType.FX_RATE_MISMATCH
    assert flags[0].details["booked_rate"] == "1.1500"
    assert flags[0].details["reference_rate"] == "1.0800"


def test_no_flag_when_currency_matches_base():
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("1000.00"), currency="USD", account_code="1000")
    ]
    provider = FakeFXProvider(rate=Decimal("1.0"))

    flags = check_fx_rates(gl, provider, base_currency="USD")

    assert flags == []


def test_no_flag_when_no_booked_rate_recorded():
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("1000.00"), currency="EUR", account_code="1000")
    ]
    provider = FakeFXProvider(rate=Decimal("1.08"))

    flags = check_fx_rates(gl, provider, base_currency="USD")

    assert flags == []
