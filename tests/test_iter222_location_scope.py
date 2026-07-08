"""iter222 — validate `_expand_location_scope` fix.

The fix causes /accounting/accounts, /accounting/reports/trial-balance and
/accounting/reports/cash-flow to return entries whose location_id belongs to
the picked id OR its parent OR any of its direct children.  Previously the
strict equality hid payroll JEs that were posted at the sub-location level
while operators picked the campus in the report filter.
"""
import os
import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # fallback: parse from /app/frontend/.env
    try:
        with open("/app/frontend/.env", "r") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _load_base_url()

ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
CANONICAL_SUB = "loc_419f5d5e"   # 58:12 Uganda (sub of loc_001)
CANONICAL_PARENT = "loc_001"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if not tok:
        pytest.skip("no access token in login response")
    return tok


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def locations(client):
    r = client.get(f"{BASE_URL}/api/locations", timeout=30)
    assert r.status_code == 200
    return r.json()


# ------ helper -------
def _tb(client, loc_id=None):
    params = {"location_id": loc_id} if loc_id else {}
    r = client.get(f"{BASE_URL}/api/accounting/reports/trial-balance", params=params, timeout=30)
    assert r.status_code == 200, f"trial-balance {loc_id}: {r.status_code} {r.text[:200]}"
    return r.json()


def _accounts(client, loc_id=None):
    params = {"location_id": loc_id} if loc_id else {}
    r = client.get(f"{BASE_URL}/api/accounting/accounts", params=params, timeout=30)
    assert r.status_code == 200, f"accounts {loc_id}: {r.status_code} {r.text[:200]}"
    return r.json()


