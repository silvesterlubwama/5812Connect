# iter420: the deduction's own note, two hatchery runs side by side, waiters
# signed on at the till, and screens on the wall.
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import kitchen as kit  # noqa: E402
from routers import screens as scr  # noqa: E402
from routers import stock_lifecycle as life  # noqa: E402
from routers import store_settings as cfg  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP = f"loc_q_{uuid.uuid4().hex[:6]}"
OTHER = f"loc_r_{uuid.uuid4().hex[:6]}"
CHICKS = f"prod_q_{uuid.uuid4().hex[:6]}"
BROILERS = f"prod_r_{uuid.uuid4().hex[:6]}"
STAFF = f"user_q_{uuid.uuid4().hex[:6]}"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user(role="Manager", loc=SHOP, name="Kate", uid="test-waiterboss"):
    return {"id": uid, "role": role, "name": name,
            "organization_id": GLOBAL_ORG, "location_id": loc}


@pytest.fixture
def shop():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_many([
                {"id": SHOP, "name": "Zimba Kitchen", "organization_id": GLOBAL_ORG},
                {"id": OTHER, "name": "Jinja Shop", "organization_id": GLOBAL_ORG},
            ])
            await raw_db.products.insert_many([
                {"id": CHICKS, "organization_id": GLOBAL_ORG, "name": "Brooder Chicks",
                 "location_id": SHOP, "stock": 300, "price": 4000,
                 "grows_into_product_id": BROILERS, "grow_after_days": 28},
                {"id": BROILERS, "organization_id": GLOBAL_ORG, "name": "4 Week Broilers",
                 "location_id": SHOP, "stock": 0, "price": 15000},
            ])
            await raw_db.users.insert_one({"id": STAFF, "organization_id": GLOBAL_ORG,
                                           "name": "Moses", "role": "Staff", "location_id": SHOP})
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.products.delete_many({"id": {"$in": [CHICKS, BROILERS]}})
            await raw_db.locations.delete_many({"id": {"$in": [SHOP, OTHER]}})
            await raw_db.users.delete_many({"id": STAFF})
            await raw_db.stock_losses.delete_many({"location_id": SHOP})
            await raw_db.stock_batches.delete_many({"location_id": SHOP})
            await raw_db.stock_movements.delete_many({"location_id": SHOP})
            await raw_db.kitchen_orders.delete_many({"location_id": SHOP})
            await raw_db.device_screens.delete_many({"location_id": {"$in": [SHOP, OTHER]}})
            await raw_db.live_sales.delete_many({"key": {"$regex": f"^{SHOP}"}})
            await raw_db.store_settings.delete_many({"location_id": {"$in": [SHOP, OTHER]}})
    _run(_rm())


def _loss(qty, reason="negligence", note=""):
    set_current_org(GLOBAL_ORG)
    body = life.LossCreate(product_id=CHICKS, qty=qty, reason=reason, location_id=SHOP, note=note,
                           employee_id=STAFF if reason == "negligence" else None)
    return _run(life.record_stock_loss(body, _user(role="Staff")))


def _batch(days_ago=0, qty=100, supplier=""):
    set_current_org(GLOBAL_ORG)
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()[:19]
    return _run(life.create_batch(life.BatchCreate(product_id=CHICKS, qty=qty, location_id=SHOP,
                                                   received_at=when, supplier=supplier),
                                  _user(role="Staff")))["batch"]


# ------------------------------------------ the staff member's own copy
def test_a_deduction_says_in_words_what_it_is_for(shop):
    _loss(2, note="dropped the crate")
    lines, _ = _run(life.pending_loss_lines(STAFF, 500000))
    note = lines[0]["note"]
    assert "Brooder Chicks" in note
    assert "employee negligence" in note
    assert "dropped the crate" in note
    assert "Kate" in note                       # who wrote it off
    assert "taken in full" in note


def test_the_note_travels_on_the_payslip_line_itself(shop):
    _loss(1)
    lines, _ = _run(life.pending_loss_lines(STAFF, 500000))
    details = lines[0]["details"]
    assert isinstance(details, dict)
    assert details["note"] == lines[0]["note"]   # the PDF reads this, never the dict
    assert details["product_name"] == "Brooder Chicks"
    assert details["charged"] == 4000


