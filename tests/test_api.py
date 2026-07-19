from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_upload_and_reconcile_end_to_end(tmp_path):
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "date,amount,currency,description,reference,account\n"
        "2026-06-30,1000.00,USD,ACME CORP PAYMENT,INV-1,Operating\n"
        "2026-06-29,250.00,USD,Unrecognized wire,WIRE-9,Operating\n"
    )

    gl_csv = tmp_path / "gl.csv"
    gl_csv.write_text(
        "date,amount,currency,account_code,account_name,description,reference\n"
        "2026-06-30,1000.00,USD,4000,Revenue,Acme Corp Payment,INV-1\n"
        "2026-06-15,-1000.00,USD,1000,Cash,Unrelated GL only entry,GL-7\n"
    )

    tb_csv = tmp_path / "tb.csv"
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
        )
    assert resp.status_code == 200
    source_id = resp.json()["source_id"]

    resp = client.post(
        "/reconciliations/run",
        json={"source_id": source_id, "check_fx": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    reconciliation_id = body["reconciliation_id"]
    assert body["summary"]["matched"] == 1
    assert body["summary"]["unmatched_bank"] == 1
    assert body["summary"]["unmatched_gl"] == 1

    resp = client.get(f"/reconciliations/{reconciliation_id}/exceptions")
    assert resp.status_code == 200
    flag_types = {f["type"] for f in resp.json()["flags"]}
    assert "unmatched_bank" in flag_types
    assert "unmatched_gl" in flag_types

    resp = client.get(f"/reconciliations/{reconciliation_id}/trial-balance")
    assert resp.status_code == 200
    accounts = resp.json()["accounts"]
    assert all(a["tied_out"] for a in accounts)
