# iter426: the assistant's memory — organisation paperwork it may show, figures
# it may quote, and a payout that can be backed out of the books.
import asyncio
import io
import sys
import uuid

import pytest
from starlette.datastructures import Headers, UploadFile

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import org_documents as od  # noqa: E402
from routers import ai_knowledge as kb  # noqa: E402
from routers import funds  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
TAG = uuid.uuid4().hex[:6]
CAMPUS = f"loc_k_{TAG}"
STAFF = {"id": f"usr_s_{TAG}", "role": "Staff", "name": "Esther", "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
MANAGER = {"id": f"usr_m_{TAG}", "role": "Manager", "name": "Peter", "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
BOSS = {"id": f"usr_d_{TAG}", "role": "Director", "name": "Deborah", "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
ACCTS = {
    "fees": {"id": f"acc_f_{TAG}", "code": f"8{TAG[:3]}1", "name": "Programme Costs ZT", "type": "expense"},
    "bank": {"id": f"acc_b_{TAG}", "code": f"8{TAG[:3]}2", "name": "Campus Bank ZT", "type": "asset"},
}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _upload(data: bytes, name: str, mime: str):
    return UploadFile(filename=name, file=io.BytesIO(data), headers=Headers({"content-type": mime}))


@pytest.fixture
def org(monkeypatch):
    # The model is not called in tests — we file the paperwork ourselves.
    async def _no_model(path, mime, extracted):
        return {}
    monkeypatch.setattr(od, "_read_with_model", _no_model)
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_one({"id": CAMPUS, "name": "Hope Campus", "organization_id": GLOBAL_ORG})
            await raw_db.finance_chart_of_accounts.insert_many(
                [{**a, "active": True, "organization_id": GLOBAL_ORG} for a in ACCTS.values()])
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.org_documents.delete_many({"uploaded_by": {"$in": [MANAGER["id"], BOSS["id"]]}})
            await raw_db.locations.delete_many({"id": CAMPUS})
            await raw_db.finance_chart_of_accounts.delete_many({"id": {"$in": [a["id"] for a in ACCTS.values()]}})
            await raw_db.finance_account_access.delete_many({"user_id": STAFF["id"]})
            await raw_db.finance_journal_entries.delete_many({"location_id": CAMPUS})
            await raw_db.finance_deleted_entries.delete_many({"location_id": CAMPUS})
            await raw_db.approval_requests.delete_many({"location_id": CAMPUS})
            await raw_db.financial.delete_many({"location_id": CAMPUS})
    _run(_rm())


def _file_doc(text=b"NGO OPERATING PERMIT\nIssued by the NGO Bureau.\nValid until 2027-03-31.",
              title="NGO operating permit", level=5, expires="2027-03-31", user=MANAGER, name="permit.txt",
              mime="text/plain"):
    set_current_org(GLOBAL_ORG)
    return _run(od.upload_document(file=_upload(text, name, mime), title=title, doc_type="permit",
                                  min_level=level, expires_on=expires, notes=None, current_user=user))


# ------------------------------------------------- filing
def test_a_manager_files_a_permit_and_its_words_are_kept(org):
    doc = _file_doc()
    assert doc["title"] == "NGO operating permit"
    assert doc["expires_on"] == "2027-03-31"
    assert doc["min_level"] == 5
    with org_bypass():
        stored = _run(raw_db.org_documents.find_one({"id": doc["id"]}, {"_id": 0}))
    assert "NGO BUREAU" in stored["text"].upper()


def test_rubbish_file_types_are_turned_away(org):
    with pytest.raises(Exception) as err:
        _run(od.upload_document(file=_upload(b"MZ\x90", "hack.exe", "application/x-msdownload"),
                                title=None, doc_type=None, min_level=5, expires_on=None, notes=None,
                                current_user=MANAGER))
    assert "can't be filed" in str(err.value)


# ------------------------------------------------- who may see what
def test_a_staff_member_never_learns_a_managers_only_paper_exists(org):
    open_doc = _file_doc(title="Fire certificate", level=5)
    secret = _file_doc(text=b"Board minutes: salaries discussed", title="Board minutes", level=7)
    rows = _run(od.list_documents(q=None, doc_type=None, limit=50, current_user=STAFF))
    ids = [r["id"] for r in rows]
    assert open_doc["id"] in ids
    assert secret["id"] not in ids
    with pytest.raises(Exception) as err:
        _run(od.get_document(secret["id"], STAFF))
    assert "not found" in str(err.value).lower()
    # ...and cannot be downloaded by guessing the id either.
    with pytest.raises(Exception) as err:
        _run(od.download_document(secret["id"], STAFF))
    assert "not found" in str(err.value).lower()
    assert _run(od.get_document(secret["id"], BOSS))["id"] == secret["id"]


def test_the_assistant_only_searches_what_the_asker_may_read(org):
    _file_doc(title="NGO operating permit", level=5)
    _file_doc(text=b"Confidential lease agreement", title="Head office lease", level=8)
    hits = _run(kb.search_documents(STAFF, "when does our NGO permit expire?"))
    titles = [h["title"] for h in hits]
    assert "NGO operating permit" in titles
    assert "Head office lease" not in titles
    boss_hits = _run(kb.search_documents(BOSS, "lease agreement"))
    assert any(h["title"] == "Head office lease" for h in boss_hits)


def test_an_expiring_permit_can_be_found_before_it_lapses(org):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=20)).isoformat()
    _file_doc(title="Vehicle licence", level=5, expires=soon)
    rows = _run(od.expiring_documents(days=60, current_user=STAFF))
    mine = [r for r in rows if r["title"] == "Vehicle licence"]
    assert mine and mine[0]["days_left"] == 20


def test_a_photographed_receipt_becomes_a_pdf(org):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), (240, 240, 240)).save(buf, "PNG")
    shot = _file_doc(text=buf.getvalue(), title="Fuel receipt", level=5, expires=None,
                     name="receipt.png", mime="image/png")
    pdf = _run(od.convert_to_pdf(shot["id"], MANAGER))
    assert pdf["mime"] == "application/pdf" and pdf["derived_from"] == shot["id"]
    assert pdf["title"].endswith("(PDF)")


