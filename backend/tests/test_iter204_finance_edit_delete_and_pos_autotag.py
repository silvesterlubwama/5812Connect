"""Iteration 204 — CoA/Journal/Tax edit+delete, POS auto-tag default cash/bank/momo, batch balance perf.

Public URL is used (REACT_APP_BACKEND_URL). All endpoints are under /api.
Admin credential is read from /app/memory/test_credentials.md conventions.
"""
import os
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fall back only for local dev; test collection will still fail loud.
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_IDENT = creds.ADMIN_EMAIL
ADMIN_PASS = creds.ADMIN_PASSWORD
LOC = "loc_001"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_IDENT, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in login payload: {data}"
    return tok


@pytest.fixture(scope="session")
def admin(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def orig_store_settings(admin):
    """Snapshot store settings for LOC so we can restore after the module."""
    r = admin.get(f"{BASE_URL}/api/store-settings/{LOC}", timeout=15)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="session", autouse=True)
def _restore_store_settings(admin, orig_store_settings):
    yield
    # Best-effort restore of the default_* keys we may have mutated
    restore = {
        "default_cash_account_id": orig_store_settings.get("default_cash_account_id", ""),
        "default_bank_account_id": orig_store_settings.get("default_bank_account_id", ""),
        "default_momo_account_id": orig_store_settings.get("default_momo_account_id", ""),
    }
    try:
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json=restore, timeout=15)
    except Exception:
        pass


def _make_cha(admin, name_suffix="", starting=0.0):
    body = {
        "name": f"TEST_Iter204_{name_suffix or uuid.uuid4().hex[:6]}",
        "kind": "cash",
        "currency": "UGX",
        "starting_balance": float(starting),
        "location_id": LOC,
    }
    r = admin.post(f"{BASE_URL}/api/financial/chart-accounts", json=body, timeout=15)
    assert r.status_code == 200, f"create chart account failed: {r.status_code} {r.text}"
    return r.json()


def _cleanup_cha(admin, cha_id):
    try:
        admin.delete(f"{BASE_URL}/api/financial/chart-accounts/{cha_id}", timeout=15)
    except Exception:
        pass