def test_a_part_payment_says_what_is_still_to_come(shop):
    _loss(10)                                   # 40,000 charged
    lines, _ = _run(life.pending_loss_lines(STAFF, 15000))
    assert "15,000 off this payslip" in lines[0]["note"]
    assert "25,000 still to come" in lines[0]["note"]


# ------------------------------------------ two runs side by side
def test_two_runs_are_compared_and_the_weaker_one_is_named(shop):
    weak = _batch(days_ago=30, qty=50, supplier="Kabira Hatchery")
    strong = _batch(days_ago=3, qty=100, supplier="Nsambya Hatchery")
    _loss(10, reason="died")                    # oldest batch first → the weak run
    rep = _run(scr_compare([weak["id"], strong["id"]]))
    assert len(rep["batches"]) == 2
    assert rep["batches"][0]["supplier"] == "Kabira Hatchery"
    assert rep["batches"][0]["mortality_pct"] == 20.0
    assert rep["batches"][1]["mortality_pct"] == 0.0
    assert "Kabira Hatchery" in rep["verdict"]
    assert "20" in rep["verdict"] or "percentage points" in rep["verdict"]


def test_comparison_rolls_the_losses_up_per_supplier(shop):
    a = _batch(days_ago=30, qty=50, supplier="Kabira Hatchery")
    b = _batch(days_ago=3, qty=100, supplier="Nsambya Hatchery")
    _loss(5, reason="died")
    rep = _run(scr_compare([a["id"], b["id"]]))
    worst = rep["by_supplier"][0]
    assert worst["supplier"] == "Kabira Hatchery"
    assert worst["lost"] == 5 and worst["started_with"] == 50
    assert worst["mortality_pct"] == 10.0


def test_one_run_is_not_a_comparison(shop):
    only = _batch(qty=20)
    with pytest.raises(Exception) as err:
        _run(scr_compare([only["id"]]))
    assert "two runs" in str(err.value)


def test_a_hatchery_can_be_named_after_the_birds_arrive(shop):
    batch = _batch(qty=20)
    assert batch["supplier"] is None
    res = _run(life.update_batch(batch["id"], {"supplier": "Kabira Hatchery"}, _user(role="Staff")))
    assert res["batch"]["supplier"] == "Kabira Hatchery"


def test_survival_is_reported_next_to_the_losses(shop):
    a = _batch(days_ago=20, qty=100, supplier="Kabira Hatchery")
    b = _batch(days_ago=2, qty=100, supplier="Nsambya Hatchery")
    _loss(25, reason="died")
    rep = _run(scr_compare([a["id"], b["id"]]))
    assert rep["batches"][0]["survival_pct"] == 75.0


async def scr_compare(ids):
    return await life.compare_batches(",".join(ids), 8, _user(role="Staff"))


# ------------------------------------------ waiters signed on at the till
def _order(server=None, table="4", items=None):
    set_current_org(GLOBAL_ORG)
    body = kit.OrderCreate(
        items=items or [{"name": "Goat stew", "qty": 2, "price": 12000}],
        location_id=SHOP, table_label=table,
        server_id=(server or {}).get("id"), server_name=(server or {}).get("name"),
    )
    return _run(kit.create_order(body, _user(role="Staff", name="Till Operator", uid="till-1")))["order"]


def test_the_tab_belongs_to_the_waiter_who_signed_on(shop):
    order = _order(server={"id": STAFF, "name": "Moses"})
    assert order["server_id"] == STAFF
    assert order["server_name"] == "Moses"
    assert order["created_by_name"] == "Till Operator"     # who rang it up is kept too


def test_without_a_waiter_the_till_operator_is_recorded(shop):
    order = _order()
    assert order["server_name"] == "Till Operator"


def test_a_tip_is_recorded_against_the_waiter_who_served(shop):
    order = _order(server={"id": STAFF, "name": "Moses"})
    res = _run(kit.settle_order(order["id"], {"sale_id": "sale_x1", "tip": 3000},
                                _user(role="Staff")))
    assert res["tip"] == 3000
    assert "Moses" in res["message"]
    with org_bypass():
        row = _run(raw_db.kitchen_orders.find_one({"id": order["id"]}, {"_id": 0}))
    assert row["tip"] == 3000 and row["paid"] is True


