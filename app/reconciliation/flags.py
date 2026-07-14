"""Cross-cutting flagging rules that aren't part of the core bank/GL match
or trial-balance tie-out passes. Currently: currency mismatch detection
against an independent FX reference source.
"""
from __future__ import annotations

from decimal import Decimal

from app.config import settings as default_settings
from app.fx.base import FXRateProvider
from app.models import Flag, FlagSeverity, FlagType, GLEntry


def check_fx_rates(
    gl_entries: list[GLEntry],
    fx_provider: FXRateProvider,
    base_currency: str | None = None,
    tolerance_bps: int | None = None,
) -> list[Flag]:
    """Flags GL entries whose booked FX conversion rate deviates from the
    independent reference rate (OANDA, ECB/Frankfurter, or whichever
    provider is configured) by more than the allowed tolerance in basis
    points. Catches stale rates, wrong currency pairs, and manual posting
    errors on multi-currency entries.
    """
    base_currency = base_currency or default_settings.base_currency
    tolerance_bps = (
        tolerance_bps if tolerance_bps is not None else default_settings.fx_mismatch_tolerance_bps
    )

    flags: list[Flag] = []
    for entry in gl_entries:
        if entry.currency == base_currency or entry.booked_fx_rate is None:
            continue

        reference_rate = fx_provider.get_rate(entry.currency, base_currency, entry.date)
        if reference_rate == 0:
            continue

        variance_bps = abs(entry.booked_fx_rate - reference_rate) / reference_rate * Decimal(10000)
        if variance_bps <= tolerance_bps:
            continue

        severity = FlagSeverity.CRITICAL if variance_bps > tolerance_bps * 4 else FlagSeverity.WARNING
        flags.append(
            Flag(
                type=FlagType.FX_RATE_MISMATCH,
                severity=severity,
                message=(
                    f"{entry.account_name or entry.account_code}: entry booked "
                    f"{entry.currency}->{base_currency} at {entry.booked_fx_rate}, reference rate "
                    f"was {reference_rate} ({variance_bps:.1f} bps variance)"
                ),
                entry_ids=[entry.id],
                details={
                    "currency": entry.currency,
                    "base_currency": base_currency,
                    "booked_rate": str(entry.booked_fx_rate),
                    "reference_rate": str(reference_rate),
                    "variance_bps": str(variance_bps),
                },
            )
        )
    return flags
