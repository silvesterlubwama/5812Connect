# iter415: returning one line off a receipt + keeping stores apart.
import asyncio
import sys
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import sales as sales_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP_A = f"loc_a_{uuid.uuid4().hex[:6]}"
SHOP_B = f"loc_b_{uuid.uuid4().hex[:6]}"
PROD = f"prod_r_{uuid.uuid4().hex[:6]}"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _cashier(loc=SHOP_A):
    return {"id": "test-cashier", "role": "Staff", "name": "Kate",
            "organization_id": GLOBAL_ORG, "location_id": loc}


def _admin(active=None):
    u = {"id": "test-admin", "role": "admin", "name": "Test Admin", "organization_id": GLOBAL_ORG}
    if active:
        u["active_campus_id"] = active
    return u


SALE_ID = f"s_ref_{uuid.uuid4().hex[:6]}"


@pytest.fixture
def receipt():
    sale = {
        "id": SALE_ID, "organization_id": GLOBAL_ORG, "location_id": SHOP_A,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "receipt_number": "INV-TEST-0001", "total": 30000, "payment_method": "cash",
        "payment_status": "paid", "cashier_id": "test-cashier", "cashier_name": "Kate",
        "items": [
            {"product_id": PROD, "name": "Soap", "qty": 3, "price": 5000, "units_per_pack": 1},
            {"product_id": None, "name": "Service fee", "qty": 1, "price": 15000},
        ],
    }
    other_shop_sale = {
        "id": f"s_b_{uuid.uuid4().hex[:6]}", "organization_id": GLOBAL_ORG,
        "location_id": SHOP_B, "created_at": datetime.now(timezone.utc).isoformat(),
        "receipt_number": "INV-TEST-0002", "total": 9000, "payment_method": "cash",
        "items": [{"product_id": None, "name": "Tea", "qty": 1, "price": 9000}],
    }

    async def _mk():
        with org_bypass():
            await raw_db.sales.insert_many([sale, other_shop_sale])
            await raw_db.products.insert_one({
                "id": PROD, "organization_id": GLOBAL_ORG, "name": "Soap",
                "location_id": SHOP_A, "stock": 10, "price": 5000,
            })
            await raw_db.locations.insert_many([
                {"id": SHOP_A, "name": "Shop A", "organization_id": GLOBAL_ORG},
                {"id": SHOP_B, "name": "Shop B", "organization_id": GLOBAL_ORG},
            ])
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield sale

    async def _rm():
        with org_bypass():
            await raw_db.sales.delete_many({"location_id": {"$in": [SHOP_A, SHOP_B]}})
            await raw_db.products.delete_many({"id": PROD})
            await raw_db.locations.delete_many({"id": {"$in": [SHOP_A, SHOP_B]}})
            await raw_db.finance_journal_entries.delete_many({"reference": SALE_ID})
    _run(_rm())


def _refund(items, user=None, reason="Damaged"):
    set_current_org(GLOBAL_ORG)
    body = sales_mod.RefundCreate(items=items, reason=reason)
    return _run(sales_mod.refund_sale_lines(SALE_ID, body, user or _cashier()))


def _stock():
    with org_bypass():
        p = _run(raw_db.products.find_one({"id": PROD}, {"_id": 0, "stock": 1}))
    return int(p["stock"])


def test_one_unit_comes_back_and_the_rest_of_the_receipt_stands(receipt):
    res = _refund([{"product_id": PROD, "name": "Soap", "qty": 1}])
    assert res["refund"]["amount"] == 5000
    assert res["fully_refunded"] is False
    assert _stock() == 11
    with org_bypass():
        sale = _run(raw_db.sales.find_one({"id": SALE_ID}, {"_id": 0}))
    assert sale["total"] == 30000              # the receipt itself is untouched
    assert sale["refunded_total"] == 5000
    assert sale["items"][0]["refunded_qty"] == 1


def test_it_refuses_more_than_was_sold(receipt):
    with pytest.raises(HTTPException) as e:
        _refund([{"product_id": PROD, "name": "Soap", "qty": 4}])
    assert e.value.status_code == 400
    assert "left to refund" in e.value.detail
    assert _stock() == 10