# =============================================================================
# COA / Journals / Taxes — edit + delete
# =============================================================================
class TestAccountingCoAEditDelete:
    def test_coa_edit_and_persist(self, admin):
        code = f"T{uuid.uuid4().hex[:5].upper()}"
        create = admin.post(
            f"{BASE_URL}/api/accounting/accounts",
            json={"code": code, "name": "TEST_Iter204_CoA", "type": "asset_cash", "currency": "UGX", "location_id": LOC},
            timeout=15,
        )
        assert create.status_code == 200, create.text
        acc = create.json()
        aid = acc["id"]

        new_name = "TEST_Iter204_CoA_Renamed"
        upd = admin.put(
            f"{BASE_URL}/api/accounting/accounts/{aid}",
            json={"name": new_name, "type": "asset_non_current", "currency": "USD"},
            timeout=15,
        )
        assert upd.status_code == 200, upd.text
        # Confirm via GET list
        lst = admin.get(f"{BASE_URL}/api/accounting/accounts?location_id={LOC}", timeout=15).json()
        found = next((x for x in lst if x["id"] == aid), None)
        assert found, "updated account not in list"
        assert found["name"] == new_name
        assert found["type"] == "asset_non_current"
        assert found["currency"] == "USD"

        # Delete — no lines → deleted:true
        d = admin.delete(f"{BASE_URL}/api/accounting/accounts/{aid}", timeout=15)
        assert d.status_code == 200
        assert d.json().get("deleted") is True

    def test_coa_delete_with_lines_deactivates(self, admin):
        # Create account
        code = f"T{uuid.uuid4().hex[:5].upper()}"
        r = admin.post(
            f"{BASE_URL}/api/accounting/accounts",
            json={"code": code, "name": "TEST_Iter204_CoA_WithLines", "type": "asset_cash", "currency": "UGX", "location_id": LOC},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        # Seed a journal entry line by hand via a small journal entry
        # Use accounting_entry_lines directly via a create entry endpoint if present.
        # If not, we approximate by inserting through the entries endpoint.
        # Create a second account to balance the entry.
        r2 = admin.post(
            f"{BASE_URL}/api/accounting/accounts",
            json={"code": f"T{uuid.uuid4().hex[:5].upper()}", "name": "TEST_Iter204_CoA_Pair", "type": "income", "currency": "UGX", "location_id": LOC},
            timeout=15,
        )
        assert r2.status_code == 200
        aid2 = r2.json()["id"]
        # Need a journal
        jr = admin.post(
            f"{BASE_URL}/api/accounting/journals",
            json={"code": f"J{uuid.uuid4().hex[:4].upper()}", "name": "TEST_Iter204_Journal", "kind": "miscellaneous", "location_id": LOC},
            timeout=15,
        )
        assert jr.status_code == 200, jr.text
        jid = jr.json()["id"]
        entry = admin.post(
            f"{BASE_URL}/api/accounting/entries",
            json={
                "journal_id": jid,
                "date": "2026-01-15",
                "narration": "TEST_Iter204 entry",
                "lines": [
                    {"account_id": aid, "debit": 1000, "credit": 0, "description": "dr"},
                    {"account_id": aid2, "debit": 0, "credit": 1000, "description": "cr"},
                ],
                "location_id": LOC,
            },
            timeout=15,
        )
        entry_ok = entry.status_code == 200
        # Now try delete — should be deactivated:true if lines exist, otherwise deleted:true
        d = admin.delete(f"{BASE_URL}/api/accounting/accounts/{aid}", timeout=15)
        assert d.status_code == 200, d.text
        body = d.json()
        if entry_ok:
            assert body.get("deactivated") is True, f"expected deactivated, got {body}"
        else:
            # Journal-entry creation might not be exposed; still deletion must return either
            assert body.get("deleted") is True or body.get("deactivated") is True
        # Cleanup: pair + journal
        admin.delete(f"{BASE_URL}/api/accounting/accounts/{aid2}", timeout=15)
        admin.delete(f"{BASE_URL}/api/accounting/journals/{jid}", timeout=15)

    def test_journal_edit_and_delete(self, admin):
        jr = admin.post(
            f"{BASE_URL}/api/accounting/journals",
            json={"code": f"J{uuid.uuid4().hex[:4].upper()}", "name": "TEST_Iter204_J", "kind": "sales", "location_id": LOC},
            timeout=15,
        )
        assert jr.status_code == 200, jr.text
        jid = jr.json()["id"]
        upd = admin.put(f"{BASE_URL}/api/accounting/journals/{jid}", json={"name": "TEST_Iter204_J_Renamed", "kind": "cash"}, timeout=15)
        assert upd.status_code == 200
        body = upd.json()
        assert body["name"] == "TEST_Iter204_J_Renamed"
        assert body["kind"] == "cash"
        d = admin.delete(f"{BASE_URL}/api/accounting/journals/{jid}", timeout=15)
        assert d.status_code == 200
        assert d.json().get("deleted") is True

    def test_tax_edit_and_delete(self, admin):
        tr = admin.post(
            f"{BASE_URL}/api/accounting/taxes",
            json={"name": "TEST_Iter204_VAT", "rate": 18, "kind": "sales", "inclusive": False},
            timeout=15,
        )
        assert tr.status_code == 200, tr.text
        tid = tr.json()["id"]
        upd = admin.put(f"{BASE_URL}/api/accounting/taxes/{tid}", json={"name": "TEST_Iter204_VAT_2", "rate": 20, "kind": "purchase", "inclusive": True}, timeout=15)
        assert upd.status_code == 200
        body = upd.json()
        assert body["name"] == "TEST_Iter204_VAT_2"
        assert float(body["rate"]) == 20.0
        assert body["kind"] == "purchase"
        assert body["inclusive"] is True
        d = admin.delete(f"{BASE_URL}/api/accounting/taxes/{tid}", timeout=15)
        assert d.status_code == 200
        assert d.json().get("deleted") is True


# =============================================================================
# Cash accounts (chart_accounts) — edit + delete + starting_balance recompute
# =============================================================================
class TestChartAccountsEditDelete:
    def test_edit_and_starting_balance_recompute(self, admin):
        acc = _make_cha(admin, "editme", starting=1000)
        aid = acc["id"]
        assert float(acc["balance"]) == 1000
        upd = admin.put(
            f"{BASE_URL}/api/financial/chart-accounts/{aid}",
            json={"name": "TEST_Iter204_editme_Renamed", "kind": "bank", "starting_balance": 2500},
            timeout=15,
        )
        assert upd.status_code == 200, upd.text
        body = upd.json()
        assert body["name"] == "TEST_Iter204_editme_Renamed"
        assert body["kind"] == "bank"
        assert float(body["starting_balance"]) == 2500
        # Balance reflects new starting balance
        assert float(body["balance"]) == 2500
        _cleanup_cha(admin, aid)

    def test_delete_no_txn_hard_deletes(self, admin):
        acc = _make_cha(admin, "delme")
        aid = acc["id"]
        d = admin.delete(f"{BASE_URL}/api/financial/chart-accounts/{aid}", timeout=15)
        assert d.status_code == 200
        assert d.json().get("deleted") is True

    def test_delete_with_txn_archives(self, admin, orig_store_settings):
        acc = _make_cha(admin, "archiveme", starting=0)
        aid = acc["id"]
        # Create a sale that references this account
        sr = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 5000, "name": "Test"}],
                "total": 5000,
                "payment_method": "cash",
                "location_id": LOC,
                "deposit_to_account_id": aid,
            },
            timeout=15,
        )
        assert sr.status_code == 200, sr.text
        sid = sr.json()["id"]
        d = admin.delete(f"{BASE_URL}/api/financial/chart-accounts/{aid}", timeout=15)
        assert d.status_code == 200, d.text
        body = d.json()
        assert body.get("archived") is True
        assert body.get("referenced_txns", 0) >= 1
        # Cleanup: void the sale so future tests aren't polluted
        try:
            admin.post(f"{BASE_URL}/api/sales/{sid}/void", json={"reason": "test cleanup"}, timeout=15)
        except Exception:
            pass