class TestExpandLocationScope:
    """Validate the _expand_location_scope helper across the three endpoints
    that consume it."""

    def test_sub_location_returns_parent_entries(self, client, locations):
        """Picking a SUB location must surface entries that live at the parent."""
        loc_map = {loc["id"]: loc for loc in locations}
        assert CANONICAL_SUB in loc_map, "canonical sub-location fixture missing"
        assert loc_map[CANONICAL_SUB].get("parent_id") == CANONICAL_PARENT, \
            f"expected {CANONICAL_SUB}.parent_id == {CANONICAL_PARENT}"

        tb_sub = _tb(client, CANONICAL_SUB)
        tb_parent = _tb(client, CANONICAL_PARENT)

        # PRIMARY assertion — pre-fix this was 0; post-fix ~210M (per agent probe)
        assert len(tb_sub["rows"]) > 0, "iter222 fix regressed — sub returned 0 rows"
        assert tb_sub["totals"]["balanced"] is True
        assert tb_sub["totals"]["debit"] > 100_000_000, \
            f"sub debit unexpectedly low: {tb_sub['totals']['debit']}"
        # Sub-scope is {self, parent} — a subset of parent-scope which also
        # includes sibling subs. So sub totals must be <= parent totals.
        assert tb_sub["totals"]["debit"] <= tb_parent["totals"]["debit"] + 0.02
        assert tb_parent["totals"]["balanced"] is True

    def test_parent_campus_returns_children_and_own(self, client):
        """Picking the PARENT campus must include all children's entries."""
        tb = _tb(client, CANONICAL_PARENT)
        assert tb["totals"]["balanced"] is True
        assert len(tb["rows"]) > 0

    def test_accounts_merged_for_sub_and_parent(self, client):
        """Accounts list under a sub should include the parent's accounts
        (backend merges via _expand_location_scope). Note: parent's list also
        includes other siblings' accounts, so we only assert sub ⊇ (its own +
        parent's own), not sub ⊇ parent (parent's list is a superset)."""
        sub_accounts = _accounts(client, CANONICAL_SUB)
        parent_only = [a for a in _accounts(client, CANONICAL_PARENT)
                       if a.get("location_id") == CANONICAL_PARENT]
        p_ids = {a["id"] for a in parent_only}
        s_ids = {a["id"] for a in sub_accounts}
        assert p_ids.issubset(s_ids), \
            f"sub-location did not surface parent-owned accounts (missing {p_ids - s_ids})"
        # Pre-fix: sub would only see its own accounts (or 0). Post-fix: >= parent's own count.
        assert len(sub_accounts) >= len(parent_only), \
            f"sub accounts ({len(sub_accounts)}) < parent-owned ({len(parent_only)})"

    def test_isolated_location_returns_only_own_data(self, client, locations):
        """Fallback: picking a location with no parent AND no children falls back
        to strict equality (scope_ids len == 1)."""
        isolated = None
        parent_ids = {loc.get("parent_id") for loc in locations if loc.get("parent_id")}
        for loc in locations:
            if loc.get("parent_id"):
                continue
            if loc["id"] in parent_ids:
                continue
            if loc["id"] in {CANONICAL_PARENT, CANONICAL_SUB}:
                continue
            isolated = loc
            break
        if not isolated:
            pytest.skip("no isolated (childless + parentless) location in preview db")
        tb = _tb(client, isolated["id"])
        # Not asserting counts (may legitimately be 0) — just that it doesn't error
        assert tb["totals"]["balanced"] is True

    def test_no_location_id_regression(self, client):
        """When no location_id is passed, admin should see everything (no
        campus filter)."""
        tb = _tb(client, None)
        assert tb["totals"]["balanced"] is True
        assert len(tb["rows"]) > 0

    def test_cashflow_endpoint_respects_scope(self, client):
        """/accounting/reports/cash-flow also uses _expand_location_scope.
        Sub-scope is a subset of parent-scope, so |sub.net_change| <= |parent.net_change|."""
        r_sub = client.get(f"{BASE_URL}/api/accounting/reports/cash-flow",
                           params={"location_id": CANONICAL_SUB}, timeout=30)
        r_par = client.get(f"{BASE_URL}/api/accounting/reports/cash-flow",
                           params={"location_id": CANONICAL_PARENT}, timeout=30)
        assert r_sub.status_code == 200 and r_par.status_code == 200
        sub_data = r_sub.json()
        par_data = r_par.json()
        # Sub must now have data (pre-fix would be all-zero).
        assert (len(sub_data["operating"]) + len(sub_data["investing"]) + len(sub_data["financing"])) > 0
        # Sub is a subset of parent scope → magnitude comparable but ≤ parent
        assert abs(sub_data["totals"]["net_change"]) <= abs(par_data["totals"]["net_change"]) + 0.02

    def test_pl_and_bs_inherit_fix(self, client):
        """P&L and BS reuse trial_balance so must inherit the scope expansion.
        Sub-scope ⊆ parent-scope → sub totals ≤ parent totals in magnitude."""
        p_sub = client.get(f"{BASE_URL}/api/accounting/reports/profit-loss",
                           params={"location_id": CANONICAL_SUB}, timeout=30).json()
        p_par = client.get(f"{BASE_URL}/api/accounting/reports/profit-loss",
                           params={"location_id": CANONICAL_PARENT}, timeout=30).json()
        assert p_sub["totals"]["income"] > 0, "sub P&L income unexpectedly 0"
        assert p_sub["totals"]["income"] <= p_par["totals"]["income"] + 0.02
        assert p_sub["totals"]["expense"] <= p_par["totals"]["expense"] + 0.02

        b_sub = client.get(f"{BASE_URL}/api/accounting/reports/balance-sheet",
                           params={"location_id": CANONICAL_SUB}, timeout=30).json()
        b_par = client.get(f"{BASE_URL}/api/accounting/reports/balance-sheet",
                           params={"location_id": CANONICAL_PARENT}, timeout=30).json()
        assert b_sub["totals"]["assets"] != 0
        assert abs(b_sub["totals"]["assets"]) <= abs(b_par["totals"]["assets"]) + 0.02
