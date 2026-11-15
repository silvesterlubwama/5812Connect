# iter418: restaurant service — tickets, tabs and dishes through the kitchen.
import asyncio
import sys
import uuid

import pytest
from fastapi import HTTPException

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import kitchen  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP = f"loc_k_{uuid.uuid4().hex[:6]}"
OTHER = f"loc_k2_{uuid.uuid4().hex[:6]}"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _waiter(loc=SHOP):
    return {"id": "test-waiter", "role": "Staff", "name": "Grace",
            "organization_id": GLOBAL_ORG, "location_id": loc}


@pytest.fixture(autouse=True)
def clean():
    set_current_org(GLOBAL_ORG)
    yield
    with org_bypass():
        _run(raw_db.kitchen_orders.delete_many({"location_id": {"$in": [SHOP, OTHER]}}))


def _order(items=None, table="4", order_type="dine_in", location=SHOP, sale_id=None):
    set_current_org(GLOBAL_ORG)
    body = kitchen.OrderCreate(
        items=items or [
            {"name": "Chicken & chips", "qty": 2, "price": 18000, "notes": "no onions", "station": "Grill"},
            {"name": "Soda", "qty": 2, "price": 2000},
        ],
        location_id=location, table_label=table, order_type=order_type, sale_id=sale_id)
    return _run(kitchen.create_order(body, _waiter()))


def test_a_ticket_reaches_the_kitchen_with_the_table_and_the_requests():
    res = _order()
    order = res["order"]
    assert order["table_label"] == "4"
    assert order["status"] == "new"
    assert order["paid"] is False               # a tab, not yet settled
    assert order["items"][0]["notes"] == "no onions"
    assert order["items"][0]["station"] == "Grill"
    assert order["ticket_number"].startswith("K")
    assert "table 4" in res["message"]


def test_an_empty_ticket_is_refused():
    set_current_org(GLOBAL_ORG)
    with pytest.raises(HTTPException) as e:
        _run(kitchen.create_order(kitchen.OrderCreate(items=[], location_id=SHOP), _waiter()))
    assert e.value.status_code == 400


def test_paying_first_marks_the_ticket_paid_straight_away():
    res = _order(sale_id="sale_abc")
    assert res["order"]["paid"] is True
    assert res["order"]["sale_id"] == "sale_abc"


def test_a_dish_moves_on_its_own_and_the_ticket_waits_for_the_slowest():
    order = _order()["order"]
    chips, soda = order["items"][0]["line_id"], order["items"][1]["line_id"]
    r = _run(kitchen.set_item_status(order["id"], soda, {"status": "ready"}, _waiter()))
    assert r["status"] == "ready"
    assert r["order_status"] == "new"           # the chicken has not started
    _run(kitchen.set_item_status(order["id"], chips, {"status": "cooking"}, _waiter()))
    after = _run(kitchen.list_orders(SHOP, "open", 50, _waiter()))
    assert after[0]["status"] == "cooking"


def test_tapping_a_dish_without_saying_a_stage_just_moves_it_along():
    order = _order()["order"]
    line = order["items"][0]["line_id"]
    first = _run(kitchen.set_item_status(order["id"], line, {}, _waiter()))
    assert first["status"] == "cooking"
    second = _run(kitchen.set_item_status(order["id"], line, {}, _waiter()))
    assert second["status"] == "ready"


def test_the_whole_ticket_can_be_called_away_at_once():
    order = _order()["order"]
    r = _run(kitchen.set_order_status(order["id"], {"status": "ready"}, _waiter()))
    assert r["status"] == "ready"
    rows = _run(kitchen.list_orders(SHOP, "open", 50, _waiter()))
    assert all(i["status"] == "ready" for i in rows[0]["items"])


def test_a_served_ticket_drops_off_the_kitchen_screen():
    order = _order()["order"]
    _run(kitchen.set_order_status(order["id"], {"status": "served"}, _waiter()))
    assert _run(kitchen.list_orders(SHOP, "open", 50, _waiter())) == []


def test_an_unknown_stage_is_refused():
    order = _order()["order"]
    with pytest.raises(HTTPException) as e:
        _run(kitchen.set_order_status(order["id"], {"status": "burnt"}, _waiter()))
    assert e.value.status_code == 400


def test_a_second_round_goes_on_the_same_tab():
    order = _order()["order"]
    _run(kitchen.set_order_status(order["id"], {"status": "served"}, _waiter()))
    r = _run(kitchen.add_items(order["id"], {"items": [{"name": "Ice cream", "qty": 1, "price": 5000}]},
                               _waiter()))
    assert len(r["order"]["items"]) == 3
    assert r["order"]["status"] == "new"        # the kitchen has work again
    assert r["added"][0]["name"] == "Ice cream"


def test_nothing_can_be_added_to_a_tab_that_was_paid():
    order = _order(sale_id="sale_abc")["order"]
    with pytest.raises(HTTPException) as e:
        _run(kitchen.add_items(order["id"], {"items": [{"name": "Tea", "qty": 1, "price": 1000}]}, _waiter()))
    assert e.value.status_code == 400


def test_settling_a_tab_ties_it_to_the_sale_that_paid():
    order = _order()["order"]
    _run(kitchen.settle_order(order["id"], {"sale_id": "sale_xyz"}, _waiter()))
    tabs = _run(kitchen.list_orders(SHOP, "tabs", 50, _waiter()))
    assert tabs == []                           # no longer an open tab
    with org_bypass():
        fresh = _run(raw_db.kitchen_orders.find_one({"id": order["id"]}, {"_id": 0}))
    assert fresh["paid"] is True and fresh["sale_id"] == "sale_xyz"


def test_settling_needs_a_sale():
    order = _order()["order"]
    with pytest.raises(HTTPException) as e:
        _run(kitchen.settle_order(order["id"], {}, _waiter()))
    assert e.value.status_code == 400


def test_an_open_tab_shows_what_the_table_owes():
    _order()
    tabs = _run(kitchen.list_orders(SHOP, "tabs", 50, _waiter()))
    assert len(tabs) == 1
    assert tabs[0]["total"] == 40000            # 2x18,000 + 2x2,000


def test_a_tab_can_be_cancelled_but_a_paid_one_cannot():
    tab = _order()["order"]
    _run(kitchen.cancel_order(tab["id"], _waiter()))
    assert _run(kitchen.list_orders(SHOP, "tabs", 50, _waiter())) == []
    paid = _order(sale_id="sale_abc")["order"]
    with pytest.raises(HTTPException) as e:
        _run(kitchen.cancel_order(paid["id"], _waiter()))
    assert e.value.status_code == 400


def test_one_restaurants_tickets_do_not_show_at_another():
    _order()
    assert _run(kitchen.list_orders(OTHER, "open", 50, _waiter())) == []
    assert len(_run(kitchen.list_orders(SHOP, "open", 50, _waiter()))) == 1


def test_a_takeaway_ticket_says_so():
    res = _order(table=None, order_type="takeaway")
    assert res["order"]["order_type"] == "takeaway"
    assert res["order"]["table_label"] is None
    assert "takeaway" in res["message"]
