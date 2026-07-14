from datetime import date, timedelta
from decimal import Decimal

from app.models import BankTransaction, FlagType, GLEntry
from app.reconciliation.matcher import match_transactions


def test_exact_match():
    bank = [BankTransaction(date=date(2026, 6, 30), amount=Decimal("1000.00"), currency="USD", reference="INV-1")]
    gl = [GLEntry(date=date(2026, 6, 30), amount=Decimal("1000.00"), currency="USD", account_code="1000", reference="INV-1")]

    result = match_transactions(bank, gl)

    assert len(result.matched_pairs) == 1
    assert result.matched_pairs[0].method == "exact"
    assert not result.unmatched_bank_ids
    assert not result.unmatched_gl_ids


def test_date_window_match():
    bank = [BankTransaction(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD")]
    gl = [GLEntry(date=date(2026, 6, 28), amount=Decimal("500.00"), currency="USD", account_code="1000")]

    result = match_transactions(bank, gl, date_window_days=3)

    assert len(result.matched_pairs) == 1
    assert result.matched_pairs[0].method == "date_window"


def test_no_match_outside_window_and_amount():
    bank = [BankTransaction(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD")]
    gl = [GLEntry(date=date(2026, 6, 1), amount=Decimal("999.00"), currency="USD", account_code="1000")]

    result = match_transactions(bank, gl, date_window_days=3)

    assert result.matched_pairs == []
    assert result.unmatched_bank_ids == [bank[0].id]
    assert result.unmatched_gl_ids == [gl[0].id]
    flag_types = {f.type for f in result.flags}
    assert FlagType.UNMATCHED_BANK in flag_types
    assert FlagType.UNMATCHED_GL in flag_types


def test_fuzzy_description_match_outside_date_window():
    bank = [
        BankTransaction(
            date=date(2026, 6, 30),
            amount=Decimal("250.00"),
            currency="USD",
            description="ACME CORP PAYMENT",
        )
    ]
    gl = [
        GLEntry(
            date=date(2026, 5, 1),  # far outside any reasonable date window
            amount=Decimal("250.00"),
            currency="USD",
            account_code="4000",
            description="Acme Corp Payment",
        )
    ]

    result = match_transactions(bank, gl, date_window_days=3)

    assert len(result.matched_pairs) == 1
    assert result.matched_pairs[0].method == "fuzzy_description"


def test_amount_mismatch_flagged_for_same_day_similar_description():
    bank = [
        BankTransaction(
            date=date(2026, 6, 30),
            amount=Decimal("1200.00"),
            currency="USD",
            description="VENDOR X INVOICE 42",
        )
    ]
    gl = [
        GLEntry(
            date=date(2026, 6, 30),
            amount=Decimal("1150.00"),
            currency="USD",
            account_code="2000",
            description="Vendor X Invoice 42",
        )
    ]

    result = match_transactions(bank, gl, date_window_days=3)

    assert result.matched_pairs == []
    amount_mismatch_flags = [f for f in result.flags if f.type == FlagType.AMOUNT_MISMATCH]
    assert len(amount_mismatch_flags) == 1
    assert amount_mismatch_flags[0].details["difference"] == "50.00"


def test_duplicate_bank_transactions_flagged():
    txn_date = date(2026, 6, 30)
    bank = [
        BankTransaction(date=txn_date, amount=Decimal("100.00"), currency="USD", description="Coffee shop"),
        BankTransaction(date=txn_date, amount=Decimal("100.00"), currency="USD", description="Coffee shop"),
    ]

    result = match_transactions(bank, [])

    duplicate_flags = [f for f in result.flags if f.type == FlagType.DUPLICATE_TRANSACTION]
    assert len(duplicate_flags) == 1
