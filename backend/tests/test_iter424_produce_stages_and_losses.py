# iter424: losses come off a named batch and a named variant, variants carry
# their own price and count, and produce grows through its own stages.
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
from routers import stock_lifecycle as life  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP = f"loc_p_{uuid.uuid4().hex[:6]}"
BIRDS = f"prod_p_{uuid.uuid4().hex[:6]}"
PLAIN = f"prod_s_{uuid.uuid4().hex[:6]}"
CHICK = "var_chick"
BROILER = "var_broiler"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user(role="Staff"):
    return {"id": "produce-boss", "role": role, "name": "Kate",
            "organization_id": GLOBAL_ORG, "location_id": SHOP}


@pytest.fixture
def farm():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_one({"id": SHOP, "name": "Zimba Farm", "organization_id": GLOBAL_ORG})
            await raw_db.products.insert_many([
                {"id": BIRDS, "organization_id": GLOBAL_ORG, "name": "Broiler Birds",
                 "location_id": SHOP, "price": 0, "stock": 0, "is_produce": True, "has_variants": True,
                 "variants": [
                     {"id": CHICK, "name": "Day-old chicks", "price": 4000, "stock": 0,
                      "grow_after_days": 28},
                     {"id": BROILER, "name": "4 Week Broilers", "price": 15000, "stock": 0},
                 ]},
                {"id": PLAIN, "organization_id": GLOBAL_ORG, "name": "Maize Flour",
                 "location_id": SHOP, "price": 3000, "stock": 50},
            ])
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.products.delete_many({"id": {"$in": [BIRDS, PLAIN]}})
            await raw_db.locations.delete_many({"id": SHOP})
            for col in ("stock_losses", "stock_batches", "stock_movements", "stock_transformations"):
                await raw_db[col].delete_many({"location_id": SHOP})
    _run(_rm())


def _intake(qty=100, days_ago=0, supplier="Kabira Hatchery", variant=CHICK, add_stock=True):
    set_current_org(GLOBAL_ORG)
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()[:19]
    return _run(life.create_batch(life.BatchCreate(
        product_id=BIRDS, variant_id=variant, qty=qty, location_id=SHOP,
        received_at=when, supplier=supplier, add_stock=add_stock), _user()))


def _variant(vid):
    with org_bypass():
        prod = _run(raw_db.products.find_one({"id": BIRDS}, {"_id": 0}))
    return next(v for v in prod["variants"] if v["id"] == vid), prod


def _loss(qty, variant_id=None, batch_id=None, product_id=BIRDS, reason="died"):
    set_current_org(GLOBAL_ORG)
    return _run(life.record_stock_loss(life.LossCreate(
        product_id=product_id, qty=qty, reason=reason, location_id=SHOP,
        variant_id=variant_id, batch_id=batch_id), _user()))


# ------------------------------------- booking produce in
def test_booking_a_batch_in_also_books_the_birds_in(farm):
    res = _intake(qty=100)
    chick, prod = _variant(CHICK)
    assert chick["stock"] == 100
    assert prod["stock"] == 100                       # the parent is the total
    assert res["batch"]["variant_name"] == "Day-old chicks"
    assert res["batch"]["becomes_variant_name"] == "4 Week Broilers"
    assert "4 Week Broilers" in res["message"]


def test_produce_must_say_which_stage_came_in(farm):
    with pytest.raises(Exception) as err:
        _run(life.create_batch(life.BatchCreate(product_id=BIRDS, qty=50, location_id=SHOP), _user()))
    assert "Which stage" in str(err.value)


def test_a_final_stage_cannot_start_a_clock(farm):
    with pytest.raises(Exception) as err:
        _intake(qty=10, variant=BROILER)
    assert "no stage to grow into" in str(err.value)


# ------------------------------------- the loss has to come off something real
def test_a_variant_item_will_not_let_you_write_off_thin_air(farm):
    _intake(qty=100)
    with pytest.raises(Exception) as err:
        _loss(5)
    assert "Pick the variant" in str(err.value)


def test_a_loss_must_name_the_batch_it_came_from(farm):
    _intake(qty=100)
    with pytest.raises(Exception) as err:
        _loss(5, variant_id=CHICK)
    assert "which batch" in str(err.value)


def test_the_loss_comes_off_that_batch_and_no_other(farm):
    weak = _intake(qty=50, days_ago=10, supplier="Kabira Hatchery")["batch"]
    strong = _intake(qty=50, days_ago=2, supplier="Nsambya Hatchery")["batch"]
    _loss(6, variant_id=CHICK, batch_id=strong["id"])
    with org_bypass():
        rows = {b["id"]: b for b in _run(raw_db.stock_batches.find({"location_id": SHOP}, {"_id": 0}).to_list(5))}
    assert rows[strong["id"]]["lost"] == 6 and rows[strong["id"]]["remaining"] == 44
    assert rows[weak["id"]]["lost"] == 0 and rows[weak["id"]]["remaining"] == 50


def test_a_loss_bigger_than_the_batch_is_refused(farm):
    """There are 40 chicks on the farm, but only 20 in THIS batch."""
    batch = _intake(qty=20, days_ago=5)["batch"]
    _intake(qty=20, days_ago=1, supplier="Nsambya Hatchery")
    with pytest.raises(Exception) as err:
        _loss(25, variant_id=CHICK, batch_id=batch["id"])
    assert "only has 20 left" in str(err.value)


