from __future__ import annotations

import io
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.schemas import ChartOfAccountsEntryRequest, FeedbackRequest, ReconciliationRequest
from app.coa import AccountType, chart_of_accounts
from app.entities import registry as entity_registry
from app.fx import get_fx_provider
from app.ingestion.csv_excel import CSVExcelAdapter
from app.reconciliation import check_fx_rates, match_transactions, tie_out
from app.reporting import build_pl_workbook, compute_profit_and_loss
from app.security import audit_log, require_role
from app.skills import skill_store
from app.store import store

router = APIRouter()

# Classification for this repo's own sample_data/ files, used only by the
# /demo/seed endpoint below -- intentionally leaves 1300 (Intercompany
# Receivable) and 6200 (Software Expense) unclassified so the demo dashboard
# has something real to show in "unclassified accounts", not a contrived gap.
_DEMO_CHART_OF_ACCOUNTS = [
    ("1000", "Cash", AccountType.ASSET),
    ("4000", "Revenue", AccountType.REVENUE),
    ("5000", "Cost of Goods Sold", AccountType.COGS),
    ("6100", "Facilities Expense", AccountType.OPERATING_EXPENSE),
]
_DEMO_PERIOD_START = date(2026, 6, 1)
_DEMO_PERIOD_END = date(2026, 6, 30)

# Seeded once per process (in-memory, like everything else in this MVP): the
# entity and uploaded source are created on first call and reused after that,
# so repeated demo loads don't pile up duplicate entities or double-count GL
# activity in the P&L. Re-running reconciliation on the same source each call
# is harmless and deterministic -- it's what demonstrates "run it any time."
_demo_cache: dict = {}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/entities")
def list_entities():
    return {
        "entities": [
            {"id": e.id, "name": e.name, "base_currency": e.base_currency, "description": e.description}
            for e in entity_registry.list()
        ]
    }


@router.post("/entities")
def create_entity(name: str, base_currency: str = "USD", description: str = ""):
    entity = entity_registry.add(name=name, base_currency=base_currency, description=description)
    return {"id": entity.id, "name": entity.name, "base_currency": entity.base_currency}


@router.get("/entities/{entity_id}/chart-of-accounts")
def get_chart_of_accounts(entity_id: str):
    return {
        "accounts": [
            {"account_code": a.account_code, "account_name": a.account_name, "account_type": a.account_type.value}
            for a in chart_of_accounts.accounts_for(entity_id)
        ]
    }


@router.post("/entities/{entity_id}/chart-of-accounts")
def set_chart_of_accounts_entry(
    entity_id: str,
    request: ChartOfAccountsEntryRequest,
    identity: tuple[str, str] = Depends(require_role("preparer")),
):
    """Classifies a GL account (revenue/COGS/operating expense/other
    income/other expense/asset/liability/equity) for this entity. Required
    before an account's activity can appear in that entity's P&L -- an
    unclassified account is flagged, never silently included or excluded.
    """
    entry = chart_of_accounts.set_account(
        entity_id=entity_id,
        account_code=request.account_code,
        account_name=request.account_name,
        account_type=request.account_type,
    )
    audit_log.record(
        actor=identity[0],
        action="chart_of_accounts_updated",
        entity_id=entity_id,
        details={"account_code": entry.account_code, "account_type": entry.account_type.value},
    )
    return {"account_code": entry.account_code, "account_name": entry.account_name, "account_type": entry.account_type.value}


@router.get("/entities/{entity_id}/profit-and-loss")
def get_profit_and_loss(entity_id: str, period_start: date, period_end: date):
    if entity_registry.get(entity_id) is None:
        raise HTTPException(404, f"Unknown entity_id {entity_id}")

    gl_entries = store.gl_entries_for_entity(entity_id)
    report = compute_profit_and_loss(gl_entries, chart_of_accounts, entity_id, period_start, period_end)

    def _lines(lines):
        return [{"account_code": l.account_code, "account_name": l.account_name, "amount": str(l.amount)} for l in lines]

    return {
        "entity_id": entity_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "revenue": {"lines": _lines(report.revenue_lines), "total": str(report.total_revenue)},
        "cogs": {"lines": _lines(report.cogs_lines), "total": str(report.total_cogs)},
        "gross_profit": str(report.gross_profit),
        "operating_expenses": {"lines": _lines(report.operating_expense_lines), "total": str(report.total_operating_expenses)},
        "operating_income": str(report.operating_income),
        "other_income": {"lines": _lines(report.other_income_lines), "total": str(report.total_other_income)},
        "other_expense": {"lines": _lines(report.other_expense_lines), "total": str(report.total_other_expense)},
        "net_income": str(report.net_income),
        "unclassified_account_codes": report.unclassified_account_codes,
    }


