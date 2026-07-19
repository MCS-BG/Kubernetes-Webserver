from datetime import date
from decimal import Decimal

from app.models import FlagType, GLEntry, TrialBalanceLine
from app.reconciliation.trial_balance import tie_out


def test_account_ties_out_within_tolerance():
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account_code="1000", account_name="Cash"),
        GLEntry(date=date(2026, 6, 30), amount=Decimal("-500.00"), currency="USD", account_code="4000", account_name="Revenue"),
    ]
    reported = [
        TrialBalanceLine(account_code="1000", account_name="Cash", reported_debit=Decimal("500.00"), reported_credit=Decimal("0")),
        TrialBalanceLine(account_code="4000", account_name="Revenue", reported_debit=Decimal("0"), reported_credit=Decimal("500.00")),
    ]

    results, flags = tie_out(gl, reported)

    assert all(r.tied_out for r in results)
    assert flags == []


def test_account_mismatch_flagged():
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account_code="1000", account_name="Cash"),
    ]
    reported = [
        TrialBalanceLine(account_code="1000", account_name="Cash", reported_debit=Decimal("475.00"), reported_credit=Decimal("0")),
    ]

    results, flags = tie_out(gl, reported)

    assert results[0].tied_out is False
    tie_out_flags = [f for f in flags if f.type == FlagType.ACCOUNT_TIE_OUT_MISMATCH]
    assert len(tie_out_flags) == 1
    assert tie_out_flags[0].details["debit_variance"] == "25.00"


def test_ledger_out_of_balance_flagged():
    # Debits and credits across the whole ledger don't net to zero.
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account_code="1000"),
        GLEntry(date=date(2026, 6, 30), amount=Decimal("-400.00"), currency="USD", account_code="4000"),
    ]

    results, flags = tie_out(gl, [])

    out_of_balance_flags = [f for f in flags if f.type == FlagType.TRIAL_BALANCE_OUT_OF_BALANCE]
    assert len(out_of_balance_flags) == 1