# ------------------------------------------------- what figures may be quoted
def test_a_staff_member_is_told_why_the_spend_is_not_theirs_to_see(org):
    out = _run(kb.answer_data_question(STAFF, "how much money did the organisation spend last month?"))
    assert out["denied"] is True
    assert "finance access" in out["answer"]
    assert "Chart of Accounts" in out["answer"]           # tells them how to get it


def test_a_staff_member_with_their_own_account_gets_their_own_figures(org):
    with org_bypass():
        _run(raw_db.finance_account_access.insert_one({
            "id": f"facc_{TAG}", "user_id": STAFF["id"], "account_ids": [ACCTS["fees"]["id"]]}))
    out = _run(kb.answer_data_question(STAFF, "how much have I spent this month?"))
    assert out["denied"] is False
    assert "your own" in out["preamble"].lower()
    assert ACCTS["fees"]["name"] in out["facts"]


def test_payroll_stays_with_hr(org):
    out = _run(kb.answer_data_question(STAFF, "what is the total payroll this month?"))
    assert out["denied"] is True and "HR access" in out["answer"]


def test_a_director_gets_the_organisation_totals(org):
    out = _run(kb.answer_data_question(BOSS, "how much did we spend last month?"))
    assert out["denied"] is False and out["scope"] == "org"
    assert "Total spend" in out["facts"]


def test_a_question_about_nothing_financial_is_left_alone(org):
    assert _run(kb.answer_data_question(STAFF, "when does our NGO permit expire?")) is None