@router.get("/entities/{entity_id}/profit-and-loss/export")
def export_profit_and_loss(entity_id: str, period_start: date, period_end: date):
    """Downloads a live, formula-driven P&L workbook: a GL Data tab holding
    this entity's full ledger, and a P&L tab where every figure is a real
    SUMIFS/SUM formula referencing it -- change the period cells or the
    underlying data and the report recalculates, no regeneration needed.
    """
    entity = entity_registry.get(entity_id)
    if entity is None:
        raise HTTPException(404, f"Unknown entity_id {entity_id}")

    gl_entries = store.gl_entries_for_entity(entity_id)
    workbook = build_pl_workbook(gl_entries, chart_of_accounts, entity_id, entity.name, period_start, period_end)

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    filename = f"{entity.name.replace(' ', '_')}_PL_{period_start.isoformat()}_{period_end.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/sources/upload")
async def upload_source(
    bank_file: UploadFile | None = File(None),
    gl_file: UploadFile | None = File(None),
    trial_balance_file: UploadFile | None = File(None),
    default_currency: str = Form("USD"),
    entity_id: str | None = Form(None),
    identity: tuple[str, str] = Depends(require_role("preparer")),
):
    """Ingests a one-time ERP data migration / export: CSV or Excel files
    for the bank statement, the GL, and/or the reported trial balance.
    """
    if not any([bank_file, gl_file, trial_balance_file]):
        raise HTTPException(
            400, "At least one of bank_file, gl_file, trial_balance_file is required"
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="recon_"))
    saved_paths: dict[str, Path] = {}
    for field_name, upload in (
        ("bank_file", bank_file),
        ("gl_file", gl_file),
        ("trial_balance_file", trial_balance_file),
    ):
        if upload is None:
            continue
        dest = tmp_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_paths[field_name] = dest

    adapter = CSVExcelAdapter(
        bank_file=saved_paths.get("bank_file"),
        gl_file=saved_paths.get("gl_file"),
        trial_balance_file=saved_paths.get("trial_balance_file"),
        default_currency=default_currency,
    )
    source_id = store.add_source(
        bank=adapter.fetch_bank_transactions(),
        gl=adapter.fetch_gl_entries(),
        trial_balance=adapter.fetch_trial_balance(),
        entity_id=entity_id,
    )
    audit_log.record(
        actor=identity[0], action="source_upload", entity_id=entity_id, details={"source_id": source_id}
    )
    return {"source_id": source_id}


@router.post("/reconciliations/run")
def run_reconciliation(
    request: ReconciliationRequest,
    identity: tuple[str, str] = Depends(require_role("preparer")),
):
    source = store.sources.get(request.source_id)
    if not source:
        raise HTTPException(404, f"Unknown source_id {request.source_id}")

    tolerance = Decimal(request.amount_tolerance) if request.amount_tolerance else None

    result = match_transactions(
        source.bank_transactions,
        source.gl_entries,
        date_window_days=request.date_window_days,
        amount_tolerance=tolerance,
        fuzzy_threshold=request.fuzzy_threshold,
        gl_account_codes=request.cash_account_codes,
    )

    tie_out_lines, tb_flags = tie_out(source.gl_entries, source.trial_balance)
    result.flags.extend(tb_flags)

    if request.check_fx:
        fx_provider = get_fx_provider()
        result.flags.extend(
            check_fx_rates(source.gl_entries, fx_provider, base_currency=request.base_currency)
        )

    result.flags, suppressed_count = skill_store.apply_suppression(result.flags, source.entity_id)

    store.results[result.id] = result
    store.tie_outs[result.id] = tie_out_lines
    store.result_entity[result.id] = source.entity_id
    store.result_actor[result.id] = identity[0]

    audit_log.record(
        actor=identity[0],
        action="reconciliation_run",
        entity_id=source.entity_id,
        details={"reconciliation_id": result.id, "source_id": request.source_id},
    )

    summary = result.summary()
    summary["suppressed_by_learned_patterns"] = suppressed_count
    return {"reconciliation_id": result.id, "summary": summary}


@router.post("/feedback")
def record_feedback(
    request: FeedbackRequest,
    identity: tuple[str, str] = Depends(require_role("reviewer")),
):
    """Marks a flag as a reviewed false positive, so future reconciliation
    runs for the same entity suppress the same recognized noise. This is
    the concrete mechanism behind "the skill file evolves" -- a human
    decision, recorded once, applied automatically going forward.

    Requires reviewer role, and enforces segregation of duties: the
    reviewer recording feedback cannot be the same actor who ran the
    original reconciliation.
    """
    result = store.results.get(request.reconciliation_id)
    if not result:
        raise HTTPException(404, f"Unknown reconciliation_id {request.reconciliation_id}")
    if request.flag_index < 0 or request.flag_index >= len(result.flags):
        raise HTTPException(400, f"flag_index {request.flag_index} out of range")

    entity_id = store.result_entity.get(request.reconciliation_id)
    if not entity_id:
        raise HTTPException(
            400, "This reconciliation run has no associated entity_id -- feedback needs one"
        )

    preparer = store.result_actor.get(request.reconciliation_id)
    reviewer = identity[0]
    if preparer is not None and preparer == reviewer and reviewer != "unauthenticated":
        raise HTTPException(
            403,
            "Segregation of duties: the reviewer approving this exception cannot be the "
            "same person who ran the reconciliation it came from.",
        )

    flag = result.flags[request.flag_index]
    pattern = skill_store.record_feedback(
        entity_id=entity_id,
        flag_type=flag.type,
        match_text=request.match_text,
        note=request.note,
    )
    audit_log.record(
        actor=reviewer,
        action="feedback_recorded",
        entity_id=entity_id,
        details={"reconciliation_id": request.reconciliation_id, "pattern_id": pattern.id},
    )
    return {"pattern_id": pattern.id, "entity_id": entity_id, "flag_type": flag.type.value}


