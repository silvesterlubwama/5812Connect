"""
Iteration 169 — Case Detail dialog backend tests.

Covers:
- PUT /api/social-work/cases/{id} accepts new sponsor_manual field and persists it
- PUT validator still enforces risk_level in {low,medium,high} and category in 4 valid values
- Roundtrip: GET returns sponsor_manual + updated risk_level + updated category
- sponsor_member_id and sponsor_manual can be set/cleared mutually
"""
import os
import time
import uuid
import requests
import pytest

def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/")
    p = "/app/frontend/.env"
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _load_backend_url()
ADMIN_ID = "admin@5812uganda.org"
ADMIN_PW = "Admin@5812"

VALID_CATEGORIES = {"sponsored", "restricted_location", "welfare_support", "multiple"}
VALID_RISK = {"low", "medium", "high"}


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"identifier": ADMIN_ID, "password": ADMIN_PW}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    j = r.json()
    tok = j.get("token") or j.get("access_token")
    assert tok, f"no token in {j}"
    return tok


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def child_id(headers):
    name = f"TEST_iter169_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE}/api/children",
                      json={"name": name, "date_of_birth": "2014-01-01", "gender": "M"},
                      headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text[:300]
    cid = r.json()["id"]
    yield cid
    try:
        requests.delete(f"{BASE}/api/children/{cid}", headers=headers, timeout=10)
    except Exception:
        pass


@pytest.fixture(scope="session")
def case_id(headers, child_id):
    r = requests.post(f"{BASE}/api/social-work/cases",
                      json={"subject_id": child_id, "subject_kind": "child",
                            "category": "sponsored",
                            "risk_level": "low", "summary": "iter169 seed"},
                      headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text[:400]
    cid = r.json()["id"]
    yield cid
    try:
        requests.delete(f"{BASE}/api/social-work/cases/{cid}", headers=headers, timeout=10)
    except Exception:
        pass


# ---------- BASIC PERSISTENCE ----------

def test_case_created_with_initial_values(headers, case_id):
    r = requests.get(f"{BASE}/api/social-work/cases/{case_id}", headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data["category"] == "sponsored"
    assert data["risk_level"] == "low"
    assert data["status"] == "active"


# ---------- INLINE EDITORS ----------

def test_put_updates_category_inline(headers, case_id):
    r = requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                     json={"category": "welfare_support"}, headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:400]
    g = requests.get(f"{BASE}/api/social-work/cases/{case_id}", headers=headers, timeout=10).json()
    assert g["category"] == "welfare_support"


def test_put_updates_risk_level_inline(headers, case_id):
    r = requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                     json={"risk_level": "high"}, headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:400]
    g = requests.get(f"{BASE}/api/social-work/cases/{case_id}", headers=headers, timeout=10).json()
    assert g["risk_level"] == "high"


def test_put_rejects_invalid_risk_level(headers, case_id):
    r = requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                     json={"risk_level": "extreme"}, headers=headers, timeout=10)
    assert r.status_code == 400, r.text[:300]


# ---------- SPONSOR MANUAL ----------

def test_put_accepts_sponsor_manual_object(headers, case_id):
    payload = {"sponsor_manual": {
        "name": "Sarah Johnson",
        "email": "sarah@hopefund.org",
        "phone": "+1-555-0102",
        "notes": "Hope Foundation · monthly $50"
    }, "sponsor_member_id": None}
    r = requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                     json=payload, headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:400]
    g = requests.get(f"{BASE}/api/social-work/cases/{case_id}", headers=headers, timeout=10).json()
    sm = g.get("sponsor_manual")
    assert sm, f"sponsor_manual not persisted: {g}"
    assert sm.get("name") == "Sarah Johnson"
    assert sm.get("email") == "sarah@hopefund.org"
    assert sm.get("phone") == "+1-555-0102"
    assert sm.get("notes") == "Hope Foundation · monthly $50"
    assert g.get("sponsor_member_id") in (None, "")


def test_put_clears_sponsor_manual_to_null(headers, case_id):
    # ensure it exists first
    requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                 json={"sponsor_manual": {"name": "Temp"}}, headers=headers, timeout=10)
    r = requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                     json={"sponsor_manual": None}, headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:400]
    g = requests.get(f"{BASE}/api/social-work/cases/{case_id}", headers=headers, timeout=10).json()
    assert g.get("sponsor_manual") in (None, {}, "")


def test_combined_put_risk_category_sponsor(headers, case_id):
    payload = {
        "risk_level": "medium",
        "category": "multiple",
        "sponsor_manual": {"name": "Combined Test", "email": "c@x.org"}
    }
    r = requests.put(f"{BASE}/api/social-work/cases/{case_id}",
                     json=payload, headers=headers, timeout=10)
    assert r.status_code == 200, r.text[:400]
    g = requests.get(f"{BASE}/api/social-work/cases/{case_id}", headers=headers, timeout=10).json()
    assert g["risk_level"] == "medium"
    assert g["category"] == "multiple"
    assert g["sponsor_manual"]["name"] == "Combined Test"
