# iter414: end-of-day takings for one till.
import asyncio
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import sales as sales_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
LOC = f"loc_z_{uuid.uuid4().hex[:6]}"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "test-admin", "role": "admin", "name": "Test Admin",
            "organization_id": GLOBAL_ORG, "active_campus_id": LOC}


def _sale(total, method, *, voided=False, qty=2, cashier="Kate", discount=0):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": f"s_{uuid.uuid4().hex[:8]}", "organization_id": GLOBAL_ORG,
        "location_id": LOC, "created_at": now, "total": total, "discount": discount,
        "payment_method": method, "voided": voided, "cashier_name": cashier,
        "receipt_number": f"R-{uuid.uuid4().hex[:4].upper()}",
        "items": [{"product_name": "Soap", "qty": qty, "price": total / max(qty, 1)}],
    }


@pytest.fixture
def till():
    rows = [
        _sale(10000, "cash"), _sale(5000, "cash"),
        _sale(20000, "mobile_money", qty=1),
        _sale(7000, "cash", voided=True),
        _sale(3000, "card", cashier="Chris", discount=500),
    ]

    async def _mk():
        with org_bypass():
            await raw_db.sales.insert_many(rows)
            await raw_db.locations.insert_one({"id": LOC, "name": "Z Test Till", "organization_id": GLOBAL_ORG})
            await raw_db.shifts.insert_one({
                "id": f"shift_{uuid.uuid4().hex[:6]}", "organization_id": GLOBAL_ORG,
                "location_id": LOC, "status": "closed", "cashier_id": "test-admin",
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "opening_cash": 50000, "cash_drops_total": 10000,
                "expected_cash": 55000, "closing_cash": 53000, "variance": -2000,
            })
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield rows

    async def _rm():
        with org_bypass():
            await raw_db.sales.delete_many({"location_id": LOC})
            await raw_db.locations.delete_many({"id": LOC})
            await raw_db.shifts.delete_many({"location_id": LOC})
    _run(_rm())


def _report():
    set_current_org(GLOBAL_ORG)
    return _run(sales_mod.z_report(TODAY, LOC, None, _admin()))


def test_it_counts_only_the_sales_that_stood(till):
    r = _report()
    assert r["sales_count"] == 4
    assert r["gross"] == 38000, r["gross"]
    assert r["voided_count"] == 1
    assert r["voided_total"] == 7000


def test_it_splits_the_takings_by_payment_method(till):
    r = _report()
    by = {m["method"]: m for m in r["by_method"]}
    assert by["cash"]["count"] == 2 and by["cash"]["total"] == 15000
    assert by["mobile_money"]["total"] == 20000
    assert by["card"]["total"] == 3000


def test_it_splits_by_cashier_and_counts_the_items(till):
    r = _report()
    by = {c["cashier"]: c for c in r["by_cashier"]}
    assert by["Kate"]["count"] == 3
    assert by["Chris"]["total"] == 3000
    assert r["items_sold"] == 2 + 2 + 1 + 2       # the voided one is left out


def test_net_takes_the_discounts_off(till):
    r = _report()
    assert r["discounts"] == 500
    assert r["net"] == 37500


def test_it_shows_the_drawer_against_what_was_counted(till):
    r = _report()
    assert r["drawer"]["expected_cash"] == 55000
    assert r["drawer"]["counted_cash"] == 53000
    assert r["drawer"]["variance"] == -2000


def test_it_names_the_till_and_the_first_and_last_receipt(till):
    r = _report()
    assert r["store_name"] == "Z Test Till"
    assert r["first_receipt"] and r["last_receipt"]


def test_another_till_is_not_counted(till):
    set_current_org(GLOBAL_ORG)
    other = _run(sales_mod.z_report(TODAY, f"loc_other_{uuid.uuid4().hex[:4]}", None, _admin()))
    assert other["sales_count"] == 0
    assert other["gross"] == 0


def test_a_quiet_day_reports_zeroes_not_an_error(till):
    set_current_org(GLOBAL_ORG)
    r = _run(sales_mod.z_report("2001-01-01", LOC, None, _admin()))
    assert r["sales_count"] == 0 and r["gross"] == 0 and r["average_sale"] == 0
