# iter419: negligence charges onto the payslip, and mortality week by week.
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
CHICKS = f"prod_m_{uuid.uuid4().hex[:6]}"
BROILERS = f"prod_n_{uuid.uuid4().hex[:6]}"
STAFF = f"user_p_{uuid.uuid4().hex[:6]}"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user():
    return {"id": "test-farmhand", "role": "Staff", "name": "Kate",
            "organization_id": GLOBAL_ORG, "location_id": SHOP}


@pytest.fixture
def farm():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_one({"id": SHOP, "name": "Zimba Farm",
                                                "organization_id": GLOBAL_ORG})
            await raw_db.products.insert_many([
                {"id": CHICKS, "organization_id": GLOBAL_ORG, "name": "Brooder Chicks",
                 "location_id": SHOP, "stock": 100, "price": 4000,
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
            await raw_db.locations.delete_many({"id": SHOP})
            await raw_db.users.delete_many({"id": STAFF})
            await raw_db.stock_losses.delete_many({"location_id": SHOP})
            await raw_db.stock_batches.delete_many({"location_id": SHOP})
            await raw_db.stock_movements.delete_many({"location_id": SHOP})
            await raw_db.stock_transformations.delete_many({"location_id": SHOP})
    _run(_rm())


def _loss(qty, reason="negligence", **kw):
    set_current_org(GLOBAL_ORG)
    pid = kw.pop("product_id", CHICKS)
    # iter424 — the batch has to be named; these tests keep one open batch.
    if "batch_id" not in kw:
        open_batches = _run(life.open_batches_for(pid, SHOP, kw.get("variant_id")))
        if open_batches:
            kw["batch_id"] = open_batches[0]["id"]
    body = life.LossCreate(product_id=pid, qty=qty, reason=reason, location_id=SHOP,
                           employee_id=STAFF if reason == "negligence" else None, **kw)
    return _run(life.record_stock_loss(body, _user()))


# ------------------------------------------------- payslip deductions
def test_a_negligence_charge_becomes_a_payslip_deduction_line(farm):
    _loss(2)                                        # 2 x 4,000 = 8,000
    lines, apps = _run(life.pending_loss_lines(STAFF, 500000))
    assert len(lines) == 1
    assert lines[0]["amount"] == 8000
    assert lines[0]["type"] == "deduction"
    assert lines[0]["source"] == "stock_loss"
    assert "Brooder Chicks" in lines[0]["name"]
    assert apps[0]["amount"] == 8000


def test_working_out_the_lines_changes_nothing_until_the_payslip_is_saved(farm):
    _loss(2)
    _run(life.pending_loss_lines(STAFF, 500000))
    owed = _run(life.pending_deductions(STAFF, _user()))
    assert owed["total"] == 8000                    # a preview must not swallow it


def test_marking_it_takes_it_off_what_is_owed(farm):
    _loss(2)
    _, apps = _run(life.pending_loss_lines(STAFF, 500000))
    _run(life.mark_loss_deductions(apps, "ps_test01", "2026-11"))
    owed = _run(life.pending_deductions(STAFF, _user()))
    assert owed["total"] == 0
    with org_bypass():
        row = _run(raw_db.stock_losses.find_one({"employee_id": STAFF}, {"_id": 0}))
    assert row["recovery_status"] == "recovered"
    assert row["deductions"][0]["payslip_id"] == "ps_test01"


def test_a_charge_bigger_than_the_pay_is_taken_in_instalments(farm):
    _loss(10)                                       # 40,000 owed
    lines, apps = _run(life.pending_loss_lines(STAFF, 15000))
    assert lines[0]["amount"] == 15000
    assert "(part)" in lines[0]["name"]
    _run(life.mark_loss_deductions(apps, "ps_test02", "2026-11"))
    owed = _run(life.pending_deductions(STAFF, _user()))
    assert owed["total"] == 25000                   # the rest waits for next month
    nxt, _ = _run(life.pending_loss_lines(STAFF, 500000))
    assert nxt[0]["amount"] == 25000


def test_nothing_is_taken_when_there_is_no_pay_left(farm):
    _loss(2)
    lines, apps = _run(life.pending_loss_lines(STAFF, 0))
    assert lines == [] and apps == []


def test_deleting_the_payslip_puts_the_charge_back(farm):
    _loss(2)
    _, apps = _run(life.pending_loss_lines(STAFF, 500000))
    _run(life.mark_loss_deductions(apps, "ps_test03", "2026-11"))
    assert _run(life.pending_deductions(STAFF, _user()))["total"] == 0
    undone = _run(life.unmark_loss_deductions("ps_test03"))
    assert undone == 1
    assert _run(life.pending_deductions(STAFF, _user()))["total"] == 8000


def test_an_ordinary_write_off_never_reaches_anyones_pay(farm):
    _loss(3, reason="spoiled")
    lines, _ = _run(life.pending_loss_lines(STAFF, 500000))
    assert lines == []


def test_several_charges_come_off_oldest_first(farm):
    _loss(1)
    _loss(2)
    lines, _ = _run(life.pending_loss_lines(STAFF, 500000))
    assert [line["amount"] for line in lines] == [4000, 8000]


# ------------------------------------------------- mortality by week
def _batch(days_ago=0, qty=100):
    set_current_org(GLOBAL_ORG)
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()[:19]
    return _run(life.create_batch(life.BatchCreate(product_id=CHICKS, qty=qty, location_id=SHOP,
                                                   received_at=when), _user()))["batch"]


def test_mortality_counts_deaths_into_the_week_they_happened(farm):
    _batch(days_ago=10)
    _loss(4, reason="died")                         # today = week 2 of that batch
    rep = _run(life.batch_mortality(CHICKS, SHOP, 8, 20, _user()))
    row = rep["batches"][0]
    assert row["started_with"] == 100
    assert row["lost"] == 4
    assert row["mortality_pct"] == 4.0
    weeks = {w["week"]: w["deaths"] for w in row["weeks"]}
    assert weeks[2] == 4 and weeks[1] == 0
    assert row["by_reason"]["Died"] == 4


def test_a_clean_batch_reports_no_deaths(farm):
    _batch()
    rep = _run(life.batch_mortality(CHICKS, SHOP, 8, 20, _user()))
    assert rep["batches"][0]["lost"] == 0
    assert rep["worst"] is None


def test_the_weakest_run_stands_out(farm):
    good = _batch(days_ago=3, qty=100)
    _batch(days_ago=40, qty=50)
    # kill 10 off the older (second) batch — losses take the OLDEST batch first
    _loss(10, reason="died")
    rep = _run(life.batch_mortality(CHICKS, SHOP, 8, 20, _user()))
    worst = rep["worst"]
    assert worst["lost"] == 10
    assert worst["mortality_pct"] == 20.0           # 10 of 50
    assert worst["batch_id"] != good["id"]


def test_every_kind_of_loss_shows_in_the_breakdown(farm):
    _batch(days_ago=2)
    _loss(2, reason="died")
    _loss(1, reason="stolen")
    rep = _run(life.batch_mortality(CHICKS, SHOP, 8, 20, _user()))
    row = rep["batches"][0]
    assert row["by_reason"]["Died"] == 2
    assert row["by_reason"]["Stolen or missing"] == 1
    assert row["lost"] == 3


def test_a_farm_with_no_batches_gets_an_empty_chart(farm):
    rep = _run(life.batch_mortality(CHICKS, SHOP, 8, 20, _user()))
    assert rep["batches"] == [] and rep["worst"] is None
