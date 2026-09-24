"""iter367 — sub-location departments + fixed-asset improvements vs repairs.

Two user reports:
  • "when entering a transaction, sublocation departments aren't being loaded"
    — the form asked for departments using the PARENT campus id, and the
    endpoint had no way to answer for a sub-location.
  • "how should we deal with fixed assets and their improvement expenses"
    — spending that extends life/capacity is capitalised onto the asset;
    spending that just keeps it working is a repairs expense.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER367_{uuid.uuid4().hex[:6]}"
state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def teardown_module():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    if state.get("asset"):
        requests.delete(f"{BASE}/finance/assets/{state['asset']}", headers=h, timeout=30)


# ---------- departments for sub-locations ----------

def _locations(head):
    rows = requests.get(f"{BASE}/locations", headers=head, timeout=30).json()
    parents = [l for l in rows if not l.get("parent_id")]
    subs = [l for l in rows if l.get("parent_id")]
    return parents, subs


def test_sublocation_departments_are_returned(head):
    parents, subs = _locations(head)
    assert subs, "no sub-locations configured"
    sub = subs[0]
    campus_only = requests.get(f"{BASE}/departments", params={"location_id": sub["parent_id"]},
                               headers=head, timeout=30).json()
    with_sub = requests.get(f"{BASE}/departments",
                            params={"location_id": sub["parent_id"], "sublocation_id": sub["id"]},
                            headers=head, timeout=30).json()
    names_campus = {d["name"] for d in campus_only}
    names_sub = {d["name"] for d in with_sub}
    # the sub-location call must be a superset — campus-wide ones stay usable
    assert names_campus <= names_sub
    own = [d for d in with_sub if d.get("location_id") == sub["id"] or d.get("sublocation_id") == sub["id"]]
    if own:
        # its own departments are listed first
        assert with_sub[0] in own


def test_passing_a_sublocation_as_location_id_also_works(head):
    """The form can send just the picked id — the API resolves the parent."""
    _, subs = _locations(head)
    sub = subs[0]
    direct = requests.get(f"{BASE}/departments", params={"location_id": sub["id"]},
                          headers=head, timeout=30).json()
    explicit = requests.get(f"{BASE}/departments",
                            params={"location_id": sub["parent_id"], "sublocation_id": sub["id"]},
                            headers=head, timeout=30).json()
    assert {d["id"] for d in direct} == {d["id"] for d in explicit}


# ---------- fixed assets: improvements vs repairs ----------

def test_create_asset_and_capitalise_an_improvement(head):
    r = requests.post(f"{BASE}/finance/assets", headers=head, timeout=30, json={
        "name": f"{TAG} Hiace van", "category": "vehicle", "value": 12000,
        "purchase_date": "2024-02-01", "depreciation_years": 8,
    })
    assert r.status_code == 200, r.text
    state["asset"] = r.json()["id"]

    imp = requests.post(f"{BASE}/finance/assets/{state['asset']}/spend", headers=head,
                        timeout=30, json={"kind": "improvement", "amount": 2500,
                                          "description": "Replacement engine", "vendor": "Kampala Motors",
                                          "extends_life_years": 3})
    assert imp.status_code == 200, imp.text
    asset = imp.json()["asset"]
    assert asset["improvements_total"] == 2500.0
    assert asset["total_cost"] == 14500.0, "an improvement must raise the carried cost"
    assert asset["repairs_total"] == 0
    assert asset["depreciation_years"] == 11, "extra life should extend the useful life"


def test_repair_does_not_change_the_asset_value(head):
    rep = requests.post(f"{BASE}/finance/assets/{state['asset']}/spend", headers=head,
                        timeout=30, json={"kind": "repair", "amount": 180,
                                          "description": "Service and new tyres"})
    assert rep.status_code == 200, rep.text
    asset = rep.json()["asset"]
    assert asset["repairs_total"] == 180.0
    assert asset["improvements_total"] == 2500.0
    assert asset["total_cost"] == 14500.0, "a repair is an expense, not part of the asset"


def test_register_totals_and_validation(head):
    reg = requests.get(f"{BASE}/finance/assets", headers=head, timeout=30)
    assert reg.status_code == 200
    body = reg.json()
    mine = next(a for a in body["assets"] if a["id"] == state["asset"])
    assert mine["total_cost"] == 14500.0
    assert body["improvements_total"] >= 2500.0

    bad = requests.post(f"{BASE}/finance/assets/{state['asset']}/spend", headers=head,
                        timeout=30, json={"kind": "improvement", "amount": 0, "description": "x"})
    assert bad.status_code == 400
    no_desc = requests.post(f"{BASE}/finance/assets/{state['asset']}/spend", headers=head,
                            timeout=30, json={"kind": "improvement", "amount": 50})
    assert no_desc.status_code == 400
    wrong_kind = requests.post(f"{BASE}/finance/assets/{state['asset']}/spend", headers=head,
                               timeout=30, json={"kind": "capital", "amount": 50, "description": "x"})
    assert wrong_kind.status_code == 400


def test_removing_an_improvement_rolls_the_cost_back(head):
    asset = requests.get(f"{BASE}/finance/assets/{state['asset']}", headers=head, timeout=30).json()
    entry = next(e for e in asset["spend"] if e["kind"] == "improvement")
    r = requests.delete(f"{BASE}/finance/assets/{state['asset']}/spend/{entry['id']}",
                        headers=head, timeout=30)
    assert r.status_code == 200, r.text
    after = r.json()["asset"]
    assert after["improvements_total"] == 0
    assert after["total_cost"] == 12000.0
    assert after["depreciation_years"] == 8, "the extra life should come back off"


def test_valuation_endpoint_works(head):
    """This route used to be a dangling decorator on the reconciliation handler."""
    r = requests.put(f"{BASE}/finance/assets/{state['asset']}/valuation", headers=head,
                     timeout=30, json={"current_value": 9000, "basis": "market check"})
    assert r.status_code == 200, r.text
    assert r.json()["current_value"] == 9000.0
