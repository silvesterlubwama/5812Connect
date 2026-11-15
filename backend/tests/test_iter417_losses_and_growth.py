# iter417: write-offs (spoilage, deaths, donations, negligence) and growing on.
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import stock_lifecycle as life  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP = f"loc_l_{uuid.uuid4().hex[:6]}"
OTHER = f"loc_o_{uuid.uuid4().hex[:6]}"
CHICKS = f"prod_c_{uuid.uuid4().hex[:6]}"
BROILERS = f"prod_b_{uuid.uuid4().hex[:6]}"
STAFF = f"user_s_{uuid.uuid4().hex[:6]}"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _staff_user():
    return {"id": "test-farmhand", "role": "Staff", "name": "Kate",
            "organization_id": GLOBAL_ORG, "location_id": SHOP}


@pytest.fixture
def farm():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_many([
                {"id": SHOP, "name": "Zimba Farm", "organization_id": GLOBAL_ORG},
                {"id": OTHER, "name": "Town Shop", "organization_id": GLOBAL_ORG},
            ])
            await raw_db.products.insert_many([
                {"id": CHICKS, "organization_id": GLOBAL_ORG, "name": "Brooder Chicks",
                 "location_id": SHOP, "stock": 50, "price": 4000,
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
            await raw_db.stock_losses.delete_many({"product_id": {"$in": [CHICKS, BROILERS]}})
            await raw_db.stock_batches.delete_many({"product_id": {"$in": [CHICKS, BROILERS]}})
            await raw_db.stock_transformations.delete_many({"from_product_id": CHICKS})
            await raw_db.stock_movements.delete_many({"product_id": {"$in": [CHICKS, BROILERS]}})
    _run(_rm())


def _loss(qty, reason, **kw):
    set_current_org(GLOBAL_ORG)
    body = life.LossCreate(product_id=kw.pop("product_id", CHICKS), qty=qty, reason=reason,
                           location_id=SHOP, **kw)
    return _run(life.record_stock_loss(body, _staff_user()))


def _stock(pid=CHICKS):
    with org_bypass():
        return int(_run(raw_db.products.find_one({"id": pid}, {"_id": 0, "stock": 1}))["stock"])


# ------------------------------------------------------------------ losses
def test_a_death_comes_off_the_count_and_gets_a_slip(farm):
    res = _loss(3, "died", note="Found in the brooder")
    assert _stock() == 47
    loss = res["loss"]
    assert loss["value"] == 12000                 # 3 x 4,000
    assert loss["slip_number"].startswith("LOSS-")
    assert loss["recoverable"] is False
    assert "died" in res["message"]


def test_negligence_is_charged_to_the_person_responsible(farm):
    res = _loss(2, "negligence", employee_id=STAFF)
    loss = res["loss"]
    assert loss["recoverable"] is True
    assert loss["recovery_status"] == "pending"
    assert loss["employee_name"] == "Moses"
    assert "come off their pay" in res["message"]
    owed = _run(life.pending_deductions(None, _staff_user()))
    assert owed["total"] == 8000
    assert owed["staff"][0]["employee_name"] == "Moses"


def test_negligence_needs_a_name(farm):
    with pytest.raises(HTTPException) as e:
        _loss(1, "negligence")
    assert e.value.status_code == 400
    assert _stock() == 50


def test_a_donation_gets_its_own_receipt_number(farm):
    res = _loss(5, "donated", donated_to="St Mary's school")
    assert res["loss"]["slip_number"].startswith("DON-")
    assert res["loss"]["donated_to"] == "St Mary's school"
    assert res["loss"]["recoverable"] is False
    assert "donated to St Mary's school" in res["message"]


def test_a_donation_needs_to_say_where_it_went(farm):
    with pytest.raises(HTTPException) as e:
        _loss(1, "donated")
    assert e.value.status_code == 400


def test_it_will_not_write_off_more_than_is_there(farm):
    with pytest.raises(HTTPException) as e:
        _loss(99, "spoiled")
    assert e.value.status_code == 400 and "on hand" in e.value.detail
    assert _stock() == 50


def test_an_unknown_reason_is_refused(farm):
    with pytest.raises(HTTPException) as e:
        _loss(1, "vanished")
    assert e.value.status_code == 400


def test_a_write_off_leaves_a_stock_movement_behind(farm):
    res = _loss(1, "stolen")
    with org_bypass():
        mv = _run(raw_db.stock_movements.find_one({"reference": res["loss"]["slip_number"]}, {"_id": 0}))
    assert mv and mv["delta"] == -1 and mv["reason"] == "loss"


def test_the_loss_report_adds_up_by_reason_and_product(farm):
    _loss(2, "died")
    _loss(1, "negligence", employee_id=STAFF)
    _loss(3, "donated", donated_to="Church")
    rep = _run(life.loss_report(TODAY, TODAY, SHOP, _staff_user()))
    assert rep["losses_count"] == 3
    assert rep["items_lost"] == 6
    assert rep["value_lost"] == 24000
    assert rep["to_recover"] == 4000
    assert rep["donated_value"] == 12000
    assert rep["worst"]["name"] == "Brooder Chicks"


def test_another_stores_write_offs_are_not_in_this_report(farm):
    _loss(2, "died")
    rep = _run(life.loss_report(TODAY, TODAY, OTHER, _staff_user()))
    assert rep["losses_count"] == 0


def test_marking_a_deduction_recovered(farm):
    res = _loss(1, "negligence", employee_id=STAFF)
    _run(life.update_loss_recovery(res["loss"]["id"], {"status": "recovered"}, _staff_user()))
    owed = _run(life.pending_deductions(None, _staff_user()))
    assert owed["total"] == 0


def test_only_a_negligence_loss_can_be_recovered(farm):
    res = _loss(1, "spoiled")
    with pytest.raises(HTTPException) as e:
        _run(life.update_loss_recovery(res["loss"]["id"], {"status": "recovered"}, _staff_user()))
    assert e.value.status_code == 400


# ------------------------------------------------------------------ batches
def _batch(qty=50, received=None):
    set_current_org(GLOBAL_ORG)
    body = life.BatchCreate(product_id=CHICKS, qty=qty, location_id=SHOP,
                            received_at=received, note="Hatchery run")
    return _run(life.create_batch(body, _staff_user()))


def test_an_intake_knows_when_it_will_grow_up(farm):
    res = _batch()
    batch = res["batch"]
    assert batch["becomes_product_name"] == "4 Week Broilers"
    expected = (datetime.fromisoformat(batch["received_at"]) + timedelta(days=28)).date().isoformat()
    assert batch["matures_at"][:10] == expected
    assert "4 Week Broilers" in res["message"]


def test_a_product_with_no_rule_cannot_have_a_batch(farm):
    set_current_org(GLOBAL_ORG)
    with pytest.raises(HTTPException) as e:
        _run(life.create_batch(life.BatchCreate(product_id=BROILERS, qty=5, location_id=SHOP),
                               _staff_user()))
    assert e.value.status_code == 400 and "growing-on rule" in e.value.detail


def test_a_due_batch_becomes_the_grown_product_at_the_new_price(farm):
    _batch(received=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat()[:19])
    res = _run(life.run_due_maturations())
    assert res["matured"] == 1
    assert _stock(CHICKS) == 0
    assert _stock(BROILERS) == 50
    with org_bypass():
        grow = _run(raw_db.stock_transformations.find_one({"from_product_id": CHICKS}, {"_id": 0}))
    assert grow["qty"] == 50
    assert grow["from_value"] == 200000          # 50 chicks at 4,000
    assert grow["to_value"] == 750000            # the same birds at the broiler price
    assert grow["needs_loss_check"] is True


def test_a_batch_that_is_not_due_stays_put(farm):
    _batch()
    res = _run(life.run_due_maturations())
    assert res["matured"] == 0
    assert _stock(CHICKS) == 50 and _stock(BROILERS) == 0


def test_running_it_twice_does_not_move_the_same_batch_twice(farm):
    _batch(received=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat()[:19])
    _run(life.run_due_maturations())
    again = _run(life.run_due_maturations())
    assert again["matured"] == 0
    assert _stock(BROILERS) == 50


def test_deaths_during_the_period_come_out_of_the_batch(farm):
    _batch()
    _loss(4, "died")
    with org_bypass():
        batch = _run(raw_db.stock_batches.find_one({"product_id": CHICKS}, {"_id": 0}))
    assert batch["remaining"] == 46 and batch["lost"] == 4


def test_growing_on_by_hand_can_record_the_deaths(farm):
    res = _batch()
    out = _run(life.mature_batch_now(res["batch"]["id"], {"lost": 5}, _staff_user()))
    assert out["qty"] == 45
    assert _stock(BROILERS) == 45
    assert _stock(CHICKS) == 0                   # the five that died left stock as a write-off
    rep = _run(life.loss_report(TODAY, TODAY, SHOP, _staff_user()))
    assert rep["items_lost"] == 5 and rep["by_reason"][0]["reason"] == "died"


def test_a_batch_can_only_be_grown_on_once(farm):
    res = _batch()
    _run(life.mature_batch_now(res["batch"]["id"], {}, _staff_user()))
    with pytest.raises(HTTPException) as e:
        _run(life.mature_batch_now(res["batch"]["id"], {}, _staff_user()))
    assert e.value.status_code == 400


def test_the_farm_can_mark_a_changeover_as_checked(farm):
    _batch(received=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat()[:19])
    _run(life.run_due_maturations())
    with org_bypass():
        grow = _run(raw_db.stock_transformations.find_one({"from_product_id": CHICKS}, {"_id": 0}))
    _run(life.acknowledge_transformation(grow["id"], _staff_user()))
    with org_bypass():
        again = _run(raw_db.stock_transformations.find_one({"id": grow["id"]}, {"_id": 0}))
    assert again["needs_loss_check"] is False