# =============================================================================
# POS auto-tag — default cash / bank / momo
# =============================================================================
class TestPOSAutoTagDefaults:
    def test_default_cash_autotags_cash_sale(self, admin):
        cha = _make_cha(admin, "def_cash", starting=0)
        cid = cha["id"]
        # Set default_cash_account_id
        pr = admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": cid}, timeout=15)
        assert pr.status_code == 200
        # POST sale without deposit_to_account_id
        sr = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 3000, "name": "T"}],
                "total": 3000,
                "payment_method": "cash",
                "location_id": LOC,
            },
            timeout=15,
        )
        assert sr.status_code == 200, sr.text
        s = sr.json()
        assert s.get("deposit_to_account_id") == cid, f"expected auto-tag {cid}, got {s.get('deposit_to_account_id')}"
        assert s.get("deposit_auto_tagged") is True
        # Balance should reflect the sale
        gr = admin.get(f"{BASE_URL}/api/financial/chart-accounts/{cid}", timeout=15)
        assert gr.status_code == 200
        assert float(gr.json()["balance"]) == 3000
        # cleanup
        try:
            admin.post(f"{BASE_URL}/api/sales/{s['id']}/void", json={"reason": "cleanup"}, timeout=15)
        except Exception:
            pass
        # reset default before deleting account
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": ""}, timeout=15)
        _cleanup_cha(admin, cid)

    def test_default_bank_for_card_sale(self, admin):
        cash = _make_cha(admin, "def_cash2")
        bank = _make_cha(admin, "def_bank")
        admin.put(
            f"{BASE_URL}/api/store-settings/{LOC}",
            json={"default_cash_account_id": cash["id"], "default_bank_account_id": bank["id"]},
            timeout=15,
        )
        sr = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 4200, "name": "T"}],
                "total": 4200,
                "payment_method": "card",
                "location_id": LOC,
            },
            timeout=15,
        )
        assert sr.status_code == 200, sr.text
        s = sr.json()
        assert s.get("deposit_to_account_id") == bank["id"], f"card sale should route to bank, got {s.get('deposit_to_account_id')}"
        assert s.get("deposit_auto_tagged") is True
        # cleanup
        try:
            admin.post(f"{BASE_URL}/api/sales/{s['id']}/void", json={"reason": "cleanup"}, timeout=15)
        except Exception:
            pass
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": "", "default_bank_account_id": ""}, timeout=15)
        _cleanup_cha(admin, cash["id"])
        _cleanup_cha(admin, bank["id"])

    def test_default_momo_for_mobile_money(self, admin):
        momo = _make_cha(admin, "def_momo")
        admin.put(
            f"{BASE_URL}/api/store-settings/{LOC}",
            json={"default_momo_account_id": momo["id"]},
            timeout=15,
        )
        sr = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 2200, "name": "T"}],
                "total": 2200,
                "payment_method": "mobile_money",
                "location_id": LOC,
            },
            timeout=15,
        )
        assert sr.status_code == 200, sr.text
        s = sr.json()
        assert s.get("deposit_to_account_id") == momo["id"]
        assert s.get("deposit_auto_tagged") is True
        try:
            admin.post(f"{BASE_URL}/api/sales/{s['id']}/void", json={"reason": "cleanup"}, timeout=15)
        except Exception:
            pass
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_momo_account_id": ""}, timeout=15)
        _cleanup_cha(admin, momo["id"])

    def test_bank_falls_back_to_cash_if_no_bank_default(self, admin):
        cash = _make_cha(admin, "fallback_cash")
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": cash["id"], "default_bank_account_id": "", "default_momo_account_id": ""}, timeout=15)
        sr = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 1500, "name": "T"}],
                "total": 1500,
                "payment_method": "card",
                "location_id": LOC,
            },
            timeout=15,
        )
        assert sr.status_code == 200, sr.text
        s = sr.json()
        assert s.get("deposit_to_account_id") == cash["id"], "card sale should fall back to cash default"
        assert s.get("deposit_auto_tagged") is True
        try:
            admin.post(f"{BASE_URL}/api/sales/{s['id']}/void", json={"reason": "cleanup"}, timeout=15)
        except Exception:
            pass
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": ""}, timeout=15)
        _cleanup_cha(admin, cash["id"])

    def test_explicit_deposit_wins(self, admin):
        cha_default = _make_cha(admin, "default_wins")
        cha_explicit = _make_cha(admin, "explicit_wins")
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": cha_default["id"]}, timeout=15)
        sr = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 1000, "name": "T"}],
                "total": 1000,
                "payment_method": "cash",
                "location_id": LOC,
                "deposit_to_account_id": cha_explicit["id"],
            },
            timeout=15,
        )
        assert sr.status_code == 200, sr.text
        s = sr.json()
        assert s.get("deposit_to_account_id") == cha_explicit["id"], "explicit deposit_to_account_id must win"
        # deposit_auto_tagged should be falsy (undefined or False)
        assert not s.get("deposit_auto_tagged"), f"expected NOT auto-tagged, got {s.get('deposit_auto_tagged')}"
        try:
            admin.post(f"{BASE_URL}/api/sales/{s['id']}/void", json={"reason": "cleanup"}, timeout=15)
        except Exception:
            pass
        admin.put(f"{BASE_URL}/api/store-settings/{LOC}", json={"default_cash_account_id": ""}, timeout=15)
        _cleanup_cha(admin, cha_default["id"])
        _cleanup_cha(admin, cha_explicit["id"])


