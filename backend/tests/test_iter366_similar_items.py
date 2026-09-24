"""iter366 — similar-item consolidation for customs paperwork.

"Blankets" in box 24 and "blanket" in box 25 read as two consignment lines at
customs. These tests cover finding those groups, combining them into one line
with the quantity/value added up and boxes written "Boxes 24 & 25", combining
only within one box, deleting a straight repeat, and undoing a combine.
"""
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
TAG = f"ITER366_{uuid.uuid4().hex[:6]}"

state = {}


@pytest.fixture(scope="module")
def head():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def shipment(head):
    r = requests.post(f"{BASE}/shipments", json={"name": f"{TAG} shipment"}, headers=head, timeout=30)
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    state["sid"] = sid
    boxes = {}
    for no in (24, 25):
        b = requests.post(f"{BASE}/shipments/{sid}/packing-units",
                          json={"name": f"Box {no} – {TAG}", "type": "box"}, headers=head, timeout=30)
        assert b.status_code in (200, 201), b.text
        body = b.json()
        boxes[no] = body.get("id") or (body.get("unit") or {}).get("id")
    state["boxes"] = boxes

    def add(name, qty, value, box_no=None, **extra):
        payload = {"name": name, "qty_needed": qty, "qty_acquired": qty, "value_usd": value, **extra}
        if box_no:
            payload["packing_unit_id"] = boxes[box_no]
        rr = requests.post(f"{BASE}/shipments/{sid}/items", json=payload, headers=head, timeout=30)
        assert rr.status_code in (200, 201), rr.text
        return rr.json()["id"]

    state["blanket_a"] = add("Blankets", 10, 5, 24)
    state["blanket_b"] = add("blanket", 6, 5, 25)
    state["repeat_a"] = add("Kitchen pots", 4, 12, 24)
    state["repeat_b"] = add("Kitchen pots", 4, 12, 24)
    state["unrelated"] = add("Chest freezer", 1, 200, 25)
    yield sid
    requests.delete(f"{BASE}/shipments/{sid}", headers=head, timeout=30)


def _groups(head, sensitivity="normal"):
    r = requests.get(f"{BASE}/shipments/{state['sid']}/similar-items",
                     params={"sensitivity": sensitivity}, headers=head, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_finds_the_blanket_group_across_two_boxes(head):
    body = _groups(head)
    grp = next((g for g in body["groups"] if "blanket" in g["label"].lower()), None)
    assert grp, body
    assert grp["same_box"] is False
    assert grp["box_label"] == "Boxes 24 & 25"
    assert grp["total_qty"] == 16
    assert grp["total_value"] == 80.0
    assert grp["suggested_action"] == "combine_across_boxes"
    # the unrelated freezer must not be dragged in
    assert all("freezer" not in i["name"].lower() for i in grp["items"])


def test_flags_the_exact_repeat_in_one_box(head):
    body = _groups(head)
    grp = next((g for g in body["groups"] if "pots" in g["label"].lower()), None)
    assert grp, body
    assert grp["same_box"] is True
    assert grp["exact_repeat"] is True
    assert grp["suggested_action"] == "delete_repeats"
    assert grp["box_label"] == "Box 24"


def test_combine_across_boxes_keeps_the_line_total(head):
    r = requests.post(f"{BASE}/shipments/{state['sid']}/items/consolidate",
                      json={"keep_id": state["blanket_a"], "merge_ids": [state["blanket_b"]],
                            "mode": "combine", "name": "Blankets"},
                      headers=head, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["qty_acquired"] == 16
    assert body["line_value"] == 80.0
    assert body["box_label"] == "Boxes 24 & 25"

    detail = requests.get(f"{BASE}/shipments/{state['sid']}", headers=head, timeout=30).json()
    items = {i["id"]: i for i in detail["items"]}
    assert state["blanket_b"] not in items, "the merged row should be gone"
    kept = items[state["blanket_a"]]
    assert kept["qty_acquired"] == 16
    assert kept["value_usd"] == 5.0
    assert kept["consolidated"] is True
    assert kept["box_label"] == "Boxes 24 & 25"
    assert len(kept["consolidated_items"]) == 1


def test_undo_restores_the_original_rows(head):
    r = requests.post(f"{BASE}/shipments/{state['sid']}/items/{state['blanket_a']}/undo-consolidate",
                      headers=head, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["restored"] == 1
    detail = requests.get(f"{BASE}/shipments/{state['sid']}", headers=head, timeout=30).json()
    items = {i["id"]: i for i in detail["items"]}
    assert state["blanket_b"] in items
    assert items[state["blanket_a"]]["qty_acquired"] == 10
    assert items[state["blanket_a"]]["consolidated"] is False


def test_delete_repeats_removes_only_the_duplicate(head):
    r = requests.post(f"{BASE}/shipments/{state['sid']}/items/consolidate",
                      json={"keep_id": state["repeat_a"], "merge_ids": [state["repeat_b"]],
                            "mode": "delete_repeats"}, headers=head, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["removed"] == 1
    detail = requests.get(f"{BASE}/shipments/{state['sid']}", headers=head, timeout=30).json()
    items = {i["id"]: i for i in detail["items"]}
    assert state["repeat_b"] not in items
    assert items[state["repeat_a"]]["qty_acquired"] == 4, "the kept line must not be inflated"


def test_same_box_mode_refuses_when_nothing_shares_the_box(head):
    r = requests.post(f"{BASE}/shipments/{state['sid']}/items/consolidate",
                      json={"keep_id": state["blanket_a"], "merge_ids": [state["blanket_b"]],
                            "mode": "combine_same_box"}, headers=head, timeout=30)
    assert r.status_code == 400
    assert "box" in r.json()["detail"].lower()


def test_manifest_pdf_still_renders_after_consolidation(head):
    requests.post(f"{BASE}/shipments/{state['sid']}/items/consolidate",
                  json={"keep_id": state["blanket_a"], "merge_ids": [state["blanket_b"]],
                        "mode": "combine"}, headers=head, timeout=30)
    r = requests.get(f"{BASE}/shipments/{state['sid']}/manifest.pdf", headers=head, timeout=60)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
