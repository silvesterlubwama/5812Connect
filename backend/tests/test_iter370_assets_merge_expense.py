"""iter370 — assets: merge, optional real expense entry, currency, edit, delete.

User reports:
  • "allow asset merging"
  • "allow option expense entry when adding a new asset or when logging expense,
     use existing expense entry route if choosing the expense option"
  • "looks like asset expense is using USD instead of the active currency"
  • "allow editing of asset details" … "and deletion"
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER370_{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    for key in ("keep", "dupe", "plain"):
        if state.get(key):
            requests.delete(f"{BASE}/finance/assets/{state[key]}", headers=h, timeout=30)
    for eid in state.get("expenses", []):
        requests.delete(f"{BASE}/finance/journal/{eid}", headers=h, timeout=30)


def test_create_asset_in_the_active_currency(head):
    r = requests.post(f"{BASE}/finance/assets", headers=head, timeout=30, json={
        "name": f"{TAG} Borehole", "category": "building", "value": 4500000,
        "currency": "UGX", "purchase_date": "2026-01-15"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["currency"] == "UGX", body
    assert body.get("purchase_expense_id") in (None, ""), "no expense unless asked for"
    state["keep"] = body["id"]


def test_purchase_can_post_a_real_expense(head):
    r = requests.get(f"{BASE}/locations", headers=head, timeout=30)
    state["loc"] = r.json()[0]["id"]
    r = requests.post(f"{BASE}/finance/assets", headers=head, timeout=30, json={
        "name": f"{TAG} Tractor", "category": "vehicle", "value": 12000,
        "currency": "USD", "purchase_date": "2026-02-01", "vendor": f"{TAG} Supplier",
        "location_id": state["loc"], "post_expense": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["purchase_expense_id"], "the expense route should have been used"
    state["dupe"] = body["id"]
    state.setdefault("expenses", []).append(body["purchase_expense_id"])

    r = requests.get(f"{BASE}/finance/journal/{body['purchase_expense_id']}", headers=head, timeout=30)
    assert r.status_code == 200, r.text
    je = r.json()
    assert float(je["total"]) == 12000, je
    assert any("Asset purchase" in (l.get("memo") or "") or "Asset purchase" in (je.get("description") or "")
               for l in je.get("lines", [])) or "Asset purchase" in je.get("description", ""), je


def test_spend_keeps_the_assets_currency_and_can_be_expensed(head):
    requests.put(f"{BASE}/finance/assets/{state['keep']}", headers=head, timeout=30,
                 json={"location_id": state["loc"]})
    r = requests.post(f"{BASE}/finance/assets/{state['keep']}/spend", headers=head, timeout=30, json={
        "kind": "repair", "amount": 250000, "description": "Replaced the pump seals",
        "vendor": f"{TAG} Mechanic", "post_expense": True,
        "location_id": state["loc"]})
    assert r.status_code == 200, r.text
    entry = r.json()["entry"]
    assert entry["currency"] == "UGX", "spend must inherit the asset's currency, not USD"
    assert entry["expense_id"], entry
    state.setdefault("expenses", []).append(entry["expense_id"])
    r2 = requests.get(f"{BASE}/finance/journal/{entry['expense_id']}", headers=head, timeout=30)
    assert r2.status_code == 200 and float(r2.json()["total"]) == 250000, r2.text
    assert r.json()["asset"]["repairs_total"] == 250000
    assert r.json()["asset"]["total_cost"] == 4500000, "a repair never changes the cost"


def test_improvement_still_capitalises(head):
    r = requests.post(f"{BASE}/finance/assets/{state['keep']}/spend", headers=head, timeout=30, json={
        "kind": "improvement", "amount": 500000, "description": "Deepened by 20m",
        "extends_life_years": 3})
    assert r.status_code == 200, r.text
    assert r.json()["asset"]["total_cost"] == 5000000, r.json()["asset"]


def test_edit_asset_details(head):
    r = requests.put(f"{BASE}/finance/assets/{state['keep']}", headers=head, timeout=30, json={
        "name": f"{TAG} Borehole (north)", "condition": "fair", "serial_number": "BH-77",
        "value": 4600000, "currency": "UGX"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"].endswith("(north)") and body["condition"] == "fair", body
    assert body["serial_number"] == "BH-77" and body["value"] == 4600000, body


def test_merge_folds_history_into_the_kept_asset(head):
    before = requests.get(f"{BASE}/finance/assets/{state['keep']}", headers=head, timeout=30).json()
    r = requests.post(f"{BASE}/finance/assets/merge", headers=head, timeout=30, json={
        "target_id": state["keep"], "source_ids": [state["dupe"]], "combine_values": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["asset"]["value"] == round(before["value"] + 12000, 2), body["asset"]
    assert body["merged"][0]["id"] == state["dupe"]
    state["dupe"] = None
    r = requests.get(f"{BASE}/finance/assets/{state['keep']}", headers=head, timeout=30)
    assert len(r.json().get("merged_assets") or []) == 1
    assert requests.get(f"{BASE}/finance/assets/{body['merged'][0]['id']}",
                        headers=head, timeout=30).status_code == 404


def test_merge_needs_two_different_assets(head):
    r = requests.post(f"{BASE}/finance/assets/merge", headers=head, timeout=30, json={
        "target_id": state["keep"], "source_ids": [state["keep"]]})
    assert r.status_code == 400, r.text


def test_delete_asset(head):
    r = requests.post(f"{BASE}/finance/assets", headers=head, timeout=30, json={
        "name": f"{TAG} Scrap", "value": 10})
    state["plain"] = r.json()["id"]
    r = requests.delete(f"{BASE}/finance/assets/{state['plain']}", headers=head, timeout=30)
    assert r.status_code == 200 and r.json()["deleted"] is True, r.text
    assert requests.get(f"{BASE}/finance/assets/{state['plain']}", headers=head, timeout=30).status_code == 404
    state["plain"] = None
