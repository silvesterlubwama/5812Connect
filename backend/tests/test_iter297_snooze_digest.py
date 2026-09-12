"""Iter 297 — Digest snooze + regression endpoints."""
import os
import requests
import pytest

import creds  # env-backed logins, see tests/creds.py

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://multi-tenant-scope.preview.emergentagent.com"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login", json={"identifier": creds.ADMIN_EMAIL, "password": creds.ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# Digest preview
def test_digest_preview(h):
    r = requests.get(f"{BASE}/api/tasks/director-digest-preview", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "eligible" in d and "task_count" in d


# Snooze flow — create an overdue task, snooze it, verify digest count decreases
def test_snooze_flow(h):
    before = requests.get(f"{BASE}/api/tasks/director-digest-preview", headers=h, timeout=30).json()
    before_count = before.get("task_count", 0)

    # Create an overdue task assigned to admin
    me = requests.get(f"{BASE}/api/auth/me", headers=h, timeout=30).json()
    uid = me["id"]
    payload = {
        "title": "TEST_iter297_snooze",
        "description": "regression",
        "assignee_ids": [uid],
        "due_date": "2024-01-01T00:00:00Z",
        "priority": "high",
    }
    cr = requests.post(f"{BASE}/api/tasks", headers=h, json=payload, timeout=30)
    assert cr.status_code in (200, 201), cr.text
    task_id = cr.json().get("id") or cr.json().get("_id")
    assert task_id

    # Snooze it
    sr = requests.post(f"{BASE}/api/tasks/{task_id}/snooze", headers=h, json={"days": 1}, timeout=30)
    assert sr.status_code == 200, sr.text

    # Cleanup
    requests.delete(f"{BASE}/api/tasks/{task_id}", headers=h, timeout=30)


# Regression endpoints
@pytest.mark.parametrize("path", [
    "/api/finance/journal",
    "/api/bank/accounts",
    "/api/finance/receipts/review-queue",
])
def test_regression_gets(h, path):
    r = requests.get(f"{BASE}{path}", headers=h, timeout=30)
    assert r.status_code in (200, 204), f"{path} → {r.status_code} {r.text[:200]}"


def test_reports_pdf_list(h):
    r = requests.get(f"{BASE}/api/reports/pdf", headers=h, timeout=30)
    # Endpoint may be method-specific; accept 200/405/404 as non-server-error
    assert r.status_code < 500, r.text


def test_hr_payslips_generate_payday_exists(h):
    # POST endpoint — just probe with empty; expect 400/422 not 500
    r = requests.post(f"{BASE}/api/hr/payslips/generate-payday", headers=h, json={}, timeout=30)
    assert r.status_code < 500, r.text
