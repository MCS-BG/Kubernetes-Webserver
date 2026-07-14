from __future__ import annotations

import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.schemas import FeedbackRequest, ReconciliationRequest
from app.entities import registry as entity_registry
from app.fx import get_fx_provider
from app.ingestion.csv_excel import CSVExcelAdapter
from app.reconciliation import check_fx_rates, match_transactions, tie_out
from app.security import audit_log, require_role
from app.skills import skill_store
from app.store import store

router = APIRouter()


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
