from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

AUTH_TOKENS = "tok_alice_prep:alice:preparer,tok_alice_rev:alice:reviewer,tok_bob_rev:bob:reviewer"


def _upload_and_reconcile(tmp_path, headers):
    entity_resp = client.post("/entities", params={"name": f"Test Co {tmp_path.name}"})
    assert entity_resp.status_code == 200, entity_resp.text
    entity_id = entity_resp.json()["id"]

    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "date,amount,currency,description,reference,account\n"
        "2026-06-30,1000.00,USD,ACME CORP PAYMENT,INV-1,Operating\n"
    )
    gl_csv = tmp_path / "gl.csv"
    gl_csv.write_text(
        "date,amount,currency,account_code,account_name,description,reference\n"
        "2026-06-30,1000.00,USD,4000,Revenue,Acme Corp Payment,INV-1\n"
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
        "/reconciliations/run",
        json={"source_id": source_id, "check_fx": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["reconciliation_id"]


def test_feedback_requires_reviewer_role(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    reconciliation_id = _upload_and_reconcile(tmp_path, preparer_headers)

    # Preparer role alone can't record feedback -- needs reviewer.
    resp = client.post(
        "/feedback",
        json={"reconciliation_id": reconciliation_id, "flag_index": 0, "match_text": "x", "note": "n"},
        headers=preparer_headers,
    )
    assert resp.status_code == 403


def test_feedback_blocks_same_actor_as_preparer(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    reconciliation_id = _upload_and_reconcile(tmp_path, preparer_headers)

    # Alice reviewing her own reconciliation -- segregation of duties violation.
    alice_reviewer_headers = {"Authorization": "Bearer tok_alice_rev"}
    resp = client.post(
        "/feedback",
        json={"reconciliation_id": reconciliation_id, "flag_index": 0, "match_text": "x", "note": "n"},
        headers=alice_reviewer_headers,
    )
    assert resp.status_code == 403
    assert "Segregation of duties" in resp.json()["detail"]


def test_feedback_allowed_from_different_reviewer(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    reconciliation_id = _upload_and_reconcile(tmp_path, preparer_headers)

    bob_reviewer_headers = {"Authorization": "Bearer tok_bob_rev"}
    resp = client.get(f"/reconciliations/{reconciliation_id}/exceptions", headers=bob_reviewer_headers)
    flag_index = 0
    assert len(resp.json()["flags"]) > flag_index

    resp = client.post(
        "/feedback",
        json={
            "reconciliation_id": reconciliation_id,
            "flag_index": flag_index,
            "match_text": "Acme",
            "note": "known pattern",
        },
        headers=bob_reviewer_headers,
    )
    assert resp.status_code == 200, resp.text


def test_audit_log_requires_reviewer_and_records_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS", AUTH_TOKENS)
    preparer_headers = {"Authorization": "Bearer tok_alice_prep"}
    _upload_and_reconcile(tmp_path, preparer_headers)

    resp = client.get("/audit-log", headers=preparer_headers)
    assert resp.status_code == 403

    bob_reviewer_headers = {"Authorization": "Bearer tok_bob_rev"}
    resp = client.get("/audit-log", headers=bob_reviewer_headers)
    assert resp.status_code == 200
    actions = {e["action"] for e in resp.json()["entries"]}
    assert "source_upload" in actions
    assert "reconciliation_run" in actions
