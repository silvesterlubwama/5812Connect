# iter416: quotes, returns report, store transfers, exchanges.
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
from routers import stock_transfers as trf_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP_A = f"loc_a_{uuid.uuid4().hex[:6]}"
SHOP_B = f"loc_b_{uuid.uuid4().hex[:6]}"
PROD = f"prod_t_{uuid.uuid4().hex[:6]}"
SWAP = f"prod_s_{uuid.uuid4().hex[:6]}"
VAR = f"prod_v_{uuid.uuid4().hex[:6]}"
SALE_ID = f"s_x_{uuid.uuid4().hex[:6]}"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "test-admin", "role": "admin", "name": "Test Admin",
            "organization_id": GLOBAL_ORG, "location_id": SHOP_A}


@pytest.fixture
def shop():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_many([
                {"id": SHOP_A, "name": "Shop A", "organization_id": GLOBAL_ORG},
                {"id": SHOP_B, "name": "Shop B", "organization_id": GLOBAL_ORG},
            ])
            await raw_db.products.insert_many([
                {"id": PROD, "organization_id": GLOBAL_ORG, "name": "Soap", "unit": "bar",
                 "location_id": SHOP_A, "stock": 10, "price": 5000},
                {"id": SWAP, "organization_id": GLOBAL_ORG, "name": "Shampoo",
                 "location_id": SHOP_A, "stock": 10, "price": 8000},
                {"id": VAR, "organization_id": GLOBAL_ORG, "name": "Shirt", "has_variants": True,
                 "location_id": SHOP_A, "stock": 4, "price": 20000,
                 "variants": [{"id": "v1", "name": "S", "stock": 4}]},
            ])
            await raw_db.sales.insert_one({
                "id": SALE_ID, "organization_id": GLOBAL_ORG, "location_id": SHOP_A,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "receipt_number": "INV-TEST-X1", "total": 15000, "payment_method": "cash",
                "payment_status": "paid", "cashier_id": "test-admin",
                "items": [{"product_id": PROD, "name": "Soap", "qty": 3, "price": 5000, "units_per_pack": 1}],
            })
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.products.delete_many({"id": {"$in": [PROD, SWAP, VAR]}})
            await raw_db.locations.delete_many({"id": {"$in": [SHOP_A, SHOP_B]}})
            await raw_db.sales.delete_many({"location_id": {"$in": [SHOP_A, SHOP_B]}})
            await raw_db.stock_transfers.delete_many({"product_id": {"$in": [PROD, SWAP, VAR]}})
            await raw_db.finance_journal_entries.delete_many({"reference": SALE_ID})
    _run(_rm())


def _transfer(qty, product=PROD, src=SHOP_A, dst=SHOP_B):
    set_current_org(GLOBAL_ORG)
    body = trf_mod.TransferCreate(product_id=product, from_location_id=src,
                                  to_location_id=dst, qty=qty, note="Tuesday run")
    return _run(trf_mod.create_stock_transfer(body, _admin()))


def _product():
    with org_bypass():
        return _run(raw_db.products.find_one({"id": PROD}, {"_id": 0}))


# ---------------------------------------------------------------- transfers
def test_sending_stock_moves_both_counts(shop):
    res = _transfer(4)
    assert res["from_stock"] == 6 and res["to_stock"] == 4
    p = _product()
    assert p["store_stock"][SHOP_A] == 6 and p["store_stock"][SHOP_B] == 4
    assert SHOP_B in p["store_ids"]            # the receiving shop can now sell it


def test_the_whole_chain_count_does_not_change(shop):
    before = _product()
    _transfer(4)
    after = _product()
    assert sum(after["store_stock"].values()) == int(before["stock"])


def test_it_refuses_more_than_the_shop_holds(shop):
    with pytest.raises(HTTPException) as e:
        _transfer(99)
    assert e.value.status_code == 400 and "only has 10" in e.value.detail
    assert _product().get("store_stock") in (None, {})


def test_it_refuses_sending_to_the_same_shop(shop):
    with pytest.raises(HTTPException) as e:
        _transfer(1, dst=SHOP_A)
    assert e.value.status_code == 400


def test_a_variant_product_cannot_be_transferred_yet(shop):
    with pytest.raises(HTTPException) as e:
        _transfer(1, product=VAR)
    assert e.value.status_code == 400 and "variants" in e.value.detail


def test_a_second_hop_sends_it_on(shop):
    _transfer(4)
    res = _transfer(2, src=SHOP_B, dst=SHOP_A)
    assert res["from_stock"] == 2 and res["to_stock"] == 8


def test_the_move_is_written_down(shop):
    _transfer(4)
    rows = _run(trf_mod.list_stock_transfers(SHOP_B, 10, _admin()))
    assert len(rows) == 1
    assert rows[0]["qty"] == 4 and rows[0]["to_location_name"] == "Shop B"
    assert rows[0]["note"] == "Tuesday run"