# ------------------------------------------------- undoing a payout
@pytest.fixture
def paid_request(org):
    req = {
        "id": f"areq_{TAG}", "subject_kind": "fund_request", "status": "approved",
        "title": "Advance — fuel", "summary": "Fuel", "amount": 90000, "currency": "UGX",
        "location_id": CAMPUS, "submitted_by": STAFF["id"], "submitted_by_name": "Esther",
        "metadata": {"kind": "advance"}, "step_states": [], "created_at": "2026-06-01T07:00:00+00:00",
    }
    with org_bypass():
        _run(raw_db.approval_requests.insert_one(dict(req)))
    set_current_org(GLOBAL_ORG)
    admin = {**BOSS, "role": "system_admin"}
    res = _run(funds.mark_paid(req["id"], {"paid_from_account_id": ACCTS["bank"]["id"],
                                           "expense_account_id": ACCTS["fees"]["id"]}, admin))
    return req["id"], res, admin


def test_backing_out_a_payment_squares_the_books_and_voids_the_voucher(paid_request):
    rid, paid, admin = paid_request
    out = _run(funds.undo_payment(rid, {"reason": "Paid from the wrong account"}, admin))
    assert out["undone"] is True and out["voided_voucher_no"] == paid["voucher_no"]
    with org_bypass():
        je = _run(raw_db.finance_journal_entries.find_one({"id": paid["journal_entry_id"]}))
        exp = _run(raw_db.financial.find_one({"id": paid["expense_id"]}))
        req = _run(raw_db.approval_requests.find_one({"id": rid}, {"_id": 0}))
    assert je is None and exp is None
    md = req["metadata"]
    assert "expense_id" not in md and md["voucher_void"] is True
    assert md["payment_undone_reason"] == "Paid from the wrong account"
    # It can be paid again, properly.
    again = _run(funds.mark_paid(rid, {"paid_from_account_id": ACCTS["bank"]["id"],
                                       "expense_account_id": ACCTS["fees"]["id"]}, admin))
    assert again["voucher_no"] and again["expense_id"] != paid["expense_id"]


def test_only_finance_may_back_out_a_payment(paid_request):
    rid, _paid, _admin = paid_request
    with pytest.raises(Exception) as err:
        _run(funds.undo_payment(rid, {}, STAFF))
    assert "Only finance staff" in str(err.value)


def test_an_unpaid_request_cannot_be_unpaid(org):
    with org_bypass():
        _run(raw_db.approval_requests.insert_one({
            "id": f"areq_np_{TAG}", "subject_kind": "fund_request", "status": "approved",
            "amount": 1000, "currency": "UGX", "location_id": CAMPUS, "metadata": {"kind": "advance"}}))
    set_current_org(GLOBAL_ORG)
    with pytest.raises(Exception) as err:
        _run(funds.undo_payment(f"areq_np_{TAG}", {}, {**BOSS, "role": "system_admin"}))
    assert "hasn't been paid" in str(err.value)


# ------------------------------------------------- warning before it lapses
def test_directors_are_warned_once_before_a_permit_lapses(org):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=10)).isoformat()
    doc = _file_doc(title="ZT Fire certificate", level=5, expires=soon)
    set_current_org(GLOBAL_ORG)
    first = _run(od.warn_about_expiring_documents(days=30))
    assert first["warned"] >= 1
    with org_bypass():
        notif = _run(raw_db.notifications.find_one(
            {"message": {"$regex": "ZT Fire certificate"}}, {"_id": 0}))
        again = _run(od.warn_about_expiring_documents(days=30))
        stored = _run(raw_db.org_documents.find_one({"id": doc["id"]}, {"_id": 0}))
        _run(raw_db.notifications.delete_many({"message": {"$regex": "ZT Fire certificate"}}))
    assert notif and "expires in 10 days" in notif["message"]
    assert notif["target_role"] == "Director"
    assert stored["last_expiry_warning_step"] == 30
    assert again["warned"] == 0, "the same permit was warned about twice in one threshold"
