"""Tests the chat tool functions directly via their `.func` attribute --
this exercises the actual business logic (entity resolution, running a
reconciliation, RAG search, feedback recording) without making any network
call to the Claude API, which needs a real ANTHROPIC_API_KEY we don't have
in this environment. The live LLM routing/tool-selection itself is not
covered here -- only the tools' own behavior is.
"""
from datetime import date
from decimal import Decimal

from app.chat import tools as chat_tools
from app.close import close_workflow
from app.coa import AccountType, chart_of_accounts
from app.entities import registry as entity_registry
from app.models import BankTransaction, GLEntry, TrialBalanceLine
from app.rag import rag_store
from app.store import store


def _make_entity(name="Acme Ops LLC"):
    return entity_registry.add(name=name, base_currency="USD", description="US operating company")


def test_list_entities_empty_and_populated():
    # Use a private registry-like check via a fresh entity to avoid cross-test pollution
    entity = _make_entity(name="List Test Co")
    output = chat_tools.list_entities.func()
    assert "List Test Co" in output


def test_run_reconciliation_unknown_entity():
    result = chat_tools.run_reconciliation.func(entity_name="Totally Unknown Co", cash_account_codes="")
    assert "No entity named" in result


def test_run_reconciliation_no_source_data():
    entity = _make_entity(name="No Data Co")
    result = chat_tools.run_reconciliation.func(entity_name="No Data Co", cash_account_codes="")
    assert "No uploaded source data" in result


def test_run_reconciliation_end_to_end_via_tools():
    entity = _make_entity(name="Full Flow Co")

    bank = [BankTransaction(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account="Operating")]
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account_code="1000", account_name="Cash"),
        GLEntry(date=date(2026, 6, 30), amount=Decimal("-500.00"), currency="USD", account_code="4000", account_name="Revenue"),
    ]
    tb = [
        TrialBalanceLine(account_code="1000", account_name="Cash", reported_debit=Decimal("500.00"), reported_credit=Decimal("0")),
        TrialBalanceLine(account_code="4000", account_name="Revenue", reported_debit=Decimal("0"), reported_credit=Decimal("500.00")),
    ]
    store.add_source(bank=bank, gl=gl, trial_balance=tb, entity_id=entity.id)

    summary_text = chat_tools.run_reconciliation.func(entity_name="Full Flow Co", cash_account_codes="1000")
    assert "Reconciliation for Full Flow Co complete" in summary_text
    assert "Matched: 1" in summary_text

    # Extract reconciliation_id the same way a human/agent would read it back
    reconciliation_id = summary_text.split("reconciliation_id: ")[1].split(")")[0]

    exceptions_text = chat_tools.get_exceptions.func(reconciliation_id=reconciliation_id)
    assert "No exceptions" in exceptions_text

    tb_text = chat_tools.get_trial_balance_report.func(reconciliation_id=reconciliation_id)
    assert "1000 Cash" in tb_text
    assert "OK" in tb_text


def test_search_knowledge_base_uses_rag_store():
    entity = _make_entity(name="Docs Co")
    rag_store.add_document(
        entity.id,
        title="Revenue Policy",
        text="Revenue is recognized when control transfers to the customer per ASC 606.",
    )

    result = chat_tools.search_knowledge_base.func(entity_name="Docs Co", query="revenue recognition")
    assert "Revenue Policy" in result
    assert "ASC 606" in result


def test_record_exception_feedback_suppresses_future_flags():
    entity = _make_entity(name="Feedback Co")
    bank = [
        BankTransaction(date=date(2026, 6, 30), amount=Decimal("100.00"), currency="USD", reference="Vendor X"),
    ]
    gl: list[GLEntry] = []
    store.add_source(bank=bank, gl=gl, trial_balance=[], entity_id=entity.id)

    summary_text = chat_tools.run_reconciliation.func(entity_name="Feedback Co", cash_account_codes="1000")
    reconciliation_id = summary_text.split("reconciliation_id: ")[1].split(")")[0]

    exceptions_before = chat_tools.get_exceptions.func(reconciliation_id=reconciliation_id)
    assert "Vendor X" in exceptions_before

    feedback_result = chat_tools.record_exception_feedback.func(
        reconciliation_id=reconciliation_id,
        flag_index=0,
        match_text="Vendor X",
        note="Always pays late, not a real issue",
    )
    assert "Recorded" in feedback_result

    # Re-run reconciliation for the same entity -- the learned pattern should suppress it now
    summary_text_2 = chat_tools.run_reconciliation.func(entity_name="Feedback Co", cash_account_codes="1000")
    assert "Suppressed by previously-learned patterns: 1" in summary_text_2


