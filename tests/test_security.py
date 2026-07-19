import pytest
from fastapi import HTTPException

from app.security.audit import AuditLog
from app.security.auth import authenticate, require_role
from app.security.pii import mask_account_number, mask_name


def test_mask_account_number_keeps_last_four():
    assert mask_account_number("Wire ref 123456789") == "Wire ref *****6789"


def test_mask_account_number_ignores_short_digit_runs():
    assert mask_account_number("Invoice 42 due in 30 days") == "Invoice 42 due in 30 days"


def test_mask_name():
    assert mask_name("Jane Doe") == "J*** D**"
    assert mask_name("") == ""


def test_audit_log_is_append_only_and_masks_details():
    log = AuditLog()
    log.record(actor="alice", action="reconciliation_run", entity_id="e1", details={"note": "acct 987654321"})

    entries = log.list()
    assert len(entries) == 1
    assert entries[0].actor == "alice"
    assert entries[0].details["note"] == "acct *****4321"
    # No update/delete method exists on AuditLog -- append-only by construction.
    assert not hasattr(log, "delete")
    assert not hasattr(log, "update")


def test_audit_log_filters_by_entity():
    log = AuditLog()
    log.record(actor="alice", action="a", entity_id="e1")
    log.record(actor="bob", action="b", entity_id="e2")

    assert len(log.list(entity_id="e1")) == 1
    assert log.list(entity_id="e1")[0].actor == "alice"


def test_authenticate_no_tokens_configured_is_noop(monkeypatch):
    monkeypatch.delenv("AUTH_TOKENS", raising=False)
    identity = authenticate(authorization=None)
    assert identity == ("unauthenticated", "admin")


def test_authenticate_rejects_missing_header_when_tokens_configured(monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", "tok_alice:alice:preparer")
    with pytest.raises(HTTPException) as exc_info:
        authenticate(authorization=None)
    assert exc_info.value.status_code == 401


def test_authenticate_accepts_valid_bearer_token(monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", "tok_alice:alice:preparer,tok_bob:bob:reviewer")
    assert authenticate(authorization="Bearer tok_alice") == ("alice", "preparer")
    assert authenticate(authorization="Bearer tok_bob") == ("bob", "reviewer")


def test_require_role_blocks_insufficient_role():
    dependency = require_role("reviewer")
    with pytest.raises(HTTPException) as exc_info:
        dependency(identity=("alice", "preparer"))
    assert exc_info.value.status_code == 403


def test_require_role_allows_sufficient_role():
    dependency = require_role("preparer")
    assert dependency(identity=("alice", "reviewer")) == ("alice", "reviewer")
