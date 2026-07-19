"""Month-end close workflow: state transitions, the critical-exceptions
readiness gate, and segregation of duties on approve/reject (same rule and
same escape hatch as tests/test_segregation_of_duties.py's /feedback tests).
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTH_TOKENS = "tok_alice_prep:alice:preparer,tok_alice_rev:alice:reviewer,tok_bob_rev:bob:reviewer"

PERIOD_START = "2026-06-01"
PERIOD_END = "2026-06-30"


def _make_entity(tmp_path, name=None):
    resp = client.post("/entities", params={"name": name or f"Close Co {tmp_path.name}"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _reconcile_clean(tmp_path, entity_id, headers):
    """Matched pair + one always-unmatched leg on each side, trial balance
    tying out exactly -- zero CRITICAL flags (only WARNING for the two
    unmatched legs), so submission is never blocked."""
    bank_csv = tmp_path / "bank_clean.csv"
    bank_csv.write_text(
        "date,amount,currency,description,reference,account\n"
        "2026-06-30,1000.00,USD,ACME CORP PAYMENT,INV-1,Operating\n"
        "2026-06-29,250.00,USD,Unrecognized wire,WIRE-9,Operating\n"
    )
    gl_csv = tmp_path / "gl_clean.csv"
    gl_csv.write_text(
        "date,amount,currency,account_code,account_name,description,reference\n"
        "2026-06-30,1000.00,USD,4000,Revenue,Acme Corp Payment,INV-1\n"
        "2026-06-15,-1000.00,USD,1000,Cash,Unrelated GL only entry,GL-7\n"
    )
    tb_csv = tmp_path / "tb_clean.csv"
    tb_csv.write_text(
        "account_code,account_name,debit,credit\n"
        "4000,Revenue,1000.00,0\n"
        "1000,Cash,0,1000.00\n"
    )
    with bank_csv.open("rb") as bf, gl_csv.open("rb") as gf, tb_csv.open("rb") as tf:
        resp = client.post(
            "/sources/upload",
            files={
                "bank_file": ("bank.csv", bf, "text/csv"),
                "gl_file": ("gl.csv", gf, "text/csv"),
                "trial_balance_file": ("tb.csv", tf, "text/csv"),
            },
            data={"entity_id": entity_id},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["source_id"]

    resp = client.post(
        "/reconciliations/run", json={"source_id": source_id, "check_fx": False}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary["flags_by_severity"].get("critical", 0) == 0
    return resp.json()["reconciliation_id"]


def _reconcile_blocked(tmp_path, entity_id, headers):
    """No trial balance uploaded at all -- every account with GL activity
    has a reported balance of zero, guaranteeing an ACCOUNT_TIE_OUT_MISMATCH
    CRITICAL flag."""
    bank_csv = tmp_path / "bank_blocked.csv"
    bank_csv.write_text(
        "date,amount,currency,description,reference,account\n"
        "2026-06-30,1000.00,USD,ACME CORP PAYMENT,INV-1,Operating\n"
    )
    gl_csv = tmp_path / "gl_blocked.csv"
    gl_csv.write_text(
        "date,amount,currency,account_code,account_name,description,reference\n"
        "2026-06-30,1000.00,USD,4000,Revenue,Acme Corp Payment,INV-1\n"
        "2026-06-15,-1000.00,USD,1000,Cash,Offsetting leg,GL-7\n"
    )
    with bank_csv.open("rb") as bf, gl_csv.open("rb") as gf:
        resp = client.post(
            "/sources/upload",
            files={"bank_file": ("bank.csv", bf, "text/csv"), "gl_file": ("gl.csv", gf, "text/csv")},
            data={"entity_id": entity_id},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    source_id = resp.json()["source_id"]

    resp = client.post(
        "/reconciliations/run", json={"source_id": source_id, "check_fx": False}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary["flags_by_severity"].get("critical", 0) > 0
    return resp.json()["reconciliation_id"]


def test_close_start_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    entity_id = _make_entity(tmp_path)
    headers = {"Authorization": "Bearer tok_alice_prep"}

    resp1 = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=headers,
    )
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert body1["status"] == "in_progress"

    resp2 = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=headers,
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["id"] == body1["id"]


def test_submit_blocked_by_critical_flags(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    headers = {"Authorization": "Bearer tok_alice_prep"}
    entity_id = _make_entity(tmp_path)
    reconciliation_id = _reconcile_blocked(tmp_path, entity_id, headers)

    close_resp = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=headers,
    )
    close_id = close_resp.json()["id"]

    resp = client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "critical exception" in resp.json()["detail"]

    # Blocked attempt still leaves the close in_progress, not silently advanced.
    get_resp = client.get(f"/close/{close_id}")
    assert get_resp.json()["status"] == "in_progress"


def test_full_happy_path_start_submit_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    reviewer_headers = {"Authorization": "Bearer tok_bob_rev"}
    entity_id = _make_entity(tmp_path)
    reconciliation_id = _reconcile_clean(tmp_path, entity_id, preparer_headers)

    close_resp = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=preparer_headers,
    )
    close_id = close_resp.json()["id"]

    submit_resp = client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=preparer_headers,
    )
    assert submit_resp.status_code == 200, submit_resp.text
    assert submit_resp.json()["status"] == "pending_review"
    assert submit_resp.json()["prepared_by"] == "alice"

    approve_resp = client.post("/close/approve", json={"close_id": close_id}, headers=reviewer_headers)
    assert approve_resp.status_code == 200, approve_resp.text
    body = approve_resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "bob"
    assert [t["to_status"] for t in body["history"]] == ["in_progress", "pending_review", "approved"]

    audit_resp = client.get("/audit-log", params={"entity_id": entity_id}, headers=reviewer_headers)
    actions = {e["action"] for e in audit_resp.json()["entries"]}
    assert {"close_started", "close_submitted", "close_approved"} <= actions


def test_approve_requires_reviewer_role(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    entity_id = _make_entity(tmp_path)
    reconciliation_id = _reconcile_clean(tmp_path, entity_id, preparer_headers)

    close_id = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=preparer_headers,
    ).json()["id"]
    client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=preparer_headers,
    )

    resp = client.post("/close/approve", json={"close_id": close_id}, headers=preparer_headers)
    assert resp.status_code == 403


def test_approve_blocks_same_actor_as_preparer(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    alice_reviewer_headers = {"Authorization": "Bearer tok_alice_rev"}
    entity_id = _make_entity(tmp_path)
    reconciliation_id = _reconcile_clean(tmp_path, entity_id, preparer_headers)

    close_id = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=preparer_headers,
    ).json()["id"]
    client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=preparer_headers,
    )

    resp = client.post("/close/approve", json={"close_id": close_id}, headers=alice_reviewer_headers)
    assert resp.status_code == 403
    assert "Segregation of duties" in resp.json()["detail"]


def test_reject_requires_different_actor_then_resubmit_after_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    alice_reviewer_headers = {"Authorization": "Bearer tok_alice_rev"}
    bob_reviewer_headers = {"Authorization": "Bearer tok_bob_rev"}
    entity_id = _make_entity(tmp_path)
    reconciliation_id = _reconcile_clean(tmp_path, entity_id, preparer_headers)

    close_id = client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=preparer_headers,
    ).json()["id"]
    client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=preparer_headers,
    )

    # Alice (the preparer) can't reject her own submission either.
    resp = client.post(
        "/close/reject",
        json={"close_id": close_id, "reason": "numbers look off"},
        headers=alice_reviewer_headers,
    )
    assert resp.status_code == 403
    assert "Segregation of duties" in resp.json()["detail"]

    # Bob (a different actor) rejects it instead.
    resp = client.post(
        "/close/reject",
        json={"close_id": close_id, "reason": "Missing Q2 accrual, please add it"},
        headers=bob_reviewer_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Missing Q2 accrual, please add it"

    # Preparer fixes it and resubmits against the same (still-clean) run.
    resubmit_resp = client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=preparer_headers,
    )
    assert resubmit_resp.status_code == 200, resubmit_resp.text
    assert resubmit_resp.json()["status"] == "pending_review"
    assert resubmit_resp.json()["rejection_reason"] is None


def test_submit_rejects_reconciliation_from_a_different_entity(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    entity_a = _make_entity(tmp_path, name=f"Entity A {tmp_path.name}")
    entity_b = _make_entity(tmp_path, name=f"Entity B {tmp_path.name}")
    reconciliation_id = _reconcile_clean(tmp_path, entity_a, preparer_headers)

    close_id = client.post(
        "/close/start",
        json={"entity_id": entity_b, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=preparer_headers,
    ).json()["id"]

    resp = client.post(
        "/close/submit",
        json={"close_id": close_id, "reconciliation_id": reconciliation_id},
        headers=preparer_headers,
    )
    assert resp.status_code == 400
    assert "different entity" in resp.json()["detail"]


def test_list_close_periods_for_entity(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    entity_id = _make_entity(tmp_path)

    client.post(
        "/close/start",
        json={"entity_id": entity_id, "period_start": PERIOD_START, "period_end": PERIOD_END},
        headers=preparer_headers,
    )
    resp = client.get(f"/entities/{entity_id}/close")
    assert resp.status_code == 200
    periods = resp.json()["close_periods"]
    assert len(periods) == 1
    assert periods[0]["entity_id"] == entity_id
