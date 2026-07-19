from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_seed_demo_returns_ids_and_summary():
    resp = client.post("/demo/seed")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["entity_id"]
    assert data["entity_name"] == "Acme Ops LLC (Demo)"
    assert data["source_id"]
    assert data["reconciliation_id"]
    assert data["period_start"] == "2026-06-01"
    assert data["period_end"] == "2026-06-30"

    summary = data["summary"]
    assert summary["matched"] == 3
    assert summary["unmatched_bank"] == 2
    assert summary["unmatched_gl"] == 2
    assert summary["flags_total"] == 5


def test_seed_demo_reuses_entity_and_source_on_repeat_calls():
    first = client.post("/demo/seed").json()
    second = client.post("/demo/seed").json()

    assert second["entity_id"] == first["entity_id"]
    assert second["source_id"] == first["source_id"]
    # Reconciliation reruns each call (deterministic, so this is safe) --
    # a fresh reconciliation_id each time is expected, not a bug.
    assert second["reconciliation_id"]


def test_seed_demo_downstream_endpoints_work():
    seed = client.post("/demo/seed").json()

    tb_resp = client.get(f"/reconciliations/{seed['reconciliation_id']}/trial-balance")
    assert tb_resp.status_code == 200
    accounts = {a["account_code"]: a for a in tb_resp.json()["accounts"]}
    assert accounts["6100"]["tied_out"] is False  # the planted $25 variance

    exceptions_resp = client.get(f"/reconciliations/{seed['reconciliation_id']}/exceptions")
    assert exceptions_resp.status_code == 200
    assert len(exceptions_resp.json()["flags"]) == 5

    pl_resp = client.get(
        f"/entities/{seed['entity_id']}/profit-and-loss",
        params={"period_start": seed["period_start"], "period_end": seed["period_end"]},
    )
    assert pl_resp.status_code == 200
    pl = pl_resp.json()
    assert pl["revenue"]["total"] == "15000.00"
    assert sorted(pl["unclassified_account_codes"]) == ["1300", "6200"]