def test_the_waiter_report_adds_up_tables_takings_and_tips(shop):
    first = _order(server={"id": STAFF, "name": "Moses"}, table="4")
    _order(server={"id": STAFF, "name": "Moses"}, table="5")
    _run(kit.settle_order(first["id"], {"sale_id": "sale_x2", "tip": 2000}, _user(role="Staff")))
    rep = _run(kit.server_report(SHOP, None, None, _user(role="Staff")))
    moses = next(s for s in rep["servers"] if s["server_id"] == STAFF)
    assert moses["tables"] == 2
    assert moses["open_tabs"] == 1
    assert moses["takings"] == 48000              # 2 tables x 2 x 12,000
    assert moses["tips"] == 2000
    assert rep["tips_total"] == 2000


def test_a_kitchen_is_closed_to_someone_who_works_elsewhere(shop):
    with pytest.raises(Exception) as err:
        _run(kit.list_orders(SHOP, "open", 50, _user(role="Manager", loc=OTHER, uid="outsider")))
    assert "not signed in" in str(err.value)


# ------------------------------------------ kitchen setup is the store's own
def test_only_a_manager_at_the_store_can_switch_the_kitchen_on(shop):
    outsider = _user(role="Manager", loc=OTHER, uid="outsider")
    with pytest.raises(Exception) as err:
        _run(cfg.update_store_settings(SHOP, {"restaurant_mode": True}, outsider))
    assert "signed in to this store" in str(err.value)
    res = _run(cfg.update_store_settings(SHOP, {"restaurant_mode": True}, _user()))
    assert res["restaurant_mode"] is True


def test_the_settings_say_whether_you_may_touch_the_kitchen(shop):
    mine = _run(cfg.get_store_settings(SHOP, _user()))
    theirs = _run(cfg.get_store_settings(SHOP, _user(role="Manager", loc=OTHER, uid="outsider")))
    assert mine["can_manage_restaurant"] is True
    assert theirs["can_manage_restaurant"] is False


# ------------------------------------------ screens on the wall
def _pair(kind="kitchen", user=None):
    set_current_org(GLOBAL_ORG)
    return _run(scr.pair_screen(scr.ScreenCreate(kind=kind, location_id=SHOP, name=f"{kind} screen"),
                                user or _user()))["screen"]


def test_a_screen_is_paired_once_and_opens_without_a_password(shop):
    screen = _pair("kitchen")
    assert screen["token"]
    info = _run(scr.screen_info(screen["token"]))
    assert info["kind"] == "kitchen"
    assert info["store_name"] == "Zimba Kitchen"


def test_a_screen_can_only_be_paired_by_someone_who_works_there(shop):
    with pytest.raises(Exception) as err:
        _pair("kitchen", _user(role="Manager", loc=OTHER, uid="outsider"))
    assert "signed in to this store" in str(err.value)


def test_the_kitchen_board_shows_this_store_s_open_tickets(shop):
    screen = _pair("kitchen")
    order = _order(server={"id": STAFF, "name": "Moses"})
    board = _run(scr.screen_orders(screen["token"], 60))
    assert [o["id"] for o in board] == [order["id"]]
    assert board[0]["total"] == 24000


def test_a_cook_can_move_a_dish_on_from_the_screen(shop):
    screen = _pair("kitchen")
    order = _order()
    line = order["items"][0]["line_id"]
    res = _run(scr.screen_advance_item(screen["token"], order["id"], line, {"status": "ready"}))
    assert res["status"] == "ready"
    assert res["order_status"] == "ready"


def test_an_unpaired_screen_stops_opening(shop):
    screen = _pair("kitchen")
    _run(scr.revoke_screen(screen["id"], _user()))
    with pytest.raises(Exception) as err:
        _run(scr.screen_info(screen["token"]))
    assert "not valid" in str(err.value)