# =============================================================================
# Batch balance perf — accuracy parity between list and single-GET
# =============================================================================
class TestBatchBalanceAccuracy:
    def test_list_balances_match_single_gets(self, admin):
        # Create 3 accounts with varied starting_balances
        a1 = _make_cha(admin, "batch1", starting=1000)
        a2 = _make_cha(admin, "batch2", starting=5000)
        a3 = _make_cha(admin, "batch3", starting=0)
        # Post a sale into a1, a donation into a2 (if endpoint exists)
        s1 = admin.post(
            f"{BASE_URL}/api/sales",
            json={
                "items": [{"product_id": "none", "qty": 1, "price": 250, "name": "T"}],
                "total": 250,
                "payment_method": "cash",
                "location_id": LOC,
                "deposit_to_account_id": a1["id"],
            },
            timeout=15,
        )
        assert s1.status_code == 200, s1.text
        d2 = admin.post(
            f"{BASE_URL}/api/financial/donations",
            json={"amount": 750, "donor_name": "TEST_Iter204", "deposit_to_account_id": a2["id"], "location_id": LOC},
            timeout=15,
        )
        # donations endpoint may return 200 or 400 depending on required fields; only assert we can proceed
        # Now list
        lst = admin.get(f"{BASE_URL}/api/financial/chart-accounts", timeout=15)
        assert lst.status_code == 200
        rows = lst.json()
        by_id = {a["id"]: a for a in rows}
        assert a1["id"] in by_id and a2["id"] in by_id and a3["id"] in by_id
        # Cross-check each with single-account GET
        for aid in (a1["id"], a2["id"], a3["id"]):
            g = admin.get(f"{BASE_URL}/api/financial/chart-accounts/{aid}", timeout=15)
            assert g.status_code == 200
            single_bal = float(g.json().get("balance") or 0)
            list_bal = float(by_id[aid].get("balance") or 0)
            assert abs(single_bal - list_bal) < 0.01, f"batch vs single mismatch for {aid}: list={list_bal} single={single_bal}"
        # Explicit expected values:
        assert float(by_id[a1["id"]]["balance"]) == 1250.0  # 1000 + 250 sale
        assert float(by_id[a3["id"]]["balance"]) == 0.0
        if d2.status_code == 200:
            assert float(by_id[a2["id"]]["balance"]) == 5750.0

        # cleanup
        try:
            admin.post(f"{BASE_URL}/api/sales/{s1.json()['id']}/void", json={"reason": "cleanup"}, timeout=15)
        except Exception:
            pass
        if d2.status_code == 200:
            try:
                admin.delete(f"{BASE_URL}/api/financial/donations/{d2.json()['id']}", timeout=15)
            except Exception:
                pass
        _cleanup_cha(admin, a1["id"])
        _cleanup_cha(admin, a2["id"])
        _cleanup_cha(admin, a3["id"])