def test_a_loss_bigger_than_the_stage_is_refused_by_name(farm):
    batch = _intake(qty=20)["batch"]
    with pytest.raises(Exception) as err:
        _loss(25, variant_id=CHICK, batch_id=batch["id"])
    assert "Only 20 of Broiler Birds — Day-old chicks on hand" in str(err.value)


def test_the_loss_is_valued_at_the_variants_own_price(farm):
    batch = _intake(qty=100)["batch"]
    res = _loss(3, variant_id=CHICK, batch_id=batch["id"])
    assert res["loss"]["value"] == 12000               # 3 chicks at 4,000, not the parent's 0
    chick, _ = _variant(CHICK)
    assert chick["stock"] == 97


def test_a_broiler_lost_is_not_priced_as_a_chick(farm):
    _intake(qty=10)
    with org_bypass():
        _run(raw_db.products.update_one({"id": BIRDS, "variants.id": BROILER},
                                        {"$set": {"variants.$.stock": 5}}))
    res = _loss(2, variant_id=BROILER, reason="stolen")
    assert res["loss"]["value"] == 30000                # 2 x 15,000
    assert res["loss"]["variant_id"] == BROILER


def test_an_item_without_variants_still_writes_off_simply(farm):
    res = _loss(4, product_id=PLAIN, reason="spoiled")
    assert res["loss"]["value"] == 12000
    with org_bypass():
        prod = _run(raw_db.products.find_one({"id": PLAIN}, {"_id": 0, "stock": 1}))
    assert prod["stock"] == 46


def test_a_variant_id_on_a_plain_item_is_refused(farm):
    with pytest.raises(Exception) as err:
        _loss(1, product_id=PLAIN, variant_id=CHICK)
    assert "not kept as variants" in str(err.value)


# ------------------------------------- growing through stages
def test_chicks_become_broilers_within_the_same_item(farm):
    batch = _intake(qty=100, days_ago=30)["batch"]
    _loss(10, variant_id=CHICK, batch_id=batch["id"])
    with org_bypass():
        fresh = _run(raw_db.stock_batches.find_one({"id": batch["id"]}, {"_id": 0}))
    res = _run(life.mature_batch(fresh, _user()))
    assert res["ok"] and res["qty"] == 90
    assert res["stage"] == "4 Week Broilers"
    chick, prod = _variant(CHICK)
    broiler, _ = _variant(BROILER)
    assert chick["stock"] == 0
    assert broiler["stock"] == 90
    assert prod["stock"] == 90                         # nothing invented, nothing lost twice


def test_the_batch_follows_the_birds_and_keeps_its_history(farm):
    batch = _intake(qty=40, days_ago=30, supplier="Kabira Hatchery")["batch"]
    _loss(4, variant_id=CHICK, batch_id=batch["id"])
    with org_bypass():
        fresh = _run(raw_db.stock_batches.find_one({"id": batch["id"]}, {"_id": 0}))
    _run(life.mature_batch(fresh, _user()))
    with org_bypass():
        after = _run(raw_db.stock_batches.find_one({"id": batch["id"]}, {"_id": 0}))
    assert after["variant_name"] == "4 Week Broilers"
    assert after["status"] == "matured"                # no further stage
    assert after["supplier"] == "Kabira Hatchery"
    assert after["lost"] == 4                          # its mortality stays with it
    assert after["qty"] == 40


def test_the_value_of_growing_on_is_the_stage_price(farm):
    batch = _intake(qty=10, days_ago=30)["batch"]
    with org_bypass():
        fresh = _run(raw_db.stock_batches.find_one({"id": batch["id"]}, {"_id": 0}))
    _run(life.mature_batch(fresh, _user()))
    with org_bypass():
        moved = _run(raw_db.stock_transformations.find_one({"batch_id": batch["id"]}, {"_id": 0}))
    assert moved["from_value"] == 40000                # 10 chicks at 4,000
    assert moved["to_value"] == 150000                 # 10 broilers at 15,000
    assert moved["to_product_name"].endswith("4 Week Broilers")


def test_growing_on_with_nothing_left_blocks_rather_than_inventing_birds(farm):
    batch = _intake(qty=5, days_ago=30)["batch"]
    with org_bypass():
        _run(raw_db.products.update_one({"id": BIRDS, "variants.id": CHICK},
                                        {"$set": {"variants.$.stock": 0}}))
        fresh = _run(raw_db.stock_batches.find_one({"id": batch["id"]}, {"_id": 0}))
    res = _run(life.mature_batch(fresh, _user()))
    assert res["ok"] is False and res["reason"] == "no_stock"
    broiler, _ = _variant(BROILER)
    assert broiler["stock"] == 0


def test_mortality_is_reported_per_stage_batch(farm):
    batch = _intake(qty=100, days_ago=14, supplier="Kabira Hatchery")["batch"]
    _loss(7, variant_id=CHICK, batch_id=batch["id"])
    with org_bypass():
        rows = _run(raw_db.stock_batches.find({"location_id": SHOP}, {"_id": 0}).to_list(5))
    report = _run(life._mortality_rows(rows, 8))
    assert report[0]["variant_name"] == "Day-old chicks"
    assert report[0]["lost"] == 7
    assert report[0]["mortality_pct"] == 7.0
    assert report[0]["supplier"] == "Kabira Hatchery"
