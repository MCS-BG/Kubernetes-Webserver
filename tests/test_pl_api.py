from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_entity(name: str) -> str:
    resp = client.post("/entities", params={"name": name})
    assert resp.status_code == 200
    return resp.json()["id"]


def _set_account(entity_id, code, name, account_type):
    resp = client.post(
        f"/entities/{entity_id}/chart-of-accounts",
        json={"account_code": code, "account_name": name, "account_type": account_type},
    )
    assert resp.status_code == 200, resp.text
    return resp


def _upload_gl(entity_id, tmp_path):
    gl_csv = tmp_path / "gl.csv"
    gl_csv.write_text(
        "date,amount,currency,account_code,account_name,description,reference\n"
        "2026-06-10,-25000.00,USD,4000,Revenue,June sales,INV-1\n"
        "2026-06-10,10000.00,USD,5000,COGS,June COGS,INV-1\n"
        "2026-06-12,2000.00,USD,6100,Facilities Expense,Rent,LEASE\n"
    )
    with gl_csv.open("rb") as gf:
        resp = client.post(
            "/sources/upload",
            files={"gl_file": ("gl.csv", gf, "text/csv")},
            data={"entity_id": entity_id},
        )
    assert resp.status_code == 200, resp.text


def test_chart_of_accounts_roundtrip():
    entity_id = _make_entity("COA Test Co")
    _set_account(entity_id, "4000", "Revenue", "revenue")
    _set_account(entity_id, "5000", "COGS", "cogs")

    resp = client.get(f"/entities/{entity_id}/chart-of-accounts")
    assert resp.status_code == 200
    codes = {a["account_code"] for a in resp.json()["accounts"]}
    assert codes == {"4000", "5000"}


def test_profit_and_loss_end_to_end(tmp_path):
    entity_id = _make_entity("P&L Test Co")
    _set_account(entity_id, "4000", "Revenue", "revenue")
    _set_account(entity_id, "5000", "COGS", "cogs")
    _set_account(entity_id, "6100", "Facilities Expense", "operating_expense")
    _upload_gl(entity_id, tmp_path)

    resp = client.get(
        f"/entities/{entity_id}/profit-and-loss",
        params={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["revenue"]["total"] == "25000.00"
    assert body["cogs"]["total"] == "10000.00"
    assert body["gross_profit"] == "15000.00"
    assert body["operating_expenses"]["total"] == "2000.00"
    assert body["operating_income"] == "13000.00"
    assert body["net_income"] == "13000.00"
    assert body["unclassified_account_codes"] == []


def test_profit_and_loss_unknown_entity_404():
    resp = client.get(
        "/entities/does-not-exist/profit-and-loss",
        params={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )
    assert resp.status_code == 404


def test_profit_and_loss_flags_unclassified_account(tmp_path):
    entity_id = _make_entity("Partial COA Co")
    _set_account(entity_id, "4000", "Revenue", "revenue")
    # Deliberately don't classify 5000 or 6100
    _upload_gl(entity_id, tmp_path)

    resp = client.get(
        f"/entities/{entity_id}/profit-and-loss",
        params={"period_start": "2026-06-01", "period_end": "2026-06-30"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["unclassified_account_codes"]) == {"5000", "6100"}
    # Net income only reflects what was actually classified
    assert body["net_income"] == "25000.00"
