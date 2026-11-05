# iter408: the Staff tab on the People page saves straight to the sign-in
# account, so the account endpoint must stop mangling things it was not asked
# to change, and the staff list must not hide org-wide admins.
import asyncio
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import admin as admin_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _caller(**over):
    return {"id": "test-admin", "role": "admin", "organization_id": GLOBAL_ORG, **over}


@pytest.fixture
def account():
    uid = str(uuid.uuid4())
    email = f"iter408-{uuid.uuid4().hex[:6]}@test.local"

    async def _mk():
        with org_bypass():
            await raw_db.users.insert_one({
                "id": uid, "email": email, "name": "Title Probe", "role": "Manager",
                "title": "Operations Manager", "status": "active", "secondary_roles": ["HR"],
                "organization_id": GLOBAL_ORG, "updated_at": "2020-01-01T00:00:00+00:00",
            })
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield uid

    async def _rm():
        with org_bypass():
            await raw_db.users.delete_many({"email": email})
    _run(_rm())


def _row(uid):
    with org_bypass():
        return _run(raw_db.users.find_one({"id": uid}, {"_id": 0}))


def test_toggling_active_keeps_the_custom_title(account):
    set_current_org(GLOBAL_ORG)
    _run(admin_mod.admin_update_user(account, {"status": "suspended"}, _caller()))
    row = _row(account)
    assert row["status"] == "suspended"
    assert row["title"] == "Operations Manager", "a status change rewrote the title"


def test_an_admin_grant_titles_them_by_their_job_not_by_admin(account):
    set_current_org(GLOBAL_ORG)
    _run(admin_mod.admin_update_user(
        account, {"role": "admin", "secondary_roles": ["Manager", "HR"]}, _caller()))
    row = _row(account)
    assert row["role"] == "admin"
    assert "admin" not in (row["title"] or "").lower(), f"title became {row['title']!r}"
    assert "Manager" in (row["title"] or "")


def test_other_secondary_roles_survive_an_admin_grant(account):
    set_current_org(GLOBAL_ORG)
    _run(admin_mod.admin_update_user(
        account, {"role": "admin", "secondary_roles": ["Manager", "HR"]}, _caller()))
    assert _row(account)["secondary_roles"] == ["Manager", "HR"]


def test_every_save_stamps_updated_at(account):
    set_current_org(GLOBAL_ORG)
    _run(admin_mod.admin_update_user(account, {"status": "active"}, _caller()))
    assert _row(account)["updated_at"] != "2020-01-01T00:00:00+00:00"


def test_an_org_wide_admin_is_not_hidden_by_a_pinned_campus(account):
    """The signed-in admin's own account has no campus; pinning one used to
    drop every such account from the staff list."""
    set_current_org(GLOBAL_ORG)
    locs = _run(raw_db.locations.find({}, {"_id": 0, "id": 1}).to_list(5))
    if not locs:
        pytest.skip("no campuses configured")
    caller = _caller(active_campus_id=locs[0]["id"], location_id=locs[0]["id"])
    users = _run(admin_mod.list_all_users(None, None, None, caller))
    assert account in [u["id"] for u in users], "the campus-less account was hidden"