@router.get("/audit-log")
def get_audit_log(
    entity_id: str | None = None,
    identity: tuple[str, str] = Depends(require_role("reviewer")),
):
    entries = audit_log.list(entity_id=entity_id)
    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "actor": e.actor,
                "action": e.action,
                "entity_id": e.entity_id,
                "details": e.details,
            }
            for e in entries
        ]
    }


@router.get("/reconciliations/{reconciliation_id}/exceptions")
def get_exceptions(reconciliation_id: str):
    result = store.results.get(reconciliation_id)
    if not result:
        raise HTTPException(404, f"Unknown reconciliation_id {reconciliation_id}")
    return {
        "flags": [
            {
                "type": f.type.value,
                "severity": f.severity.value,
                "message": f.message,
                "entry_ids": f.entry_ids,
                "details": f.details,
            }
            for f in result.flags
        ]
    }


@router.get("/reconciliations/{reconciliation_id}/trial-balance")
def get_trial_balance(reconciliation_id: str):
    lines = store.tie_outs.get(reconciliation_id)
    if lines is None:
        raise HTTPException(404, f"Unknown reconciliation_id {reconciliation_id}")
    return {
        "accounts": [
            {
                "account_code": l.account_code,
                "account_name": l.account_name,
                "computed_debit": str(l.computed_debit),
                "computed_credit": str(l.computed_credit),
                "reported_debit": str(l.reported_debit),
                "reported_credit": str(l.reported_credit),
                "tied_out": l.tied_out,
            }
            for l in lines
        ]
    }


@router.post("/demo/seed")
def seed_demo():
    """One-call bootstrap for the demo dashboard (web/demo.html): creates a
    demo entity, classifies its chart of accounts, uploads this repo's own
    sample_data/ files, and runs a reconciliation -- returning every id the
    dashboard needs to then call the same read endpoints everything else in
    this app uses (exceptions, trial-balance, profit-and-loss). Not part of
    the real client-facing API surface; it exists so a demo has real data to
    show without anyone typing curl commands first.
    """
    if "entity_id" not in _demo_cache:
        entity = entity_registry.add(
            name="Acme Ops LLC (Demo)",
            base_currency="USD",
            description="Seeded automatically for the LedgeOS demo dashboard.",
        )
        for account_code, account_name, account_type in _DEMO_CHART_OF_ACCOUNTS:
            chart_of_accounts.set_account(entity.id, account_code, account_name, account_type)

        sample_dir = Path(__file__).resolve().parents[2] / "sample_data"
        adapter = CSVExcelAdapter(
            bank_file=sample_dir / "bank_statement_sample.csv",
            gl_file=sample_dir / "gl_export_sample.csv",
            trial_balance_file=sample_dir / "trial_balance_sample.csv",
            default_currency="USD",
        )
        source_id = store.add_source(
            bank=adapter.fetch_bank_transactions(),
            gl=adapter.fetch_gl_entries(),
            trial_balance=adapter.fetch_trial_balance(),
            entity_id=entity.id,
        )
        _demo_cache["entity_id"] = entity.id
        _demo_cache["entity_name"] = entity.name
        _demo_cache["source_id"] = source_id

    source = store.sources[_demo_cache["source_id"]]
    result = match_transactions(source.bank_transactions, source.gl_entries, gl_account_codes=["1000"])
    tie_out_lines, tb_flags = tie_out(source.gl_entries, source.trial_balance)
    result.flags.extend(tb_flags)
    result.flags, suppressed_count = skill_store.apply_suppression(result.flags, _demo_cache["entity_id"])

    store.results[result.id] = result
    store.tie_outs[result.id] = tie_out_lines
    store.result_entity[result.id] = _demo_cache["entity_id"]
    store.result_actor[result.id] = "demo"

    audit_log.record(
        actor="demo",
        action="demo_seeded",
        entity_id=_demo_cache["entity_id"],
        details={"source_id": _demo_cache["source_id"], "reconciliation_id": result.id},
    )

    summary = result.summary()
    summary["suppressed_by_learned_patterns"] = suppressed_count

    return {
        "entity_id": _demo_cache["entity_id"],
        "entity_name": _demo_cache["entity_name"],
        "source_id": _demo_cache["source_id"],
        "reconciliation_id": result.id,
        "summary": summary,
        "period_start": _DEMO_PERIOD_START.isoformat(),
        "period_end": _DEMO_PERIOD_END.isoformat(),
    }
