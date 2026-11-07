# iter412: deleting a sale must put everything back — stock (including packs and
# variants), the customer's running totals, the money in the books, and any
# booking or ticket the sale issued.
import asyncio
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db, db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import sales as sales_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "test-admin", "role": "admin", "name": "Test Admin", "organization_id": GLOBAL_ORG}


@pytest.fixture
def shop():
    """A product with a variant, plus a customer account."""
    pid, vid, cid = f"p_{uuid.uuid4().hex[:8]}", f"v_{uuid.uuid4().hex[:8]}", f"c_{uuid.uuid4().hex[:8]}"

    async def _mk():
        with org_bypass():
            await raw_db.products.insert_one({
                "id": pid, "name": "Test Soap", "price": 5000, "stock": 100,
                "organization_id": GLOBAL_ORG, "is_universal": False, "store_ids": [],
                "variants": [{"id": vid, "name": "Large", "stock": 40, "price": 5000}],
            })
            await raw_db.customer_accounts.insert_one({
                "id": cid, "name": "Test Buyer", "organization_id": GLOBAL_ORG,
                "total_purchases": 7, "total_spent": 70000, "receipt_history": [],
            })
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield {"product_id": pid, "variant_id": vid, "customer_id": cid}

    async def _rm():
        with org_bypass():
            await raw_db.products.delete_many({"id": pid})
            await raw_db.customer_accounts.delete_many({"id": cid})
            await raw_db.sales.delete_many({"customer_id": cid})
    _run(_rm())


def _product(pid):
    with org_bypass():
        return _run(raw_db.products.find_one({"id": pid}, {"_id": 0, "stock": 1, "variants": 1}))


def _make_sale(shop, qty=2, units_per_pack=6, paid=True):
    payload = sales_mod.SaleCreate(
        items=[{
            "product_id": shop["product_id"], "variant_id": shop["variant_id"],
            "product_name": "Test Soap", "qty": qty, "price": 5000,
            "units_per_pack": units_per_pack, "line_total": 5000 * qty,
        }],
        total=5000 * qty, payment_method="cash", customer_id=shop["customer_id"],
        customer_name="Test Buyer",
    )
    if paid:
        payload.payment_status = "paid"
    return _run(sales_mod.create_sale(payload, _admin()))


def test_a_sale_takes_the_stock_then_deleting_it_gives_it_all_back(shop):
    before = _product(shop["product_id"])
    sale = _make_sale(shop, qty=2, units_per_pack=6)
    mid = _product(shop["product_id"])
    assert mid["stock"] == before["stock"] - 12, "a 2 x 6-pack sale should take 12 units"
    assert mid["variants"][0]["stock"] == before["variants"][0]["stock"] - 2

    _run(sales_mod.delete_sale(sale["id"], _admin()))
    after = _product(shop["product_id"])
    assert after["stock"] == before["stock"], f"stock not restored: {after['stock']} vs {before['stock']}"
    assert after["variants"][0]["stock"] == before["variants"][0]["stock"], "the variant was never restored"


def test_the_sale_row_really_goes(shop):
    sale = _make_sale(shop)
    _run(sales_mod.delete_sale(sale["id"], _admin()))
    with org_bypass():
        assert _run(raw_db.sales.find_one({"id": sale["id"]})) is None


def test_the_takings_come_out_of_the_books(shop):
    sale = _make_sale(shop, paid=True)
    key = f"sale:{sale['id']}"
    with org_bypass():
        je = _run(raw_db.finance_journal_entries.find_one({"idempotency_key": key}, {"_id": 0, "id": 1}))
    if not je:
        pytest.skip("chart of accounts not set up in this environment")
    out = _run(sales_mod.delete_sale(sale["id"], _admin()))
    assert out["journal_reversed"] is True
    with org_bypass():
        left = _run(raw_db.finance_journal_entries.find_one(
            {"idempotency_key": key, "reversed": {"$ne": True}}, {"_id": 0, "id": 1}))
    assert left is None, "the sale is still sitting in the ledger"


def test_the_customers_running_total_is_put_back(shop):
    sale = _make_sale(shop, qty=2)
    _run(sales_mod.delete_sale(sale["id"], _admin()))
    with org_bypass():
        acct = _run(raw_db.customer_accounts.find_one({"id": shop["customer_id"]}, {"_id": 0}))
    assert acct["total_purchases"] == 7
    assert acct["total_spent"] == 70000


def test_deleting_an_already_voided_sale_does_not_double_restore(shop):
    before = _product(shop["product_id"])
    sale = _make_sale(shop, qty=1, units_per_pack=6)
    _run(sales_mod.undo_sale(sale["id"], _admin()))
    assert _product(shop["product_id"])["stock"] == before["stock"], "void should restore once"
    _run(sales_mod.delete_sale(sale["id"], _admin()))
    assert _product(shop["product_id"])["stock"] == before["stock"], "delete restored a second time"


def test_voiding_also_takes_the_money_back_out(shop):
    sale = _make_sale(shop, paid=True)
    key = f"sale:{sale['id']}"
    with org_bypass():
        je = _run(raw_db.finance_journal_entries.find_one({"idempotency_key": key}, {"_id": 0, "id": 1}))
    if not je:
        pytest.skip("chart of accounts not set up in this environment")
    _run(sales_mod.undo_sale(sale["id"], _admin()))
    with org_bypass():
        left = _run(raw_db.finance_journal_entries.find_one(
            {"idempotency_key": key, "reversed": {"$ne": True}}, {"_id": 0, "id": 1}))
    assert left is None, "a voided sale still shows in the ledger"
    _run(db.sales.delete_many({"id": sale["id"]}))