# ---------------------------------------------------------------- returns report
def test_the_returns_report_groups_by_product_and_reason(shop):
    set_current_org(GLOBAL_ORG)
    _run(sales_mod.refund_sale_lines(SALE_ID, sales_mod.RefundCreate(
        items=[{"product_id": PROD, "name": "Soap", "qty": 1}], reason="Damaged"), _admin()))
    _run(sales_mod.refund_sale_lines(SALE_ID, sales_mod.RefundCreate(
        items=[{"product_id": PROD, "name": "Soap", "qty": 1}], reason="Damaged"), _admin()))
    rep = _run(sales_mod.refund_report(TODAY, TODAY, SHOP_A, _admin()))
    assert rep["refunds_count"] == 2
    assert rep["refunds_total"] == 10000
    assert rep["by_reason"][0]["reason"] == "Damaged" and rep["by_reason"][0]["count"] == 2
    assert rep["worst"]["name"] == "Soap" and rep["worst"]["qty"] == 2
    assert rep["by_product"][0]["reasons"]["Damaged"] == 2


def test_a_return_with_no_reason_is_still_counted(shop):
    set_current_org(GLOBAL_ORG)
    _run(sales_mod.refund_sale_lines(SALE_ID, sales_mod.RefundCreate(
        items=[{"product_id": PROD, "name": "Soap", "qty": 1}], reason=""), _admin()))
    rep = _run(sales_mod.refund_report(TODAY, TODAY, SHOP_A, _admin()))
    assert rep["by_reason"][0]["reason"] == "No reason given"


def test_another_shops_returns_are_not_in_this_report(shop):
    set_current_org(GLOBAL_ORG)
    _run(sales_mod.refund_sale_lines(SALE_ID, sales_mod.RefundCreate(
        items=[{"product_id": PROD, "name": "Soap", "qty": 1}], reason="Damaged"), _admin()))
    rep = _run(sales_mod.refund_report(TODAY, TODAY, SHOP_B, _admin()))
    assert rep["refunds_count"] == 0 and rep["worst"] is None


# ---------------------------------------------------------------- exchange
def test_an_exchange_swaps_the_item_and_charges_the_difference(shop):
    set_current_org(GLOBAL_ORG)
    res = _run(sales_mod.exchange_sale_lines(SALE_ID, sales_mod.ExchangeCreate(
        returns=[{"product_id": PROD, "name": "Soap", "qty": 1}],
        items=[{"product_id": SWAP, "name": "Shampoo", "qty": 1, "price": 8000, "line_total": 8000}],
        total=8000, reason="Wrong item"), _admin()))
    assert res["credit"] == 5000
    assert res["difference"] == 3000
    assert "customer pays 3,000" in res["message"]
    with org_bypass():
        soap = _run(raw_db.products.find_one({"id": PROD}, {"_id": 0, "stock": 1}))
        swap = _run(raw_db.products.find_one({"id": SWAP}, {"_id": 0, "stock": 1}))
    assert soap["stock"] == 11          # the returned bar is back
    assert swap["stock"] == 9           # the replacement left the shelf
    assert res["sale"]["exchange_of"] == SALE_ID


def test_an_exchange_for_something_cheaper_gives_money_back(shop):
    set_current_org(GLOBAL_ORG)
    res = _run(sales_mod.exchange_sale_lines(SALE_ID, sales_mod.ExchangeCreate(
        returns=[{"product_id": PROD, "name": "Soap", "qty": 2}],
        items=[{"product_id": SWAP, "name": "Shampoo", "qty": 1, "price": 8000, "line_total": 8000}],
        total=8000), _admin()))
    assert res["difference"] == -2000
    assert "give back 2,000" in res["message"]


def test_an_exchange_needs_something_in_the_basket(shop):
    set_current_org(GLOBAL_ORG)
    with pytest.raises(HTTPException) as e:
        _run(sales_mod.exchange_sale_lines(SALE_ID, sales_mod.ExchangeCreate(
            returns=[{"product_id": PROD, "name": "Soap", "qty": 1}], items=[])), )
    assert e.value.status_code == 400


def test_an_exchange_shows_on_the_z_report_as_sale_and_refund(shop):
    set_current_org(GLOBAL_ORG)
    _run(sales_mod.exchange_sale_lines(SALE_ID, sales_mod.ExchangeCreate(
        returns=[{"product_id": PROD, "name": "Soap", "qty": 1}],
        items=[{"product_id": SWAP, "name": "Shampoo", "qty": 1, "price": 8000, "line_total": 8000}],
        total=8000), _admin()))
    r = _run(sales_mod.z_report(TODAY, SHOP_A, None, _admin()))
    assert r["refunds_total"] == 5000
    # gross carries both the original receipt and the replacement sale
    assert r["gross"] == 23000
    assert r["net"] == 18000