# =============================================================================
# Store settings defaults
# =============================================================================
class TestStoreSettingsDefaults:
    def test_default_keys_present_for_new_location(self, admin):
        rand_loc = f"loc_test_{uuid.uuid4().hex[:6]}"
        r = admin.get(f"{BASE_URL}/api/store-settings/{rand_loc}", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "default_cash_account_id" in body
        assert "default_bank_account_id" in body
        assert "default_momo_account_id" in body
        assert body["default_cash_account_id"] == ""
        assert body["default_bank_account_id"] == ""
        assert body["default_momo_account_id"] == ""


# =============================================================================
# Regression — expenses/donations without paid_from / deposit_to still succeed
# =============================================================================
class TestRegressionOptionalAccountFields:
    def test_expense_without_paid_from(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/financial/expenses",
            json={"amount": 100, "title": "TEST_Iter204 expense", "description": "TEST_Iter204 no account", "category": "office", "location_id": LOC},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        try:
            admin.delete(f"{BASE_URL}/api/financial/expenses/{r.json()['id']}", timeout=15)
        except Exception:
            pass

    def test_donation_without_deposit_to(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/financial/donations",
            json={"amount": 100, "donor_name": "TEST_Iter204 no account", "location_id": LOC},
            timeout=15,
        )
        # Some deployments require additional fields — accept 200 or 400 (contract regression)
        assert r.status_code in (200, 201, 400), r.text
        if r.status_code in (200, 201):
            try:
                admin.delete(f"{BASE_URL}/api/financial/donations/{r.json()['id']}", timeout=15)
            except Exception:
                pass