def test_the_customer_display_waits_quietly_until_the_till_rings_something_up(shop):
    screen = _pair("sales")
    idle = _run(scr.screen_sale(screen["token"]))
    assert idle["state"] == "idle" and idle["lines"] == []
    _run(scr.push_live_sale(scr.LiveSale(
        location_id=SHOP, lines=[{"name": "Goat stew", "qty": 2, "price": 12000, "line_total": 24000}],
        subtotal=24000, total=24000, state="selling", currency="UGX", cashier="Moses"), _user(role="Staff")))
    live = _run(scr.screen_sale(screen["token"]))
    assert live["state"] == "selling"
    assert live["total"] == 24000
    assert live["lines"][0]["name"] == "Goat stew"


def test_a_screen_only_shows_what_it_was_paired_for(shop):
    kitchen = _pair("kitchen")
    display = _pair("sales")
    with pytest.raises(Exception) as err:
        _run(scr.screen_sale(kitchen["token"]))
    assert "kitchen screen" in str(err.value)
    with pytest.raises(Exception) as err2:
        _run(scr.screen_orders(display["token"], 60))
    assert "customer display" in str(err2.value)


# ------------------------------------------ one store cannot reach into another
def _outsider():
    return _user(role="Manager", loc=OTHER, uid="outsider")


def test_another_stores_ticket_cannot_be_cooked_settled_or_cancelled(shop):
    order = _order()
    line = order["items"][0]["line_id"]
    for call in (
        lambda: kit.add_items(order["id"], {"items": [{"name": "Soda", "qty": 1}]}, _outsider()),
        lambda: kit.set_order_status(order["id"], {"status": "ready"}, _outsider()),
        lambda: kit.set_item_status(order["id"], line, {"status": "ready"}, _outsider()),
        lambda: kit.settle_order(order["id"], {"sale_id": "sale_zz", "tip": 5000}, _outsider()),
        lambda: kit.cancel_order(order["id"], _outsider()),
    ):
        with pytest.raises(Exception) as err:
            _run(call())
        assert "another store" in str(err.value)


def test_another_stores_customer_display_cannot_be_hijacked(shop):
    with pytest.raises(Exception) as err:
        _run(scr.push_live_sale(scr.LiveSale(location_id=SHOP, total=1), _outsider()))
    assert "signed in to this store" in str(err.value)


def test_another_stores_runs_cannot_be_compared_or_renamed(shop):
    a = _batch(days_ago=10, qty=20)
    b = _batch(days_ago=2, qty=20)
    with pytest.raises(Exception) as err:
        _run(life.compare_batches(f"{a['id']},{b['id']}", 8, _outsider()))
    assert "another store" in str(err.value)
    with pytest.raises(Exception) as err2:
        _run(life.update_batch(a["id"], {"supplier": "Sneaky"}, _outsider()))
    assert "another store" in str(err2.value)


def test_runs_of_different_ages_are_compared_with_a_caveat(shop):
    old = _batch(days_ago=40, qty=50, supplier="Kabira Hatchery")
    young = _batch(days_ago=1, qty=50, supplier="Nsambya Hatchery")
    _loss(5, reason="died")
    rep = _run(scr_compare([old["id"], young["id"]]))
    assert "less time to lose anything" in rep["verdict"]
    assert rep["batches"][1]["age_days"] <= 1


def test_a_waiter_pin_is_checked_without_handing_out_a_session(shop):
    from types import SimpleNamespace

    from pin_security import pin_digest
    from routers import auth as auth_router
    pin = "913744"
    with org_bypass():
        _run(raw_db.users.update_one({"id": STAFF}, {"$set": {
            "pin_lookup": pin_digest(pin), "status": "active", "location_ids": [SHOP]}}))
    req = SimpleNamespace(headers={"x-forwarded-for": "203.0.113.9"}, client=None)
    res = _run(auth_router.pin_verify({"pin": pin, "store_id": SHOP}, req))
    assert res["user"]["name"] == "Moses"
    assert "token" not in res
    with pytest.raises(Exception) as err:
        _run(auth_router.pin_verify({"pin": "000111", "store_id": SHOP}, req))
    assert "Invalid PIN" in str(err.value)