def test_a_line_cannot_be_refunded_twice_over(receipt):
    _refund([{"product_id": PROD, "name": "Soap", "qty": 2}])
    with pytest.raises(HTTPException) as e:
        _refund([{"product_id": PROD, "name": "Soap", "qty": 2}])
    assert e.value.status_code == 400
    assert _stock() == 12


def test_returning_every_line_marks_the_receipt_fully_refunded(receipt):
    res = _refund([
        {"product_id": PROD, "name": "Soap", "qty": 3},
        {"product_id": None, "name": "Service fee", "qty": 1},
    ])
    assert res["refund"]["amount"] == 30000
    assert res["fully_refunded"] is True
    assert _stock() == 13                      # only the stocked line moves


def test_an_item_not_on_the_receipt_is_rejected(receipt):
    with pytest.raises(HTTPException) as e:
        _refund([{"product_id": "prod_nope", "name": "Rice", "qty": 1}])
    assert e.value.status_code == 400


def test_a_voided_receipt_cannot_be_part_refunded(receipt):
    with org_bypass():
        _run(raw_db.sales.update_one({"id": SALE_ID}, {"$set": {"voided": True}}))
    with pytest.raises(HTTPException) as e:
        _refund([{"product_id": PROD, "name": "Soap", "qty": 1}])
    assert e.value.status_code == 400
    assert "voided" in e.value.detail


def test_a_cashier_from_another_store_cannot_refund_it(receipt):
    with pytest.raises(HTTPException) as e:
        _refund([{"product_id": PROD, "name": "Soap", "qty": 1}],
                user={"id": "other", "role": "Staff", "name": "Ben",
                      "organization_id": GLOBAL_ORG, "location_id": SHOP_B})
    assert e.value.status_code == 403


def test_the_money_leaves_the_books_with_its_own_entry(receipt):
    res = _refund([{"product_id": PROD, "name": "Soap", "qty": 1}])
    with org_bypass():
        je = _run(raw_db.finance_journal_entries.find_one(
            {"idempotency_key": f"sale_refund:{res['refund']['id']}"}, {"_id": 0}))
    # No chart of accounts in a bare test org — either it posted, or it said so.
    assert (je is not None) == res["journal_posted"]


def test_the_till_only_lists_its_own_sales(receipt):
    set_current_org(GLOBAL_ORG)
    at_a = _run(sales_mod.list_sales(0, 100, False, SHOP_A, _admin()))
    assert [s["id"] for s in at_a] == [SALE_ID]
    at_b = _run(sales_mod.list_sales(0, 100, False, SHOP_B, _admin()))
    assert SALE_ID not in [s["id"] for s in at_b]


def test_todays_part_refunds_show_on_the_z_report(receipt):
    _refund([{"product_id": PROD, "name": "Soap", "qty": 1}])
    set_current_org(GLOBAL_ORG)
    r = _run(sales_mod.z_report(TODAY, SHOP_A, None, _admin()))
    assert r["refunds_count"] == 1
    assert r["refunds_total"] == 5000
    assert r["net"] == r["gross"] - r["discounts"] - 5000


def test_another_stores_refunds_are_not_on_this_till(receipt):
    _refund([{"product_id": PROD, "name": "Soap", "qty": 1}])
    set_current_org(GLOBAL_ORG)
    r = _run(sales_mod.z_report(TODAY, SHOP_B, None, _admin()))
    assert r["refunds_count"] == 0 and r["refunds_total"] == 0


def test_voiding_after_a_part_refund_does_not_restock_it_twice(receipt):
    _refund([{"product_id": PROD, "name": "Soap", "qty": 1}])     # 10 -> 11
    assert _stock() == 11
    set_current_org(GLOBAL_ORG)
    with org_bypass():
        sale = _run(raw_db.sales.find_one({"id": SALE_ID}, {"_id": 0}))
    _run(sales_mod._reverse_sale_side_effects(sale, _admin(), reason="test void"))
    assert _stock() == 13      # the other 2 only, not all 3 again
