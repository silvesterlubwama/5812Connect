"""iter346 API integration tests via public URL: integrations mask, public shop payment options, boards sublocation, consumable tracking sheet."""
import os
import time
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-scope.preview.emergentagent.com").rstrip("/")
ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}


def _token():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_public_settings_reflects_online_payments_flag():
    tok = _token()
    # Fetch current
    cur = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    prev_payments = (cur.get("payments") or {}).copy()

    # Disable
    body = {**cur, "payments": {**prev_payments, "enabled": False}}
    r = requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)
    assert r.status_code == 200, r.text
    pub = requests.get(f"{BASE}/api/admin/system-settings/public", timeout=20).json()
    pay = pub.get("payments") or {}
    assert pay.get("online_enabled") in (False, None), pay

    # Enable with dummy keys
    body["payments"] = {
        **prev_payments,
        "enabled": True,
        "mode": "test",
        "secret_key": "FLWSECK_TEST-dummy0000abcd1234",
        "public_key": "FLWPUBK_TEST-dummy",
        "webhook_hash": "h",
        "allow_card": True,
        "allow_mobile_money": True,
        "allow_pay_on_collection": True,
        "currency": "UGX",
    }
    r = requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)
    assert r.status_code == 200
    # Read back (admin) — must be masked, no cleartext
    got = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    pmts = got.get("payments") or {}
    blob = str(pmts)
    assert "FLWSECK_TEST-dummy0000abcd1234" not in blob, "secret key must not leak"
    assert pmts.get("secret_key_set") is True
    assert pmts.get("secret_key_masked", "").endswith("1234"), pmts

    # Public endpoint exposes enabled + methods but NOT secret
    pub = requests.get(f"{BASE}/api/admin/system-settings/public", timeout=20).json()
    pay = pub.get("payments") or {}
    assert pay.get("online_enabled") is True, pay
    assert "secret_key" not in pay, pay


def test_shop_collection_order_when_online_disabled():
    tok = _token()
    cur = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    prev = (cur.get("payments") or {}).copy()
    body = {**cur, "payments": {**prev, "enabled": False}}
    requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)

    prods = requests.get(f"{BASE}/api/public/products", timeout=20).json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    if not items:
        return  # nothing to buy
    p = next((x for x in items if (x.get("stock") or 0) > 0), items[0])
    payload = {
        "items": [{"product_id": p["id"], "qty": 1}],
        "name": "TEST_iter346",
        "email": "TEST_iter346@example.org",
        "phone": "+256700000000",
        "payment_option": "collection",
    }
    r = requests.post(f"{BASE}/api/public/orders", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    js = r.json()
    assert js.get("reference") or js.get("receipt_number") or js.get("id"), js


def test_shop_online_disabled_rejects_pay_now():
    tok = _token()
    cur = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    prev = (cur.get("payments") or {}).copy()
    body = {**cur, "payments": {**prev, "enabled": False}}
    requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)

    prods = requests.get(f"{BASE}/api/public/products", timeout=20).json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    if not items:
        return
    p = items[0]
    payload = {
        "items": [{"product_id": p["id"], "qty": 1}],
        "name": "TEST_iter346",
        "email": "TEST_iter346@example.org",
        "phone": "+256700000000",
        "payment_option": "online",
        "online_method": "card",
    }
    r = requests.post(f"{BASE}/api/public/orders", json=payload, timeout=30)
    assert r.status_code in (400, 403, 503), r.status_code


def test_shop_online_momo_requires_phone():
    tok = _token()
    cur = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    prev = (cur.get("payments") or {}).copy()
    body = {**cur, "payments": {
        **prev, "enabled": True, "mode": "test",
        "secret_key": "FLWSECK_TEST-dummy", "public_key": "FLWPUBK_TEST-dummy",
        "webhook_hash": "h", "allow_card": True, "allow_mobile_money": True,
        "allow_pay_on_collection": True, "currency": "UGX",
    }}
    requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)

    prods = requests.get(f"{BASE}/api/public/products", timeout=20).json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    if not items:
        return
    p = items[0]
    stock_before = p.get("stock")
    payload = {
        "items": [{"product_id": p["id"], "qty": 1}],
        "name": "TEST_iter346",
        "email": "TEST_iter346@example.org",
        "phone": "",
        "payment_option": "online",
        "online_method": "mobile_money",
        "network": "MTN",
    }
    r = requests.post(f"{BASE}/api/public/orders", json=payload, timeout=30)
    assert r.status_code == 400, (r.status_code, r.text)
    # Stock should not have changed
    prods2 = requests.get(f"{BASE}/api/public/products", timeout=20).json()
    items2 = prods2 if isinstance(prods2, list) else prods2.get("items", [])
    p2 = next((x for x in items2 if x["id"] == p["id"]), None)
    if p2 is not None:
        assert p2.get("stock") == stock_before, (stock_before, p2.get("stock"))


