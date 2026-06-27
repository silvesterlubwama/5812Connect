"""Iteration 179 — PBX call analytics endpoint.

Validates the aggregate shape returned by GET /api/pbx/cdr/analytics.
Seeds a controlled set of CDR rows so counts/sums are deterministic.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "admin@5812uganda.org"
ADMIN_PASS = "Admin@5812"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _cleanup(ids):
    try:
        from pymongo import MongoClient
        c = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "5812global")]
        db.pbx_cdr.delete_many({"id": {"$in": ids}})
    except Exception:
        pass


@pytest.fixture
def seeded(headers):
    """Seed a deterministic CDR set: 2 incoming, 3 outgoing, 1 missed.
    Same matched contact on 4 of them so 'top_contacts' surfaces it."""
    ts = int(time.time() * 1000)
    rows = [
        {"call_id": f"an-{ts}-1", "direction": "outgoing", "peer": "+15550001111",
         "duration_sec": 60, "status": "completed",
         "matched_kind": "member", "matched_id": "mAlpha", "matched_name": "Alpha"},
        {"call_id": f"an-{ts}-2", "direction": "outgoing", "peer": "+15550001111",
         "duration_sec": 120, "status": "completed",
         "matched_kind": "member", "matched_id": "mAlpha", "matched_name": "Alpha"},
        {"call_id": f"an-{ts}-3", "direction": "outgoing", "peer": "+15550002222",
         "duration_sec": 30, "status": "completed"},
        {"call_id": f"an-{ts}-4", "direction": "incoming", "peer": "+15550001111",
         "duration_sec": 90, "status": "completed",
         "matched_kind": "member", "matched_id": "mAlpha", "matched_name": "Alpha"},
        {"call_id": f"an-{ts}-5", "direction": "incoming", "peer": "+15550003333",
         "duration_sec": 15, "status": "completed",
         "matched_kind": "member", "matched_id": "mAlpha", "matched_name": "Alpha"},
        {"call_id": f"an-{ts}-6", "direction": "missed", "peer": "+15550009999",
         "duration_sec": 0, "status": "missed"},
    ]
    ids = [r["call_id"] for r in rows]
    for body in rows:
        requests.post(f"{BASE_URL}/api/pbx/cdr/log", headers=headers, json=body, timeout=10).raise_for_status()
    yield ids
    _cleanup(ids)


class TestAnalytics:
    def test_summary_totals(self, headers, seeded):
        r = requests.get(f"{BASE_URL}/api/pbx/cdr/analytics?days=1", headers=headers, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        s = d["summary"]
        # We seeded 6 rows; other test data may be present so >= the seed counts
        assert s["total"] >= 6
        assert s["incoming"] >= 2
        assert s["outgoing"] >= 3
        assert s["missed"] >= 1
        assert s["avg_duration_sec"] > 0
        assert 0 <= s["missed_ratio"] <= 1

    def test_daily_breakdown(self, headers, seeded):
        d = requests.get(f"{BASE_URL}/api/pbx/cdr/analytics?days=7",
                         headers=headers, timeout=10).json()
        assert isinstance(d["daily"], list)
        # All entries should have date + per-direction counts
        for row in d["daily"]:
            assert "date" in row
            assert {"total", "incoming", "outgoing", "missed"}.issubset(row.keys())

    def test_top_numbers_and_contacts(self, headers, seeded):
        d = requests.get(f"{BASE_URL}/api/pbx/cdr/analytics?days=1",
                         headers=headers, timeout=10).json()
        # +15550001111 was hit 3 times in our seed, should be near the top
        nums = d["top_numbers"]
        assert isinstance(nums, list) and len(nums) > 0
        target = next((n for n in nums if n["digits"].endswith("15550001111")), None)
        assert target is not None
        assert target["count"] >= 3
        # Alpha contact was hit 4 times
        contacts = d["top_contacts"]
        alpha = next((c for c in contacts if c.get("id") == "mAlpha"), None)
        assert alpha is not None
        assert alpha["count"] >= 4
        assert alpha["kind"] == "member"

    def test_busiest_hour_has_24_entries(self, headers, seeded):
        d = requests.get(f"{BASE_URL}/api/pbx/cdr/analytics?days=1",
                         headers=headers, timeout=10).json()
        hours = d["busiest_hour"]
        assert len(hours) == 24
        assert {h["hour"] for h in hours} == set(range(24))
        # Sum of hourly counts should equal summary.total
        assert sum(h["count"] for h in hours) == d["summary"]["total"]

    def test_top_staff_omitted_when_user_filter(self, headers, seeded):
        d = requests.get(f"{BASE_URL}/api/pbx/cdr/analytics?days=1&user_id=non-existent",
                         headers=headers, timeout=10).json()
        assert d["top_staff"] == []
        assert d["summary"]["total"] == 0

    def test_admin_only(self):
        r = requests.get(f"{BASE_URL}/api/pbx/cdr/analytics?days=1", timeout=10)
        assert r.status_code in (401, 403)
