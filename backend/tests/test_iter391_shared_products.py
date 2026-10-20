"""iter391 — shared products: one catalogue entry, several stores, stock counted
per store."""
import os
import uuid
import requests

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


def _h():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _stores(h):
    locs = requests.get(f"{API}/locations", headers=h, timeout=30).json()
    rows = locs.get("locations") if isinstance(locs, dict) else locs
    return [loc["id"] for loc in rows][:2]


def _make(h, **fields):
    body = {"name": f"iter391 {uuid.uuid4().hex[:6]}", "price": 1000, "currency": "UGX",
            "stock": 0, "reorder_level": 2, **fields}
    r = requests.post(f"{API}/products", json=body, headers=h, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _get(h, pid, store=""):
    rows = requests.get(f"{API}/products", params={"location_id": store} if store else None,
                        headers=h, timeout=30).json()
    return next((p for p in rows if p["id"] == pid), None)


def test_universal_product_is_visible_from_every_store():
    h = _h()
    a, b = _stores(h)
    p = _make(h, is_universal=True, store_stock={a: 4, b: 9})
    try:
        assert _get(h, p["id"], a) is not None
        assert _get(h, p["id"], b) is not None
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_each_store_sees_its_own_stock_and_price():
    h = _h()
    a, b = _stores(h)
    p = _make(h, is_universal=True, store_stock={a: 4, b: 9}, store_prices={b: 1500})
    try:
        at_a, at_b = _get(h, p["id"], a), _get(h, p["id"], b)
        assert at_a["stock"] == 4 and at_b["stock"] == 9
        assert at_a["price"] == 1000, "store without an override must use the base price"
        assert at_b["price"] == 1500, "store price override ignored"
        # With no store in context the chain total is reported.
        assert _get(h, p["id"])["stock"] == 13
        assert at_a["shared"] is True
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_named_stores_only():
    h = _h()
    a, b = _stores(h)
    # Home store is A too, so B has no claim on it at all.
    p = _make(h, location_id=a, store_ids=[a], store_stock={a: 5})
    try:
        assert _get(h, p["id"], a) is not None
        assert _get(h, p["id"], b) is None, "a product listed for store A showed up at store B"
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_selling_at_one_store_does_not_touch_the_other():
    h = _h()
    a, b = _stores(h)
    p = _make(h, is_universal=True, store_stock={a: 4, b: 9})
    sale = None
    try:
        r = requests.post(f"{API}/sales", json={
            "items": [{"product_id": p["id"], "name": p["name"], "qty": 2, "unit_price": 1000, "total": 2000}],
            "total": 2000, "payment_method": "cash", "location_id": a,
        }, headers=h, timeout=30)
        assert r.status_code in (200, 201), r.text
        sale = r.json()
        assert _get(h, p["id"], a)["stock"] == 2, "selling store was not decremented"
        assert _get(h, p["id"], b)["stock"] == 9, "the other store's stock moved"
    finally:
        if sale:
            requests.post(f"{API}/sales/{sale['id']}/undo", json={"reason": "iter391 test"},
                          headers=h, timeout=30)
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_voiding_returns_stock_to_the_selling_store():
    h = _h()
    a, b = _stores(h)
    p = _make(h, is_universal=True, store_stock={a: 4, b: 9})
    try:
        sale = requests.post(f"{API}/sales", json={
            "items": [{"product_id": p["id"], "name": p["name"], "qty": 3, "unit_price": 1000, "total": 3000}],
            "total": 3000, "payment_method": "cash", "location_id": a,
        }, headers=h, timeout=30).json()
        assert _get(h, p["id"], a)["stock"] == 1
        v = requests.post(f"{API}/sales/{sale['id']}/undo", json={"reason": "iter391 test"},
                          headers=h, timeout=30)
        assert v.status_code == 200, v.text
        assert _get(h, p["id"], a)["stock"] == 4, "void did not restore the selling store"
        assert _get(h, p["id"], b)["stock"] == 9
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_stock_movement_needs_a_store_for_a_shared_product():
    h = _h()
    a, b = _stores(h)
    p = _make(h, is_universal=True, store_stock={a: 4, b: 9})
    try:
        vague = requests.post(f"{API}/products/{p['id']}/stock-movement",
                              json={"delta": 5, "reason": "purchase"}, headers=h, timeout=30)
        assert vague.status_code == 400, vague.text
        ok = requests.post(f"{API}/products/{p['id']}/stock-movement",
                           json={"delta": 5, "reason": "purchase", "location_id": b},
                           headers=h, timeout=30)
        assert ok.status_code == 200, ok.text
        assert ok.json()["before"] == 9 and ok.json()["after"] == 14
        assert _get(h, p["id"], a)["stock"] == 4
        assert _get(h, p["id"], b)["stock"] == 14
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_reorder_alerts_are_raised_per_store():
    h = _h()
    a, b = _stores(h)
    p = _make(h, is_universal=True, store_stock={a: 1, b: 40}, reorder_level=5)
    try:
        alerts = requests.get(f"{API}/products/reorder-alerts", headers=h, timeout=30).json()
        mine = [x for x in alerts if x["product_id"] == p["id"]]
        assert len(mine) == 1, f"expected only the short store to alert, got {mine}"
        assert mine[0]["location_id"] == a and mine[0]["stock"] == 1
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_a_variant_product_cannot_be_shared():
    h = _h()
    a, _ = _stores(h)
    r = requests.post(f"{API}/products", json={
        "name": f"iter391 variants {uuid.uuid4().hex[:6]}", "price": 1000, "is_universal": True,
        "has_variants": True, "variants": [{"id": "v1", "name": "Small", "stock": 3, "price": 1000}],
    }, headers=h, timeout=30)
    assert r.status_code == 400, r.text
    assert "variants" in r.json()["detail"].lower()


def test_becoming_shared_carries_the_existing_stock_to_its_home_store():
    """Flipping an ordinary product to shared must not look like stock vanished."""
    h = _h()
    a, _ = _stores(h)
    p = _make(h, stock=12, location_id=a)
    try:
        r = requests.put(f"{API}/products/{p['id']}", json={"is_universal": True},
                         headers=h, timeout=30)
        assert r.status_code == 200, r.text
        assert _get(h, p["id"], a)["stock"] == 12
    finally:
        requests.delete(f"{API}/products/{p['id']}", headers=h, timeout=30)


def test_a_product_saved_with_no_store_is_visible_again():
    """Legacy shape: `location_id: ""` with no store list. Such a product fell
    outside every campus filter and disappeared from the list. The API now
    always stamps a home campus, so this is asserted at the scope layer."""
    from routers.product_scope import available_at, availability_query, is_shared
    blank = {"id": "prod_legacy", "name": "Old import", "price": 10, "stock": 3, "location_id": ""}
    assert available_at(blank, "loc_anything") is True
    assert is_shared(blank) is False          # it is not "shared", just homeless
    clauses = availability_query(["loc_a"], "loc_b")["$or"]
    assert {"location_id": {"$in": ["", None]}, "store_ids": {"$in": [None, []]}} in clauses
    # And a product that does have a home is not caught by that clause.
    homed = {**blank, "location_id": "loc_a"}
    assert available_at(homed, "loc_b") is False