def test_shop_online_card_rolls_back_stock_on_bad_keys():
    tok = _token()
    cur = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    body = {**cur, "payments": {
        **(cur.get("payments") or {}), "enabled": True, "mode": "test",
        "secret_key": "FLWSECK_TEST-invalidkey", "public_key": "FLWPUBK_TEST-invalid",
        "webhook_hash": "h", "allow_card": True, "allow_mobile_money": True,
        "allow_pay_on_collection": True, "currency": "UGX",
    }}
    requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)

    prods = requests.get(f"{BASE}/api/public/products", timeout=20).json()
    items = prods if isinstance(prods, list) else prods.get("items", [])
    if not items:
        return
    p = next((x for x in items if (x.get("stock") or 0) > 0), items[0])
    stock_before = p.get("stock")
    payload = {
        "items": [{"product_id": p["id"], "qty": 1}],
        "name": "TEST_iter346",
        "email": "TEST_iter346@example.org",
        "phone": "+256700000000",
        "payment_option": "online",
        "online_method": "card",
    }
    r = requests.post(f"{BASE}/api/public/orders", json=payload, timeout=30)
    # Provider handshake fails => 4xx/5xx and no stock deducted
    assert r.status_code >= 400, r.text
    time.sleep(0.5)
    prods2 = requests.get(f"{BASE}/api/public/products", timeout=20).json()
    items2 = prods2 if isinstance(prods2, list) else prods2.get("items", [])
    p2 = next((x for x in items2 if x["id"] == p["id"]), None)
    if p2 is not None and stock_before is not None:
        assert p2.get("stock") == stock_before, (stock_before, p2.get("stock"))


def test_boards_include_sublocation_boards():
    """iter346: boards under a sub-location that lives only in db.sublocations
    (parent is a location_id, not a campus) must be visible in GET /api/boards."""
    # Seed a board under sub-location 34b3c253... if not present
    import asyncio, sys
    sys.path.insert(0, "/app/backend")
    from deps import db as _db  # type: ignore

    target_sub = "34b3c253-140e-4ccc-984d-4c311445d9f0"

    async def _seed():
        sub = await _db.sublocations.find_one({"id": target_sub}, {"_id": 0})
        if not sub:
            return None
        b = await _db.boards.find_one({"location_id": target_sub}, {"_id": 0})
        if not b:
            board = {"id": "TEST_iter346_board_sub", "name": "TEST Kitchen Board",
                     "location_id": target_sub, "created_by": "someone-else",
                     "columns": [{"id": "todo", "name": "To Do"}]}
            await _db.boards.insert_one(board)
            return board
        return b

    seeded = asyncio.run(_seed())
    assert seeded, "sub-location 34b3c253... not in db.sublocations — cannot verify"

    tok = _token()
    r = requests.get(f"{BASE}/api/boards", headers=_h(tok), timeout=20)
    assert r.status_code == 200, r.text
    boards = r.json()
    matching = [b for b in boards if b.get("location_id") == target_sub]
    print(f"boards total={len(boards)} matching_sub={len(matching)}")
    assert len(matching) >= 1, f"expected sub-location board; ids={[b.get('id') for b in boards]}"
    r2 = requests.get(f"{BASE}/api/boards/{matching[0]['id']}", headers=_h(tok), timeout=20)
    assert r2.status_code == 200, r2.text


def test_consumable_tracking_sheet_html():
    tok = _token()
    # Find a consumable resource
    r = requests.get(f"{BASE}/api/resources", headers=_h(tok), timeout=20)
    assert r.status_code == 200
    lst = r.json()
    items = lst if isinstance(lst, list) else lst.get("items", [])
    cons = [x for x in items if x.get("is_consumable") is True]
    assert cons, "expected at least one consumable resource (Posho)"
    rid = cons[0]["id"]
    # Try both variants
    r1 = requests.get(f"{BASE}/api/resources/{rid}/tracking-sheet?month=2026-01", headers=_h(tok), timeout=30)
    assert r1.status_code == 200, r1.text
    ct = r1.headers.get("content-type", "")
    assert "html" in ct.lower() or "<html" in r1.text.lower(), (ct, r1.text[:200])


def test_bank_accounts_list_ok():
    tok = _token()
    r = requests.get(f"{BASE}/api/bank/accounts", headers=_h(tok), timeout=20)
    assert r.status_code == 200, r.text
    accs = r.json()
    assert isinstance(accs, list) and len(accs) >= 1, accs
    # Every account must expose id + linked_account_id (needed for ledger drill-down)
    for a in accs:
        assert a.get("id"), a
        # linked_account_id is what powers the transactions/ledger dialog
        assert "linked_account_id" in a, a


def test_reset_payments_disabled_at_end():
    tok = _token()
    cur = requests.get(f"{BASE}/api/admin/system-settings", headers=_h(tok), timeout=20).json()
    body = {**cur, "payments": {"enabled": False, "mode": "test", "secret_key": "", "public_key": "",
                                 "webhook_hash": "", "allow_card": True, "allow_mobile_money": True,
                                 "allow_pay_on_collection": True, "currency": "UGX"}}
    r = requests.put(f"{BASE}/api/admin/system-settings", json=body, headers=_h(tok), timeout=20)
    assert r.status_code == 200
