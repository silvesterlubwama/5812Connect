# iter409: settings that actually save, and switches that actually do something.
import asyncio
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from fastapi import HTTPException  # noqa: E402
from deps import raw_db, db, get_access_settings, invalidate_access_settings, enforce_maintenance_mode  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import admin as admin_mod  # noqa: E402
from routers import system_settings as ss_mod  # noqa: E402
from routers import auth as auth_mod  # noqa: E402
from models import UserRegister  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "test-admin", "role": "admin", "organization_id": GLOBAL_ORG}


@pytest.fixture(autouse=True)
def _org():
    set_current_org(GLOBAL_ORG)
    yield
    # Leave maintenance off whatever the test did.
    _run(ss_mod.update_system_settings({"access": {"maintenance_mode": False, "registration_open": True}}, _admin()))
    invalidate_access_settings()


@pytest.fixture
def linked_person():
    """A user with a member row, the shape that broke the profile editor."""
    uid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    email = f"iter409-{uuid.uuid4().hex[:6]}@test.local"

    async def _mk():
        with org_bypass():
            await raw_db.users.insert_one({
                "id": uid, "email": email, "name": "Profile Probe", "role": "Coordinator",
                "status": "active", "organization_id": GLOBAL_ORG,
                "department": "Social Work", "department_ids": ["dept_abc"],
                "title": "Operations Manager", "extension": "1234", "badge_id": "BADGE-1",
                "notes": "keep me", "is_parent": True,
            })
            await raw_db.members.insert_one({
                "id": mid, "email": email, "name": "Profile Probe", "role": "Coordinator",
                "status": "active", "user_id": uid, "organization_id": GLOBAL_ORG,
                "gender": "male", "date_of_birth": "1990-01-01",
            })
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield {"user_id": uid, "member_id": mid}

    async def _rm():
        with org_bypass():
            await raw_db.users.delete_many({"email": email})
            await raw_db.members.delete_many({"email": email})
    _run(_rm())


def test_the_profile_editor_sees_the_account_fields(linked_person):
    """These live only on the sign-in account. The merge used to prefer the
    member row for all of them, so they opened blank and saving wrote the
    blanks back — the "I changed it and it didn't save" report."""
    p = _run(admin_mod.get_user_full_profile(linked_person["user_id"], _admin()))
    assert p["department_ids"] == ["dept_abc"]
    assert p["title"] == "Operations Manager"
    assert p["extension"] == "1234"
    assert p["badge_id"] == "BADGE-1"
    assert p["notes"] == "keep me"
    assert p["is_parent"] is True


def test_the_profile_editor_still_fills_gaps_from_the_member_row(linked_person):
    p = _run(admin_mod.get_user_full_profile(linked_person["user_id"], _admin()))
    assert p["gender"] == "male"
    assert p["date_of_birth"] == "1990-01-01"
    assert p["member_id"] == linked_person["member_id"]
    assert p["id"] == linked_person["user_id"], "must stay the ACCOUNT id"


def test_a_department_change_saves(linked_person):
    set_current_org(GLOBAL_ORG)
    _run(admin_mod.admin_update_user(
        linked_person["user_id"], {"department_ids": ["dept_abc", "dept_xyz"], "department": "Social Work"}, _admin()))
    p = _run(admin_mod.get_user_full_profile(linked_person["user_id"], _admin()))
    assert p["department_ids"] == ["dept_abc", "dept_xyz"]


def test_notification_preferences_belong_to_the_person():
    from routers import settings as settings_mod
    me = {"id": f"iter409-{uuid.uuid4().hex[:6]}", "role": "Member", "organization_id": GLOBAL_ORG}
    prefs = {"emailCheckins": False, "smsEvents": True}
    _run(settings_mod.update_app_settings({"notifications": prefs}, me))
    got = _run(settings_mod.get_app_settings(me))
    assert got["notifications"] == prefs
    _run(db.app_settings.delete_many({"user_id": me["id"]}))


def test_maintenance_mode_locks_out_everyone_below_admin():
    _run(ss_mod.update_system_settings(
        {"access": {"maintenance_mode": True, "maintenance_message": "Back by 3pm"}}, _admin()))
    invalidate_access_settings()
    assert _run(get_access_settings(GLOBAL_ORG))["maintenance_mode"] is True
    staff = {"id": "x", "role": "Coordinator", "organization_id": GLOBAL_ORG}
    with pytest.raises(HTTPException) as e:
        _run(enforce_maintenance_mode(staff))
    assert e.value.status_code == 503
    assert e.value.detail == "Back by 3pm"


def test_an_admin_still_gets_in_during_maintenance():
    _run(ss_mod.update_system_settings({"access": {"maintenance_mode": True}}, _admin()))
    invalidate_access_settings()
    _run(enforce_maintenance_mode(_admin()))   # must not raise


def test_closing_registration_refuses_new_requests():
    _run(ss_mod.update_system_settings({"access": {"registration_open": False}}, _admin()))
    invalidate_access_settings()
    data = UserRegister(name="Nope", email=f"iter409-{uuid.uuid4().hex[:6]}@test.local", password="Test@5812!")
    with pytest.raises(HTTPException) as e:
        _run(auth_mod.register(data))
    assert e.value.status_code == 403
    assert "closed" in e.value.detail.lower()


def test_the_default_role_is_used_for_a_new_request():
    _run(ss_mod.update_system_settings({"access": {"registration_open": True, "default_role": "Member"}}, _admin()))
    invalidate_access_settings()
    email = f"iter409-{uuid.uuid4().hex[:6]}@test.local"
    try:
        out = _run(auth_mod.register(UserRegister(name="New Person", email=email, password="Test@5812!")))
        assert out["user"]["role"] == "Member"
        assert out["user"]["status"] == "pending", "requests must still need approval"
    finally:
        with org_bypass():
            _run(raw_db.users.delete_many({"email": email}))
        _run(ss_mod.update_system_settings({"access": {"default_role": "Guest"}}, _admin()))
        invalidate_access_settings()
