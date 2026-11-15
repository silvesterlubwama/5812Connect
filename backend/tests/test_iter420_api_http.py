# iter420 HTTP regression: screens (public token endpoints), waiters/tips, batch compare, store-settings gate
import os
import uuid

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
STORE = "loc_59a87857"
TAG = f"ZTMP_{uuid.uuid4().hex[:5]}"

_mongo = MongoClient(os.environ.get("MONGO_URL"))[os.environ.get("DB_NAME")]
CREATED = {"screens": [], "orders": [], "products": [], "batches": [], "losses": []}


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"identifier": "admin@5812uganda.org", "password": "Admin@5812"})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    tok = r.json().get("token") or r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    yield s
    # cleanup only what we created
    for sid in CREATED["screens"]:
        s.delete(f"{BASE_URL}/api/screens/{sid}")
    _mongo.device_screens.delete_many({"id": {"$in": CREATED["screens"]}})
    _mongo.kitchen_orders.delete_many({"id": {"$in": CREATED["orders"]}})
    _mongo.stock_losses.delete_many({"id": {"$in": CREATED["losses"]}})
    _mongo.stock_batches.delete_many({"product_id": {"$in": CREATED["products"]}})
    _mongo.stock_movements.delete_many({"product_id": {"$in": CREATED["products"]}})
    _mongo.products.delete_many({"id": {"$in": CREATED["products"]}})


def _pair(admin, kind):
    r = admin.post(f"{BASE_URL}/api/screens", json={"kind": kind, "location_id": STORE,
                                                    "name": f"{TAG} {kind}"})
    assert r.status_code == 200, r.text
    scr = r.json()["screen"]
    CREATED["screens"].append(scr["id"])
    assert isinstance(scr["token"], str) and len(scr["token"]) > 8
    return scr


# --- store settings gate
class TestStoreSettings:
    def test_can_manage_restaurant(self, admin):
        r = admin.get(f"{BASE_URL}/api/store-settings/{STORE}")
        assert r.status_code == 200
        assert r.json()["can_manage_restaurant"] is True

    def test_put_restaurant_mode_roundtrip(self, admin):
        before = admin.get(f"{BASE_URL}/api/store-settings/{STORE}").json().get("restaurant_mode", False)
        r = admin.put(f"{BASE_URL}/api/store-settings/{STORE}", json={"restaurant_mode": not before})
        assert r.status_code == 200, r.text
        assert admin.get(f"{BASE_URL}/api/store-settings/{STORE}").json()["restaurant_mode"] is (not before)
        admin.put(f"{BASE_URL}/api/store-settings/{STORE}", json={"restaurant_mode": before})
        assert admin.get(f"{BASE_URL}/api/store-settings/{STORE}").json()["restaurant_mode"] is before


# --- screens: pairing + public endpoints
class TestScreens:
    def test_bad_kind_rejected(self, admin):
        r = admin.post(f"{BASE_URL}/api/screens", json={"kind": "tv", "location_id": STORE})
        assert r.status_code == 400

    def test_pair_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/screens", json={"kind": "kitchen", "location_id": STORE})
        assert r.status_code in (401, 403)

    def test_kitchen_public_flow(self, admin):
        scr = _pair(admin, "kitchen")
        info = requests.get(f"{BASE_URL}/api/screens/{scr['token']}")
        assert info.status_code == 200, info.text
        assert info.json()["kind"] == "kitchen" and info.json()["location_id"] == STORE
        # a ticket from the till
        o = admin.post(f"{BASE_URL}/api/kitchen/orders", json={
            "location_id": STORE, "table_label": f"{TAG}-T1",
            "items": [{"name": f"{TAG} stew", "qty": 1, "price": 9000},
                      {"name": f"{TAG} chips", "qty": 2, "price": 3000}]})
        assert o.status_code == 200, o.text
        order = o.json()["order"]
        CREATED["orders"].append(order["id"])
        board = requests.get(f"{BASE_URL}/api/screens/{scr['token']}/orders")
        assert board.status_code == 200
        mine = [x for x in board.json() if x["id"] == order["id"]]
        assert mine and mine[0]["total"] == 15000
        line = order["items"][0]["line_id"]
        adv = requests.patch(f"{BASE_URL}/api/screens/{scr['token']}/orders/{order['id']}/items/{line}")
        assert adv.status_code == 200, adv.text
        assert adv.json()["status"] != "new"
        whole = requests.patch(f"{BASE_URL}/api/screens/{scr['token']}/orders/{order['id']}",
                               json={"status": "ready"})
        assert whole.status_code == 200 and whole.json()["status"] == "ready"
        # cross-kind
        assert requests.get(f"{BASE_URL}/api/screens/{scr['token']}/sale").status_code == 400
        # revoke
        d = admin.delete(f"{BASE_URL}/api/screens/{scr['id']}")
        assert d.status_code == 200
        assert requests.get(f"{BASE_URL}/api/screens/{scr['token']}").status_code == 404
        assert requests.get(f"{BASE_URL}/api/screens/{scr['token']}/orders").status_code == 404

    def test_sales_display_live_feed(self, admin):
        till = f"{TAG}-till"
        r = admin.post(f"{BASE_URL}/api/screens", json={"kind": "sales", "location_id": STORE,
                                                        "name": f"{TAG} display", "till_id": till})
        scr = r.json()["screen"]
        CREATED["screens"].append(scr["id"])
        idle = requests.get(f"{BASE_URL}/api/screens/{scr['token']}/sale")
        assert idle.status_code == 200 and idle.json()["state"] == "idle"
        push = admin.post(f"{BASE_URL}/api/screens/live-sale", json={
            "location_id": STORE, "till_id": till, "state": "selling", "subtotal": 7000, "total": 7000,
            "lines": [{"name": f"{TAG} soda", "qty": 2, "price": 3500, "line_total": 7000}]})
        assert push.status_code == 200
        live = requests.get(f"{BASE_URL}/api/screens/{scr['token']}/sale").json()
        assert live["total"] == 7000 and live["lines"][0]["name"] == f"{TAG} soda"
        assert requests.get(f"{BASE_URL}/api/screens/{scr['token']}/orders").status_code == 400
        _mongo.live_sales.delete_many({"key": f"{STORE}|{till}"})

    def test_live_sale_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/screens/live-sale", json={"location_id": STORE})
        assert r.status_code in (401, 403)

    def test_unknown_token_404(self):
        assert requests.get(f"{BASE_URL}/api/screens/nope_{TAG}").status_code == 404


