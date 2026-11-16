# iter422: the shop's print helper — a receipt printer on the shop's own
# network, reached by a small helper running at the shop.
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
from routers import screens as scr  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
SHOP = f"loc_h_{uuid.uuid4().hex[:6]}"
OTHER = f"loc_i_{uuid.uuid4().hex[:6]}"
DATA = "SGVsbG8gcHJpbnRlcg=="          # "Hello printer"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user(role="Manager", loc=SHOP, uid="helper-boss"):
    return {"id": uid, "role": role, "name": "Kate",
            "organization_id": GLOBAL_ORG, "location_id": loc}


@pytest.fixture
def shop():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_many([
                {"id": SHOP, "name": "Kampala Shop", "organization_id": GLOBAL_ORG},
                {"id": OTHER, "name": "Jinja Shop", "organization_id": GLOBAL_ORG},
            ])
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.locations.delete_many({"id": {"$in": [SHOP, OTHER]}})
            await raw_db.device_screens.delete_many({"location_id": {"$in": [SHOP, OTHER]}})
            await raw_db.print_jobs.delete_many({"location_id": {"$in": [SHOP, OTHER]}})
    _run(_rm())


def _pair(kind="bridge", loc=SHOP):
    set_current_org(GLOBAL_ORG)
    return _run(scr.pair_screen(scr.ScreenCreate(kind=kind, location_id=loc, name="Shop print helper"),
                                _user(loc=loc)))["screen"]


def _alive(token):
    """One poll is what makes a helper 'running' — same as the real thing."""
    return _run(scr.claim_print_jobs(token, 5))


def _queue(loc=SHOP, host="192.168.1.50", title="Receipt 1"):
    set_current_org(GLOBAL_ORG)
    return _run(scr.queue_print_job(
        scr.PrintJob(location_id=loc, host=host, port=9100, data_b64=DATA, title=title),
        _user(role="Staff", loc=loc)))


# ---------------------------------------------- nothing queues into the void
def test_a_shop_with_no_helper_is_told_so_at_once(shop):
    with pytest.raises(Exception) as err:
        _queue()
    assert "No print helper" in str(err.value)


def test_a_helper_that_is_not_running_does_not_get_the_receipt(shop):
    _pair()                                   # paired, never started
    with pytest.raises(Exception) as err:
        _queue()
    assert "not running" in str(err.value)


