"""Iter209 - Finance starting_balance derivation from chart accounts (Option A).

Tests:
- GET /api/financial/accounts new schema fields
- Chart accounts as source of truth for starting_balance
- Legacy fallback
- balance = starting + income - expenses
- POST /api/financial/repair-starting-balances idempotent + admin-only
- Regression: trial-balance still balanced; repair-orphaned-journals still idempotent
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_ID = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def campus_id(admin_headers):
    # find first campus
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    locs = r.json()
    campuses = [l for l in locs if (l.get("type") or "").lower() == "campus"]
    assert campuses, "No campuses found"
    return campuses[0]["id"]


@pytest.fixture(scope="module")
def sublocation_id(admin_headers, campus_id):
    r = requests.get(f"{BASE_URL}/api/locations", headers=admin_headers, timeout=30)
    subs = [l for l in r.json() if l.get("parent_id") == campus_id]
    if not subs:
        # fall back: use campus itself
        return campus_id
    return subs[0]["id"]


# ---------- SEED: create an active chart account with starting_balance ----------
@pytest.fixture(scope="module")
def seeded_chart_account(admin_headers, sublocation_id, campus_id):
    payload = {
        "name": "TEST_iter209_opening",
        "kind": "cash",
        "currency": "UGX",
        "starting_balance": 12345.0,
        "location_id": sublocation_id,
        "campus_id": campus_id,
        "notes": "iter209 test seed",
    }
    r = requests.post(f"{BASE_URL}/api/financial/chart-accounts",
                      headers=admin_headers, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"Chart account create failed: {r.status_code} {r.text}"
    doc = r.json()
    yield doc
    # cleanup - deactivate (delete may not exist / cascade concerns)
    try:
        requests.patch(f"{BASE_URL}/api/financial/chart-accounts/{doc['id']}",
                       headers=admin_headers, json={"active": False, "starting_balance": 0}, timeout=15)
    except Exception:
        pass


class TestFinancialAccountsSchema:
    def test_schema_new_fields_present(self, admin_headers, campus_id, seeded_chart_account):
        r = requests.get(f"{BASE_URL}/api/financial/accounts",
                         headers=admin_headers, params={"campus_id": campus_id}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # top-level new fields
        for k in ("campus_starting_balance", "campus_balance", "campus_net_change", "accounts"):
            assert k in data, f"Missing top-level key: {k}"
        assert data["accounts"], "No accounts returned"
        for acct in data["accounts"]:
            for k in ("starting_balance", "starting_balance_source",
                      "legacy_starting_balance", "total_income", "total_expenses", "balance"):
                assert k in acct, f"Missing per-account key {k} in {acct}"
            assert acct["starting_balance_source"] in ("chart_accounts", "legacy")

    def test_chart_accounts_source_of_truth(self, admin_headers, campus_id,
                                            sublocation_id, seeded_chart_account):
        """For a location with an active chart account with starting_balance>0,
        account.starting_balance == sum of those chart account starting balances."""
        # Fetch chart accounts at this location to compute expected sum
        r_ca = requests.get(f"{BASE_URL}/api/financial/chart-accounts",
                            headers=admin_headers, timeout=30)
        assert r_ca.status_code == 200
        cas = r_ca.json()
        loc_cas = [c for c in cas
                   if c.get("location_id") == sublocation_id
                   and c.get("active", True) is not False
                   and float(c.get("starting_balance") or 0) > 0]
        expected = round(sum(float(c.get("starting_balance") or 0) for c in loc_cas), 2)
        assert expected > 0, "Seed missing"

        r = requests.get(f"{BASE_URL}/api/financial/accounts",
                         headers=admin_headers, params={"campus_id": campus_id}, timeout=30)
        assert r.status_code == 200
        target = next((a for a in r.json()["accounts"] if a["location_id"] == sublocation_id), None)
        assert target, f"No account row for location {sublocation_id}"
        assert target["starting_balance_source"] == "chart_accounts", target
        assert round(float(target["starting_balance"]), 2) == expected, \
            f"starting_balance={target['starting_balance']} expected={expected}"

    def test_balance_formula(self, admin_headers, campus_id, seeded_chart_account):
        r = requests.get(f"{BASE_URL}/api/financial/accounts",
                         headers=admin_headers, params={"campus_id": campus_id}, timeout=30)
        assert r.status_code == 200
        for acct in r.json()["accounts"]:
            expected = round(float(acct["starting_balance"])
                             + float(acct["total_income"])
                             - float(acct["total_expenses"]), 2)
            assert round(float(acct["balance"]), 2) == expected, \
                f"balance mismatch on {acct['location_id']}: got {acct['balance']} expected {expected}"

    def test_legacy_fallback(self, admin_headers, campus_id, seeded_chart_account):
        """Rows with starting_balance_source == 'legacy' must have starting_balance == legacy_starting_balance."""
        r = requests.get(f"{BASE_URL}/api/financial/accounts",
                         headers=admin_headers, params={"campus_id": campus_id}, timeout=30)
        assert r.status_code == 200
        for acct in r.json()["accounts"]:
            if acct["starting_balance_source"] == "legacy":
                assert round(float(acct["starting_balance"]), 2) == round(float(acct["legacy_starting_balance"]), 2), \
                    f"Legacy row {acct['location_id']}: starting_balance != legacy_starting_balance"


class TestRepairStartingBalances:
    def test_repair_non_admin_forbidden(self):
        # Attempt without token → 401/403; and with a manager? We only have admin creds.
        r = requests.post(f"{BASE_URL}/api/financial/repair-starting-balances", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}"

    def test_repair_admin_and_idempotent(self, admin_headers):
        r1 = requests.post(f"{BASE_URL}/api/financial/repair-starting-balances",
                           headers=admin_headers, timeout=60)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert "migrated" in d1 and "skipped_already_migrated" in d1 and "created_accounts" in d1
        # Second run: idempotent
        r2 = requests.post(f"{BASE_URL}/api/financial/repair-starting-balances",
                           headers=admin_headers, timeout=60)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["migrated"] == [], f"Second run migrated non-empty: {d2['migrated']}"
        assert d2["created_accounts"] == [], f"Second run created accounts: {d2['created_accounts']}"
        # Skipped should include (at least) previously-migrated ones. Length is
        # driven by legacy rows still >0, which after run 1 should be 0. So
        # this asserts the endpoint at least returned successfully; we accept
        # any int length for skipped_already_migrated on the second run.
        assert isinstance(d2["skipped_already_migrated"], list)

    def test_after_migration_source_chart_accounts(self, admin_headers, campus_id):
        r = requests.get(f"{BASE_URL}/api/financial/accounts",
                         headers=admin_headers, params={"campus_id": campus_id}, timeout=30)
        assert r.status_code == 200
        # For rows where legacy_starting_balance > 0 previously, after migration
        # they should now report starting_balance_source == 'chart_accounts'.
        # Post-migration legacy field is zeroed, so we just assert that any row
        # with a non-zero starting_balance uses the chart_accounts source.
        for a in r.json()["accounts"]:
            if float(a["starting_balance"]) > 0:
                assert a["starting_balance_source"] == "chart_accounts", \
                    f"After migration, {a['location_id']} still 'legacy' with sb={a['starting_balance']}"


class TestRegressions:
    def test_trial_balance_balanced(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/accounting/reports/trial-balance",
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        debits = float(data.get("total_debits") or data.get("debits") or 0)
        credits = float(data.get("total_credits") or data.get("credits") or 0)
        assert round(debits, 2) == round(credits, 2), f"Trial balance NOT balanced: debits={debits} credits={credits}"

    def test_repair_orphaned_journals_idempotent(self, admin_headers):
        r1 = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                           headers=admin_headers, timeout=60)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{BASE_URL}/api/financial/repair-orphaned-journals",
                           headers=admin_headers, timeout=60)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        # second run should not repair anything new
        for key in ("deleted", "reversed", "removed", "repaired"):
            if key in d2 and isinstance(d2[key], (list, int)):
                v = d2[key] if isinstance(d2[key], int) else len(d2[key])
                assert v == 0, f"repair-orphaned-journals not idempotent on '{key}': {d2[key]}"
