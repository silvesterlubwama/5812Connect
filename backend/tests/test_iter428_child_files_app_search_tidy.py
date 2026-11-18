# iter428: children's paperwork reaches the assistant (social work only), the
# rest of the application is searchable in one pass, and a manager can tidy the
# shelf from the chat.
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

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
TAG = uuid.uuid4().hex[:6]
CAMPUS = f"loc_z_{TAG}"
CHILD = f"child_{TAG}"
STAFF = {"id": f"usr_s_{TAG}", "role": "Staff", "name": "Esther", "email": f"es{TAG}@t.org",
         "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
SOCIAL = {"id": f"usr_w_{TAG}", "role": "Coordinator", "name": "Grace", "email": f"gr{TAG}@t.org",
          "organization_id": GLOBAL_ORG, "location_id": CAMPUS,
          "social_work_access": True}
MANAGER = {"id": f"usr_m_{TAG}", "role": "Manager", "name": "Peter", "email": f"pe{TAG}@t.org",
           "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
ADMIN = {"id": f"usr_a_{TAG}", "role": "system_admin", "name": "Root", "email": f"ro{TAG}@t.org",
         "organization_id": GLOBAL_ORG, "location_id": CAMPUS}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _upload(data: bytes, name: str, mime: str):
    return UploadFile(filename=name, file=io.BytesIO(data), headers=Headers({"content-type": mime}))


@pytest.fixture
def world(monkeypatch):
    async def _no_model(path, mime, extracted):
        return {}
    monkeypatch.setattr(od, "_read_with_model", _no_model)

    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_one({"id": CAMPUS, "name": "Hope Campus", "organization_id": GLOBAL_ORG})
            await raw_db.child_extras.insert_many([
                {"id": f"ce_lc1_{TAG}", "child_id": CHILD, "child_name": "ZW Amina Nakato",
                 "kind": "file_doc", "doc_type": "lc1_letter", "doc_label": "LC1 introduction letter",
                 "issued_date": "2026-02-10", "file_url": f"/api/uploads/child-file-docs/lc1_{TAG}.pdf",
                 "file_name": "lc1.pdf", "location_id": CAMPUS, "organization_id": GLOBAL_ORG,
                 "created_at": "2026-02-11T00:00:00+00:00"},
                {"id": f"ce_gid_{TAG}", "child_id": CHILD, "child_name": "ZW Amina Nakato",
                 "kind": "file_doc", "doc_type": "guardian_id", "doc_label": "Guardian national ID",
                 "file_url": f"/api/uploads/child-file-docs/gid_{TAG}.jpg", "file_name": "gid.jpg",
                 "location_id": CAMPUS, "organization_id": GLOBAL_ORG, "created_at": "2026-02-12T00:00:00+00:00"},
            ])
            await raw_db.children.insert_one({
                "id": CHILD, "name": "ZW Amina Nakato", "class_group": "P4", "is_sponsored": True,
                "location_id": CAMPUS, "organization_id": GLOBAL_ORG})
            await raw_db.social_cases.insert_one({
                "id": f"sc_{TAG}", "subject_id": CHILD, "subject_name": "ZW Amina Nakato",
                "category": "welfare_support", "status": "active", "risk_level": "medium",
                "location_id": CAMPUS, "organization_id": GLOBAL_ORG})
            await raw_db.events.insert_one({
                "id": f"evt_{TAG}", "title": "ZW Sponsor open day", "date": "2026-07-04",
                "start_time": "10:00", "location": "Hope Campus hall",
                "location_id": CAMPUS, "organization_id": GLOBAL_ORG})
            await raw_db.financial.insert_one({
                "id": f"fin_{TAG}", "type": "expense", "amount": 450000, "currency": "UGX",
                "description": "ZW Borehole repair", "category": "Maintenance", "date": "2026-06-02",
                "location_id": CAMPUS, "organization_id": GLOBAL_ORG})
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.child_extras.delete_many({"child_id": CHILD})
            await raw_db.children.delete_many({"id": CHILD})
            await raw_db.social_cases.delete_many({"id": f"sc_{TAG}"})
            await raw_db.events.delete_many({"id": f"evt_{TAG}"})
            await raw_db.financial.delete_many({"id": f"fin_{TAG}"})
            await raw_db.locations.delete_many({"id": CAMPUS})
            await raw_db.org_documents.delete_many({"uploaded_by": {"$in": [MANAGER["id"], ADMIN["id"]]}})
    _run(_rm())


def _file_doc(title, dtype="permit", size_text=b"x" * 50, user=MANAGER, level=5):
    set_current_org(GLOBAL_ORG)
    return _run(od.upload_document(file=_upload(size_text, "f.txt", "text/plain"), title=title, doc_type=dtype,
                                  min_level=level, expires_on=None, notes=None, current_user=user))


# ------------------------------------------------- children's paperwork
def test_social_work_finds_an_lc1_letter_on_a_childs_file(world):
    hits = _run(kb.search_child_files(SOCIAL, "where is Amina's LC1 letter?"))
    assert hits and "LC1 introduction letter" in hits[0]["title"]
    att = kb.attachment_of(hits[0])
    assert att["from_profile"] is True and att["has_file"] is True
    assert att["url"].endswith(f"lc1_{TAG}.pdf"), "the LC1 is served from where social work already keeps it"


def test_a_guardians_id_is_not_for_general_staff(world):
    assert _run(kb.search_child_files(STAFF, "show me the guardian national ID for Amina")) == []
    assert _run(kb.search_child_files(SOCIAL, "show me the guardian national ID for Amina"))


def test_an_admin_can_still_reach_a_childs_paperwork(world):
    assert _run(kb.search_child_files(ADMIN, "Amina guardian id document"))


def test_an_unrelated_question_pulls_no_child_files(world):
    assert _run(kb.search_child_files(SOCIAL, "how do I post an announcement?")) == []


# ------------------------------------------------- the rest of the application
def test_the_assistant_searches_the_whole_application(world):
    rows = _run(kb.search_app_records(SOCIAL, "ZW Amina Nakato"))
    blob = " ".join(rows)
    assert "[Child] ZW Amina Nakato" in blob
    assert "[Welfare case] ZW Amina Nakato" in blob


def test_events_and_stock_are_searchable_by_anyone_on_staff(world):
    rows = _run(kb.search_app_records(STAFF, "ZW Sponsor open day"))
    assert any(r.startswith("[Event]") and "2026-07-04" in r for r in rows)


def test_money_records_stay_out_of_a_staff_members_results(world):
    staff_rows = _run(kb.search_app_records(STAFF, "ZW Borehole repair"))
    assert not any("[Finance entry]" in r for r in staff_rows)
    admin_rows = _run(kb.search_app_records(ADMIN, "ZW Borehole repair"))
    assert any("[Finance entry]" in r and "450,000" in r for r in admin_rows)


def test_a_vague_question_does_not_dump_the_database(world):
    assert _run(kb.search_app_records(ADMIN, "what is it?")) == []


# ------------------------------------------------- tidying from the chat
def test_a_manager_is_told_what_is_on_file(world):
    _file_doc("ZW NGO permit")
    _file_doc("ZW Fire certificate", dtype="certificate")
    out = _run(kb.try_document_tidy(MANAGER, "what documents do we have on file?"))
    assert "ZW NGO permit" in out["facts"] and "ZW Fire certificate" in out["facts"]


def test_repeats_are_pointed_out_before_anything_is_touched(world):
    _file_doc("ZW NGO permit")
    _file_doc("ZW NGO permit")
    out = _run(kb.try_document_tidy(MANAGER, "are there any duplicate documents?"))
    assert "2 copies" in out["answer"]
    assert out.get("tidied") is None, "it tidied without being asked to"


def test_a_manager_clears_the_repeats_and_the_first_copy_stays(world):
    first = _file_doc("ZW NGO permit")
    second = _file_doc("ZW NGO permit")
    out = _run(kb.try_document_tidy(MANAGER, "clear out the duplicate documents"))
    assert out["tidied"] is True and second["id"] in out["removed"]
    with org_bypass():
        kept = _run(raw_db.org_documents.find_one({"id": first["id"]}, {"_id": 0}))
        gone = _run(raw_db.org_documents.find_one({"id": second["id"]}, {"_id": 0}))
    assert not kept.get("deleted")
    assert gone["deleted"] is True and gone["deleted_reason"].startswith("duplicate")
    assert gone["deleted_by_name"] == "Peter", "the audit trail lost who tidied"


def test_a_staff_member_can_see_repeats_but_not_clear_them(world):
    _file_doc("ZW NGO permit")
    _file_doc("ZW NGO permit")
    out = _run(kb.try_document_tidy(STAFF, "please delete the duplicate documents"))
    assert out.get("tidied") is None
    assert "A manager can ask me" in out["answer"]


def test_ordinary_chat_is_not_mistaken_for_tidying(world):
    assert _run(kb.try_document_tidy(MANAGER, "when does our permit expire?")) is None