def test_a_helper_gone_quiet_stops_taking_work(shop):
    helper = _pair()
    _alive(helper["token"])
    with org_bypass():
        _run(raw_db.device_screens.update_one({"id": helper["id"]}, {"$set": {
            "last_seen_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}}))
    with pytest.raises(Exception) as err:
        _queue()
    assert "not running" in str(err.value)


# ---------------------------------------------- the round trip
def test_the_receipt_goes_out_and_the_till_hears_that_it_printed(shop):
    helper = _pair()
    _alive(helper["token"])
    job = _queue(title="Receipt INV-1")
    assert job["queued"] is True and job["helper_paired"] is True

    claimed = _run(scr.claim_print_jobs(helper["token"], 5))
    assert [c["id"] for c in claimed] == [job["job_id"]]
    assert claimed[0]["host"] == "192.168.1.50"
    assert claimed[0]["data_b64"] == DATA       # the helper needs the bytes
    assert claimed[0]["attempts"] == 1

    done = _run(scr.finish_print_job(helper["token"], job["job_id"], {"ok": True}))
    assert done["status"] == "printed"
    seen = _run(scr.print_job_status(job["job_id"], _user(role="Staff")))
    assert seen["status"] == "printed"
    assert "data_b64" not in seen               # no need to ship it back


def test_a_claimed_receipt_is_not_handed_out_twice(shop):
    helper = _pair()
    _alive(helper["token"])
    _queue()
    assert len(_run(scr.claim_print_jobs(helper["token"], 5))) == 1
    assert _run(scr.claim_print_jobs(helper["token"], 5)) == []


def test_a_helper_unplugged_mid_job_does_not_lose_the_receipt(shop):
    helper = _pair()
    _alive(helper["token"])
    job = _queue()
    _run(scr.claim_print_jobs(helper["token"], 5))
    with org_bypass():
        _run(raw_db.print_jobs.update_one({"id": job["job_id"]}, {"$set": {
            "claimed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}}))
    again = _run(scr.claim_print_jobs(helper["token"], 5))
    assert [c["id"] for c in again] == [job["job_id"]]
    assert again[0]["attempts"] == 2


def test_a_printer_that_refuses_is_tried_again_then_given_up_on(shop):
    helper = _pair()
    _alive(helper["token"])
    job = _queue()
    for _ in range(2):
        _run(scr.claim_print_jobs(helper["token"], 5))
        res = _run(scr.finish_print_job(helper["token"], job["job_id"], {"ok": False, "error": "no answer"}))
        assert res["status"] == "queued"        # worth another go
    _run(scr.claim_print_jobs(helper["token"], 5))
    res = _run(scr.finish_print_job(helper["token"], job["job_id"], {"ok": False, "error": "no answer"}))
    assert res["status"] == "failed"
    assert _run(scr.print_job_status(job["job_id"], _user(role="Staff")))["error"] == "no answer"


def test_a_receipt_nobody_collected_is_not_printed_an_hour_late(shop):
    helper = _pair()
    _alive(helper["token"])
    job = _queue()
    with org_bypass():
        _run(raw_db.print_jobs.update_one({"id": job["job_id"]}, {"$set": {
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}}))
    assert _run(scr.claim_print_jobs(helper["token"], 5)) == []
    assert _run(scr.print_job_status(job["job_id"], _user(role="Staff")))["status"] == "expired"


def test_receipts_come_out_in_the_order_they_were_rung_up(shop):
    helper = _pair()
    _alive(helper["token"])
    first = _queue(title="Receipt 1")
    second = _queue(title="Receipt 2")
    claimed = _run(scr.claim_print_jobs(helper["token"], 5))
    assert [c["id"] for c in claimed] == [first["job_id"], second["job_id"]]


# ---------------------------------------------- one shop cannot print at another
def test_a_helper_only_ever_sees_its_own_shop(shop):
    mine = _pair(loc=SHOP)
    theirs = _pair(loc=OTHER)
    _alive(mine["token"])
    _alive(theirs["token"])
    job = _queue(loc=SHOP)
    assert _run(scr.claim_print_jobs(theirs["token"], 5)) == []
    with pytest.raises(Exception) as err:
        _run(scr.finish_print_job(theirs["token"], job["job_id"], {"ok": True}))
    assert "not yours" in str(err.value)


def test_a_till_elsewhere_cannot_queue_or_read_this_shops_printing(shop):
    helper = _pair()
    _alive(helper["token"])
    job = _queue()
    outsider = _user(role="Manager", loc=OTHER, uid="outsider")
    with pytest.raises(Exception) as err:
        _run(scr.print_job_status(job["job_id"], outsider))
    assert "another store" in str(err.value)
    with pytest.raises(Exception) as err2:
        _run(scr.queue_print_job(scr.PrintJob(location_id=SHOP, host="1.2.3.4", data_b64=DATA), outsider))
    assert "not signed in" in str(err2.value)


def test_a_kitchen_screen_cannot_pretend_to_be_the_print_helper(shop):
    kitchen = _pair(kind="kitchen")
    with pytest.raises(Exception) as err:
        _run(scr.claim_print_jobs(kitchen["token"], 5))
    assert "not a print helper" in str(err.value)
    helper = _pair()
    with pytest.raises(Exception) as err2:
        _run(scr.screen_orders(helper["token"], 10))
    assert "customer display" in str(err2.value) or "kitchen" in str(err2.value)


# ---------------------------------------------- the helper itself
def test_the_helper_arrives_knowing_its_own_shop(shop):
    from types import SimpleNamespace
    helper = _pair()
    req = SimpleNamespace(base_url="https://shop.example.com/")
    ps1 = _run(scr.bridge_script(helper["token"], "ps1", "", req)).body.decode()
    assert "__TOKEN__" not in ps1 and "__API__" not in ps1
    assert helper["token"] in ps1
    assert "https://shop.example.com/api" in ps1
    py = _run(scr.bridge_script(helper["token"], "py", "", req)).body.decode()
    assert helper["token"] in py
    assert "socket.create_connection" in py
    assert "58-12-print-helper" in py and "58-12-print-helper" in ps1   # or the firewall turns it away

    # The browser tells us the address the shop actually uses: behind an
    # ingress the server only knows its own internal name (iter422).
    told = _run(scr.bridge_script(helper["token"], "py", "https://shop.example.com", req)).body.decode()
    assert "https://shop.example.com/api" in told
    junk = _run(scr.bridge_script(helper["token"], "py", "not a url'; rm -rf /", req)).body.decode()
    assert "rm -rf" not in junk


def test_only_a_helper_link_hands_out_the_helper(shop):
    display = _pair(kind="sales")
    from types import SimpleNamespace
    with pytest.raises(Exception) as err:
        _run(scr.bridge_script(display["token"], "ps1", "", SimpleNamespace(base_url="https://x/")))
    assert "not a print helper" in str(err.value)


def test_an_oversized_job_is_refused_rather_than_stored(shop):
    helper = _pair()
    _alive(helper["token"])
    with pytest.raises(Exception) as err:
        _run(scr.queue_print_job(
            scr.PrintJob(location_id=SHOP, host="192.168.1.50", data_b64="A" * 2_000_001),
            _user(role="Staff")))
    assert "too big" in str(err.value)
