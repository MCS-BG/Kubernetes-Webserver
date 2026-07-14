from datetime import date
from decimal import Decimal

from app.coa import AccountType, ChartOfAccounts
from app.models import GLEntry
from app.reporting.profit_and_loss import compute_profit_and_loss


def _coa_with_standard_accounts(entity_id: str) -> ChartOfAccounts:
    coa = ChartOfAccounts()
    coa.set_account(entity_id, "4000", "Revenue", AccountType.REVENUE)
    coa.set_account(entity_id, "5000", "Cost of Goods Sold", AccountType.COGS)
    coa.set_account(entity_id, "6100", "Facilities Expense", AccountType.OPERATING_EXPENSE)
    coa.set_account(entity_id, "6200", "Software Expense", AccountType.OPERATING_EXPENSE)
    coa.set_account(entity_id, "7000", "Interest Income", AccountType.OTHER_INCOME)
    coa.set_account(entity_id, "7100", "Interest Expense", AccountType.OTHER_EXPENSE)
    coa.set_account(entity_id, "1000", "Cash", AccountType.ASSET)
    return coa


def test_basic_pl_math():
    entity_id = "e1"
    coa = _coa_with_standard_accounts(entity_id)
    gl = [
        GLEntry(date=date(2026, 6, 15), amount=Decimal("-20000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 6, 15), amount=Decimal("8000.00"), currency="USD", account_code="5000", account_name="COGS"),
        GLEntry(date=date(2026, 6, 20), amount=Decimal("1500.00"), currency="USD", account_code="6100", account_name="Facilities"),
        GLEntry(date=date(2026, 6, 20), amount=Decimal("900.00"), currency="USD", account_code="6200", account_name="Software"),
    ]

    report = compute_profit_and_loss(gl, coa, entity_id, date(2026, 6, 1), date(2026, 6, 30))

    assert report.total_revenue == Decimal("20000.00")
    assert report.total_cogs == Decimal("8000.00")
    assert report.gross_profit == Decimal("12000.00")
    assert report.total_operating_expenses == Decimal("2400.00")
    assert report.operating_income == Decimal("9600.00")
    assert report.net_income == Decimal("9600.00")
    assert report.unclassified_account_codes == []


def test_other_income_and_expense_affect_net_income_below_operating_income():
    entity_id = "e1"
    coa = _coa_with_standard_accounts(entity_id)
    gl = [
        GLEntry(date=date(2026, 6, 15), amount=Decimal("-10000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 6, 15), amount=Decimal("-500.00"), currency="USD", account_code="7000", account_name="Interest Income"),
        GLEntry(date=date(2026, 6, 15), amount=Decimal("200.00"), currency="USD", account_code="7100", account_name="Interest Expense"),
    ]

    report = compute_profit_and_loss(gl, coa, entity_id, date(2026, 6, 1), date(2026, 6, 30))

    assert report.operating_income == Decimal("10000.00")
    assert report.total_other_income == Decimal("500.00")
    assert report.total_other_expense == Decimal("200.00")
    assert report.net_income == Decimal("10300.00")


def test_period_filtering_excludes_out_of_range_entries():
    entity_id = "e1"
    coa = _coa_with_standard_accounts(entity_id)
    gl = [
        GLEntry(date=date(2026, 6, 15), amount=Decimal("-1000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 5, 15), amount=Decimal("-5000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 7, 1), amount=Decimal("-9000.00"), currency="USD", account_code="4000", account_name="Revenue"),
    ]

    report = compute_profit_and_loss(gl, coa, entity_id, date(2026, 6, 1), date(2026, 6, 30))

    assert report.total_revenue == Decimal("1000.00")


def test_unclassified_account_flagged_not_dropped_silently():
    entity_id = "e1"
    coa = _coa_with_standard_accounts(entity_id)
    gl = [
        GLEntry(date=date(2026, 6, 15), amount=Decimal("-10000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 6, 15), amount=Decimal("3000.00"), currency="USD", account_code="9999", account_name="Mystery Account"),
    ]

    report = compute_profit_and_loss(gl, coa, entity_id, date(2026, 6, 1), date(2026, 6, 30))

    assert report.unclassified_account_codes == ["9999"]
    # Mystery account never silently entered Net Income
    assert report.net_income == Decimal("10000.00")


def test_balance_sheet_accounts_excluded_from_pl():
    entity_id = "e1"
    coa = _coa_with_standard_accounts(entity_id)
    gl = [
        GLEntry(date=date(2026, 6, 15), amount=Decimal("-10000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 6, 15), amount=Decimal("10000.00"), currency="USD", account_code="1000", account_name="Cash"),
    ]

    report = compute_profit_and_loss(gl, coa, entity_id, date(2026, 6, 1), date(2026, 6, 30))

    assert report.unclassified_account_codes == []
    assert report.net_income == Decimal("10000.00")
    all_line_codes = [l.account_code for l in report.revenue_lines + report.cogs_lines + report.operating_expense_lines]
    assert "1000" not in all_line_codes