def test_get_profit_and_loss_unknown_entity():
    result = chat_tools.get_profit_and_loss.func(
        entity_name="Nope Inc", period_start="2026-06-01", period_end="2026-06-30"
    )
    assert "No entity named" in result


def test_get_profit_and_loss_bad_dates():
    entity = _make_entity(name="Date Test Co")
    result = chat_tools.get_profit_and_loss.func(
        entity_name="Date Test Co", period_start="not-a-date", period_end="2026-06-30"
    )
    assert "ISO dates" in result


def test_get_close_status_unknown_entity():
    result = chat_tools.get_close_status.func(
        entity_name="Nope Inc", period_start="2026-06-01", period_end="2026-06-30"
    )
    assert "No entity named" in result


def test_get_close_status_bad_dates():
    entity = _make_entity(name="Close Date Test Co")
    result = chat_tools.get_close_status.func(
        entity_name="Close Date Test Co", period_start="not-a-date", period_end="2026-06-30"
    )
    assert "ISO dates" in result


def test_get_close_status_not_started():
    entity = _make_entity(name="Never Closed Co")
    result = chat_tools.get_close_status.func(
        entity_name="Never Closed Co", period_start="2026-06-01", period_end="2026-06-30"
    )
    assert "not_started" in result


def test_get_close_status_reports_blocking_critical_exceptions():
    entity = _make_entity(name="Blocked Close Co")

    bank = [BankTransaction(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account="Operating")]
    gl = [
        GLEntry(date=date(2026, 6, 30), amount=Decimal("500.00"), currency="USD", account_code="1000", account_name="Cash"),
        GLEntry(date=date(2026, 6, 30), amount=Decimal("-500.00"), currency="USD", account_code="4000", account_name="Revenue"),
    ]
    # No trial balance uploaded -- guarantees ACCOUNT_TIE_OUT_MISMATCH CRITICAL flags.
    store.add_source(bank=bank, gl=gl, trial_balance=[], entity_id=entity.id)

    summary_text = chat_tools.run_reconciliation.func(entity_name="Blocked Close Co", cash_account_codes="1000")
    reconciliation_id = summary_text.split("reconciliation_id: ")[1].split(")")[0]

    period = close_workflow.start(
        entity_id=entity.id,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        actor="alice",
    )
    result_obj = store.results[reconciliation_id]
    try:
        close_workflow.submit_for_review(period.id, reconciliation_id, result_obj, actor="alice")
    except Exception:
        pass  # expected: blocked by critical flags, status stays in_progress

    status_text = chat_tools.get_close_status.func(
        entity_name="Blocked Close Co", period_start="2026-06-01", period_end="2026-06-30"
    )
    assert "in_progress" in status_text
    assert "Blocked by" in status_text
    assert "critical exception" in status_text


def test_get_profit_and_loss_end_to_end():
    entity = _make_entity(name="P&L Chat Co")
    chart_of_accounts.set_account(entity.id, "4000", "Revenue", AccountType.REVENUE)
    chart_of_accounts.set_account(entity.id, "6100", "Facilities Expense", AccountType.OPERATING_EXPENSE)

    gl = [
        GLEntry(date=date(2026, 6, 10), amount=Decimal("-5000.00"), currency="USD", account_code="4000", account_name="Revenue"),
        GLEntry(date=date(2026, 6, 12), amount=Decimal("1200.00"), currency="USD", account_code="6100", account_name="Facilities Expense"),
        GLEntry(date=date(2026, 6, 12), amount=Decimal("300.00"), currency="USD", account_code="7777", account_name="Unclassified Thing"),
    ]
    store.add_source(bank=[], gl=gl, trial_balance=[], entity_id=entity.id)

    result = chat_tools.get_profit_and_loss.func(
        entity_name="P&L Chat Co", period_start="2026-06-01", period_end="2026-06-30"
    )
    assert "Total Revenue: 5000.00" in result
    assert "Total Operating Expenses: 1200.00" in result
    assert "Net Income: 3800.00" in result
    assert "7777" in result  # unclassified account flagged, not silently dropped
