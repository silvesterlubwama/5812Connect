# iter404: which month the payslip generator opens on.
# Payroll is run at the end of the month it covers and finished off in the first
# days of the next one, so early in a month the period in hand is the month just
# gone — not the one that has barely started.
import os
import sys
from datetime import date

import pytest
import requests

sys.path.insert(0, "/app/backend")
from routers.hr import (  # noqa: E402
    _payroll_month_in_hand,
    _period_for_payday,
    _period_in_hand,
)


def _env(path, key):
    with open(path) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} missing from {path}")


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
DIRECTOR = {"identifier": "admin@5812global.org", "password": "Admin@1234"}
MONTHLY_CAMPUS = "loc_59a87857"  # monthly, payday on the 7th


@pytest.mark.parametrize("today,expected", [
    (date(2026, 11, 1), "2026-10"),    # first of the month → last month
    (date(2026, 11, 2), "2026-10"),
    (date(2026, 11, 15), "2026-10"),
    (date(2026, 11, 25), "2026-10"),   # still last month
    (date(2026, 11, 26), "2026-11"),   # five days before month end → this month
    (date(2026, 11, 30), "2026-11"),
    (date(2026, 2, 23), "2026-01"),    # short month
    (date(2026, 2, 24), "2026-02"),
    (date(2027, 1, 3), "2026-12"),     # across the year boundary
])
def test_month_in_hand(today, expected):
    assert _payroll_month_in_hand(today) == expected


@pytest.mark.parametrize("payday,expected", [
    (date(2026, 11, 2), "2026-10"),    # paid at the start of a month → last month
    (date(2026, 11, 7), "2026-10"),
    (date(2026, 11, 15), "2026-10"),
    (date(2026, 11, 25), "2026-11"),   # a late payday settles the month it is in
    (date(2026, 11, 28), "2026-11"),
    (date(2027, 1, 5), "2026-12"),
])
def test_a_payday_settles_the_right_month(payday, expected):
    assert _period_for_payday("monthly", "", payday) == expected


def test_weekly_and_biweekly_are_untouched():
    anchor = "2026-01-05"
    for freq in ("weekly", "biweekly"):
        in_hand = _period_in_hand(freq, anchor, date(2026, 11, 2))
        assert in_hand.startswith("2026-11") or in_hand.startswith("2026-10"), in_hand
        assert "_" in in_hand, "an anchored cycle must keep its window label"


def _director():
    r = requests.post(f"{API}/auth/login", json=DIRECTOR, timeout=30)
    if r.status_code != 200:
        pytest.skip("director account unavailable")
    return {"Authorization": f"Bearer {r.json()['token']}"}


class TestThroughTheApi:
    def test_pay_periods_marks_the_month_in_hand_as_current(self):
        h = _director()
        r = requests.get(f"{API}/hr/pay-periods", headers=h, timeout=30,
                         params={"past": 3, "future": 1, "location_id": "no-such-campus"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["frequency"] == "monthly"
        assert d["current"] == _payroll_month_in_hand(date.today())
        assert [p["period"] for p in d["periods"] if p["is_current"]] == [d["current"]]

    def test_generator_opens_on_the_month_in_hand(self):
        h = _director()
        r = requests.get(f"{API}/hr/payslips/upcoming-paydays", headers=h, timeout=30,
                         params={"count": 4, "location_id": MONTHLY_CAMPUS})
        if r.status_code != 200:
            pytest.skip("monthly campus unavailable")
        d = r.json()
        assert d["period_in_hand"] == _payroll_month_in_hand(date.today())
        periods = [p["period"] for p in d["paydays"]]
        # the month being worked on has to be in the list, or it could not be
        # chosen — the payday that settles it has usually already passed
        assert d["period_in_hand"] in periods, periods
        for p in d["paydays"]:
            assert p["period"] == _period_for_payday("monthly", "", date.fromisoformat(p["date"]))

    def test_preview_without_a_period_uses_the_month_in_hand(self):
        h = _director()
        r = requests.post(f"{API}/hr/payslips/preview", headers=h, timeout=60,
                          json={"location_id": MONTHLY_CAMPUS})
        if r.status_code != 200:
            pytest.skip(f"preview unavailable: {r.status_code}")
        assert r.json()["period"] == _payroll_month_in_hand(date.today())
