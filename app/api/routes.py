from __future__ import annotations

import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas import ReconciliationRequest
from app.fx import get_fx_provider
from app.ingestion.csv_excel import CSVExcelAdapter
from app.reconciliation import check_fx_rates, match_transactions, tie_out
from app.store import store

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/sources/upload")
async def upload_source(
    bank_file: UploadFile | None = File(None),
    gl_file: UploadFile | None = File(None),
    trial_balance_file: UploadFile | None = File(None),
    default_currency: str = Form("USD"),
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
    )
    return {"source_id": source_id}


@router.post("/reconciliations/run")
def run_reconciliation(request: ReconciliationRequest):
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

    store.results[result.id] = result
    store.tie_outs[result.id] = tie_out_lines

    return {"reconciliation_id": result.id, "summary": result.summary()}


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
