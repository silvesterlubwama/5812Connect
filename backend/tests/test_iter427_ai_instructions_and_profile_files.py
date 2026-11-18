# iter427: the assistant takes instructions — fix a document by saying so,
# remember a note or a link, list what expires, and reach the files already
# sitting on people's profiles (without leaking anyone else's ID).
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
from routers import documents as person_docs  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
TAG = uuid.uuid4().hex[:6]
CAMPUS = f"loc_q_{TAG}"
MEMBER_A = f"mem_a_{TAG}"
MEMBER_B = f"mem_b_{TAG}"
PORTAL_A = {"id": f"usr_pa_{TAG}", "role": "Member", "name": "Amina", "email": f"amina{TAG}@test.org",
            "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
STAFF = {"id": f"usr_s_{TAG}", "role": "Staff", "name": "Esther", "email": f"esther{TAG}@test.org",
         "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
MANAGER = {"id": f"usr_m_{TAG}", "role": "Manager", "name": "Peter", "email": f"peter{TAG}@test.org",
           "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
BOSS = {"id": f"usr_d_{TAG}", "role": "Director", "name": "Deborah", "email": f"deborah{TAG}@test.org",
        "organization_id": GLOBAL_ORG, "location_id": CAMPUS}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _upload(data: bytes, name: str, mime: str):
    return UploadFile(filename=name, file=io.BytesIO(data), headers=Headers({"content-type": mime}))


@pytest.fixture
def org(monkeypatch):
    async def _no_model(path, mime, extracted):
        return {}
    monkeypatch.setattr(od, "_read_with_model", _no_model)

    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_one({"id": CAMPUS, "name": "Hope Campus", "organization_id": GLOBAL_ORG})
            await raw_db.members.insert_many([
                {"id": MEMBER_A, "name": "Amina Q", "email": PORTAL_A["email"], "organization_id": GLOBAL_ORG},
                {"id": MEMBER_B, "name": "Brian Q", "email": f"brian{TAG}@test.org", "organization_id": GLOBAL_ORG},
            ])
            await raw_db.users.insert_many([{**u, "status": "active"} for u in (PORTAL_A, STAFF, MANAGER, BOSS)])
            await raw_db.files.insert_many([
                {"id": f"file_a_{TAG}", "member_id": MEMBER_A, "member_name": "Amina Q", "doc_type": "national_id",
                 "label": "National ID card", "local_path": f"uploads/{MEMBER_A}/id.txt", "content_type": "text/plain",
                 "is_deleted": False, "created_at": "2026-05-01T00:00:00+00:00", "organization_id": GLOBAL_ORG},
                {"id": f"file_b_{TAG}", "member_id": MEMBER_B, "member_name": "Brian Q", "doc_type": "contract",
                 "label": "Employment contract", "local_path": f"uploads/{MEMBER_B}/contract.txt",
                 "content_type": "text/plain", "is_deleted": False, "created_at": "2026-05-02T00:00:00+00:00",
                 "organization_id": GLOBAL_ORG},
            ])
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.org_documents.delete_many({"uploaded_by": {"$in": [MANAGER["id"], BOSS["id"], STAFF["id"]]}})
            await raw_db.locations.delete_many({"id": CAMPUS})
            await raw_db.members.delete_many({"id": {"$in": [MEMBER_A, MEMBER_B]}})
            await raw_db.users.delete_many({"id": {"$in": [u["id"] for u in (PORTAL_A, STAFF, MANAGER, BOSS)]}})
            await raw_db.files.delete_many({"id": {"$in": [f"file_a_{TAG}", f"file_b_{TAG}"]}})
    _run(_rm())


def _file_doc(title="ZQ NGO operating permit", level=5, expires="2027-03-31", dtype="permit",
              text=b"NGO OPERATING PERMIT valid until 2027-03-31"):
    set_current_org(GLOBAL_ORG)
    return _run(od.upload_document(file=_upload(text, "permit.txt", "text/plain"), title=title, doc_type=dtype,
                                  min_level=level, expires_on=expires, notes=None, current_user=MANAGER))


# ------------------------------------------------- fixing a document by saying so
def test_a_manager_changes_an_expiry_just_by_saying_it(org, monkeypatch):
    doc = _file_doc()

    async def _parse(self, msg):
        return '{"document_title": "ZQ NGO operating permit", "expires_on": "2028-03-31", "title": "", "min_level": 0, "doc_type": ""}'
    from emergentintegrations.llm.chat import LlmChat
    monkeypatch.setattr(LlmChat, "send_message", _parse)

    out = _run(kb.try_document_edit(MANAGER, "change the NGO permit expiry date to 31 March 2028"))
    assert out["edited"] is True and "2028-03-31" in out["answer"]
    with org_bypass():
        stored = _run(raw_db.org_documents.find_one({"id": doc["id"]}, {"_id": 0, "expires_on": 1}))
    assert stored["expires_on"] == "2028-03-31"


def test_a_manager_locks_a_document_down_by_saying_it(org, monkeypatch):
    doc = _file_doc(title="ZQ Head office lease", dtype="agreement", expires=None)

    async def _parse(self, msg):
        return '{"document_title": "ZQ Head office lease", "min_level": 8, "title": "", "expires_on": "", "doc_type": ""}'
    from emergentintegrations.llm.chat import LlmChat
    monkeypatch.setattr(LlmChat, "send_message", _parse)

    out = _run(kb.try_document_edit(BOSS, "only directors may see the head office lease"))
    assert "directors and above" in out["answer"].lower()
    # The staff member can no longer find it.
    assert not [h for h in _run(kb.search_documents(STAFF, "head office lease")) if h["id"] == doc["id"]]


def test_a_staff_member_cannot_quietly_rewrite_the_paperwork(org):
    _file_doc()
    assert _run(kb.try_document_edit(STAFF, "change the NGO permit expiry to 2030-01-01")) is None


def test_an_instruction_about_a_document_we_do_not_hold_says_so(org):
    out = _run(kb.try_document_edit(MANAGER, "change the fishing licence expiry to 2030-01-01"))
    assert "couldn't tell which document" in out["answer"]


# ------------------------------------------------- notes and links
def test_a_manager_can_just_tell_the_assistant_to_remember_something(org):
    out = _run(kb.try_knowledge_note(MANAGER, "Remember this: the NGO Bureau moved to Plot 12 Kyadondo Road"))
    assert out["noted"] is True
    hits = _run(kb.search_documents(STAFF, "where did the NGO Bureau move to?"))
    assert any("Plot 12" in (h.get("summary") or "") for h in hits)


def test_a_note_with_no_substance_is_queried_not_filed(org):
    out = _run(kb.try_knowledge_note(MANAGER, "remember this:"))
    assert "Tell me what to remember" in out["answer"]
    assert out.get("noted") is None


def test_an_unreachable_link_is_still_kept_with_the_note(org):
    out = _run(kb.try_knowledge_note(
        MANAGER, "Note this: renewal portal https://zq-not-a-real-host-8812.invalid/renew"))
    assert out["noted"] is True
    with org_bypass():
        stored = _run(raw_db.org_documents.find_one({"id": out["document"]["id"]}, {"_id": 0}))
    assert stored["source_url"].startswith("https://zq-not-a-real-host")
    assert "could not be read" in stored["text"]


def test_ordinary_staff_cannot_feed_the_knowledge_base(org):
    assert _run(kb.try_knowledge_note(STAFF, "remember this: we close at 4pm")) is None


# ------------------------------------------------- what is running out
def test_the_quarter_ahead_is_listed_from_the_records(org):
    from datetime import date, timedelta
    near = (date.today() + timedelta(days=40)).isoformat()
    far = (date.today() + timedelta(days=200)).isoformat()
    _file_doc(title="ZQ Fire certificate", expires=near, dtype="certificate")
    _file_doc(title="ZQ Vehicle licence", expires=far)
    out = _run(kb.expiry_rundown(STAFF, "which permits expire in the next quarter?"))
    assert "ZQ Fire certificate" in out["facts"]
    assert "ZQ Vehicle licence" not in out["facts"], "something 200 days out was called this quarter"
    assert "40 days left" in out["facts"]


def test_a_plain_question_is_not_treated_as_an_expiry_list(org):
    assert _run(kb.expiry_rundown(STAFF, "what is our NGO permit number?")) is None


def test_a_director_is_nudged_about_what_is_about_to_lapse(org):
    from datetime import date, timedelta
    _file_doc(title="ZQ Insurance cover", expires=(date.today() + timedelta(days=12)).isoformat())
    line = _run(kb.heads_up(BOSS))
    assert "ZQ Insurance cover" in line
    assert _run(kb.heads_up(STAFF)) == "", "staff should not get unprompted expiry nudges"


# ------------------------------------------------- files already on profiles
def test_the_assistant_finds_a_contract_sitting_on_a_profile(org):
    hits = _run(kb.search_person_files(MANAGER, "find Brian's employment contract"))
    assert hits and hits[0]["title"].startswith("Brian Q")
    att = kb.attachment_of(hits[0])
    assert att["url"] == f"/api/documents/file_b_{TAG}/file" and att["from_profile"] is True


def test_a_portal_member_only_ever_reaches_their_own_file(org):
    hits = _run(kb.search_person_files(PORTAL_A, "show me my national ID document"))
    assert [h["id"] for h in hits] == [f"file_a_{TAG}"]
    others = _run(kb.search_person_files(PORTAL_A, "Brian's employment contract document"))
    assert others == []


def test_another_members_id_cannot_be_pulled_by_guessing_the_link(org):
    with pytest.raises(Exception) as err:
        _run(person_docs.serve_document_file(f"file_b_{TAG}", PORTAL_A))
    assert "isn't yours" in str(err.value)
    with pytest.raises(Exception) as err:
        _run(person_docs.list_member_documents(MEMBER_B, PORTAL_A))
    assert "your own documents" in str(err.value)


def test_staff_may_still_open_a_members_document(org, monkeypatch):
    # Reaches the file-missing check, which means the permission gate let it through.
    with pytest.raises(Exception) as err:
        _run(person_docs.serve_document_file(f"file_b_{TAG}", MANAGER))
    assert "not found on disk" in str(err.value).lower()
