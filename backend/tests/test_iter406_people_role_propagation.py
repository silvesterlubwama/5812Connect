# iter406: the role on the People page is the person's access level.
# Ticking "Admin" there used to change the member row only — it posted the
# MEMBER id to /admin/users/{id}, which always 404'd — so the new admin never
# saw any admin options. The server now carries role/status to the linked
# sign-in account, with the same escalation guard the admin console has.
import asyncio
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from fastapi import HTTPException  # noqa: E402
from deps import raw_db  # noqa: E402
from models import MemberUpdate  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers.members import core as core_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def person():
    """A member row with a linked sign-in account, both in the default org."""
    uid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    email = f"iter406-{uuid.uuid4().hex[:6]}@test.local"

    async def _mk():
        with org_bypass():
            await raw_db.users.insert_one({
                "id": uid, "email": email, "name": "Role Probe", "role": "Staff",
                "status": "active", "organization_id": GLOBAL_ORG,
            })
            await raw_db.members.insert_one({
                "id": mid, "email": email, "name": "Role Probe", "role": "Staff",
                "status": "active", "user_id": uid, "organization_id": GLOBAL_ORG,
            })
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield {"user_id": uid, "member_id": mid}

    async def _rm():
        with org_bypass():
            await raw_db.users.delete_many({"email": email})
            await raw_db.members.delete_many({"email": email})
    _run(_rm())


def _user_role(uid):
    with org_bypass():
        row = _run(raw_db.users.find_one({"id": uid}, {"_id": 0, "role": 1, "status": 1}))
    return row


def _admin():
    return {"id": "test-admin", "role": "admin", "organization_id": GLOBAL_ORG}


def test_admin_tick_in_people_reaches_the_signin_account(person):
    set_current_org(GLOBAL_ORG)
    _run(core_mod.update_member(person["member_id"], MemberUpdate(role="admin"), _admin()))
    assert _user_role(person["user_id"])["role"] == "admin"


def test_demoting_in_people_also_reaches_the_account(person):
    set_current_org(GLOBAL_ORG)
    _run(core_mod.update_member(person["member_id"], MemberUpdate(role="admin"), _admin()))
    _run(core_mod.update_member(person["member_id"], MemberUpdate(role="Coordinator"), _admin()))
    assert _user_role(person["user_id"])["role"] == "Coordinator"


def test_status_follows_the_person(person):
    set_current_org(GLOBAL_ORG)
    _run(core_mod.update_member(person["member_id"], MemberUpdate(status="suspended"), _admin()))
    assert _user_role(person["user_id"])["status"] == "suspended"


def test_a_manager_cannot_make_somebody_an_admin_from_people(person):
    set_current_org(GLOBAL_ORG)
    manager = {"id": "test-manager", "role": "Manager", "organization_id": GLOBAL_ORG}
    with pytest.raises(HTTPException) as e:
        _run(core_mod.update_member(person["member_id"], MemberUpdate(role="admin"), manager))
    assert e.value.status_code == 403
    assert _user_role(person["user_id"])["role"] == "Staff", "the account was escalated anyway"
    with org_bypass():
        row = _run(raw_db.members.find_one({"id": person["member_id"]}, {"_id": 0, "role": 1}))
    assert row["role"] == "Staff", "the member row was changed despite the refusal"


def test_an_unrelated_field_does_not_touch_the_account(person):
    set_current_org(GLOBAL_ORG)
    _run(core_mod.update_member(person["member_id"], MemberUpdate(phone="+256700000000"), _admin()))
    assert _user_role(person["user_id"])["role"] == "Staff"