# --- waiters & tips
class TestWaiters:
    def test_server_tip_and_report(self, admin):
        o = admin.post(f"{BASE_URL}/api/kitchen/orders", json={
            "location_id": STORE, "table_label": f"{TAG}-T2", "server_id": f"{TAG}-waiter",
            "server_name": f"{TAG} Waiter", "items": [{"name": f"{TAG} goat", "qty": 2, "price": 12000}]})
        assert o.status_code == 200
        order = o.json()["order"]
        CREATED["orders"].append(order["id"])
        assert order["server_name"] == f"{TAG} Waiter"
        st = admin.patch(f"{BASE_URL}/api/kitchen/orders/{order['id']}/settle",
                         json={"sale_id": f"{TAG}-sale", "tip": 2500})
        assert st.status_code == 200 and st.json()["tip"] == 2500
        rep = admin.get(f"{BASE_URL}/api/kitchen/servers", params={"location_id": STORE})
        assert rep.status_code == 200
        me = next(s for s in rep.json()["servers"] if s["server_id"] == f"{TAG}-waiter")
        assert me["tables"] == 1 and me["tips"] == 2500 and me["takings"] == 24000 and me["open_tabs"] == 0

    def test_settle_without_sale_400(self, admin):
        o = admin.post(f"{BASE_URL}/api/kitchen/orders", json={
            "location_id": STORE, "items": [{"name": f"{TAG} tea", "qty": 1, "price": 1000}]}).json()["order"]
        CREATED["orders"].append(o["id"])
        assert admin.patch(f"{BASE_URL}/api/kitchen/orders/{o['id']}/settle", json={}).status_code == 400


# --- batch comparison
class TestCompare:
    def test_compare_two_runs(self, admin):
        target = admin.post(f"{BASE_URL}/api/products", json={
            "name": f"{TAG} Broilers", "price": 15000, "stock": 0, "location_id": STORE}).json()
        CREATED["products"].append(target["id"])
        chick = admin.post(f"{BASE_URL}/api/products", json={
            "name": f"{TAG} Chicks", "price": 4000, "stock": 0, "location_id": STORE,
            "grows_into_product_id": target["id"], "grow_after_days": 28}).json()
        CREATED["products"].append(chick["id"])
        _mongo.products.update_one({"id": chick["id"]}, {"$set": {"stock": 150}})
        a = admin.post(f"{BASE_URL}/api/stock-batches", json={
            "product_id": chick["id"], "qty": 50, "location_id": STORE,
            "received_at": "2026-01-01T08:00:00", "supplier": f"{TAG} Kabira"})
        assert a.status_code == 200, a.text
        b = admin.post(f"{BASE_URL}/api/stock-batches", json={
            "product_id": chick["id"], "qty": 100, "location_id": STORE})
        assert b.status_code == 200
        a_id, b_id = a.json()["batch"]["id"], b.json()["batch"]["id"]
        p = admin.patch(f"{BASE_URL}/api/stock-batches/{b_id}", json={"supplier": f"{TAG} Nsambya"})
        assert p.status_code == 200 and p.json()["batch"]["supplier"] == f"{TAG} Nsambya"
        loss = admin.post(f"{BASE_URL}/api/stock-losses", json={
            "product_id": chick["id"], "qty": 10, "reason": "died", "location_id": STORE, "batch_id": a_id})
        assert loss.status_code == 200, loss.text
        lj = loss.json()
        lid = (lj.get("loss") or {}).get("id") or lj.get("id")
        if lid:
            CREATED["losses"].append(lid)
        rep = admin.get(f"{BASE_URL}/api/stock-batches/compare", params={"ids": f"{a_id},{b_id}"})
        assert rep.status_code == 200, rep.text
        d = rep.json()
        assert len(d["batches"]) == 2
        assert d["batches"][0]["supplier"] == f"{TAG} Kabira"
        assert d["batches"][0]["mortality_pct"] == 20.0 and d["batches"][0]["survival_pct"] == 80.0
        assert d["batches"][1]["mortality_pct"] == 0
        assert isinstance(d["batches"][0]["weeks"], list) and len(d["batches"][0]["weeks"]) >= 1
        assert d["by_supplier"][0]["supplier"] == f"{TAG} Kabira"
        assert f"{TAG} Kabira" in d["verdict"]

    def test_compare_one_id_400(self, admin):
        assert admin.get(f"{BASE_URL}/api/stock-batches/compare", params={"ids": "x"}).status_code == 400

    def test_patch_missing_batch_404(self, admin):
        assert admin.patch(f"{BASE_URL}/api/stock-batches/nope_{TAG}", json={"supplier": "x"}).status_code == 404
