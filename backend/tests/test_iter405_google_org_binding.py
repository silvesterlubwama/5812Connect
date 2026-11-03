# iter405: signing in with Google must never cut someone off from the
# organisation they already belong to.
#
# Google sent people back to the bare domain, so the exchange ran against the
# DEFAULT organisation. A Lubwamas person was not found there and was handed a
# brand-new pending guest account instead of their own — "disassociated".
import asyncio
import sys
import uuid

import pytest
from starlette.requests import Request

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

import httpx  # noqa: E402
from deps import raw_db  # noqa: E402
from org_context import org_bypass  # noqa: E402
from routers import auth as auth_mod  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
LUB_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"


def _request(slug: str) -> Request:
    headers = [(b"host", b"testserver")]
    if slug:
        headers.append((b"x-org-slug", slug.encode()))
    return Request({
        "type": "http", "http_version": "1.1", "method": "POST", "scheme": "https",
        "path": "/api/auth/google-session", "raw_path": b"/api/auth/google-session",
        "query_string": b"", "headers": headers, "server": ("testserver", 443),
        "client": ("1.2.3.4", 1234), "app": None,
    })


class _FakeResponse:
    status_code = 200

    def __init__(self, email, name):
        self._d = {"email": email, "name": name, "picture": ""}

    def json(self):
        return self._d


class _FakeClient:
    def __init__(self, email, name):
        self._email, self._name = email, name

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **kw):
        return _FakeResponse(self._email, self._name)


@pytest.fixture
def lub_person():
    email = f"google-probe-{uuid.uuid4().hex[:6]}@test.local"
    uid = str(uuid.uuid4())
    async def _mk():
        with org_bypass():
            await raw_db.users.insert_one({
                "id": uid, "email": email, "name": "Google Probe",
                "role": "Member", "status": "active", "organization_id": LUB_ORG,
            })
    asyncio.get_event_loop().run_until_complete(_mk())
    yield {"id": uid, "email": email}
    async def _rm():
        with org_bypass():
            await raw_db.users.delete_many({"email": email})
            await raw_db.guests.delete_many({"email": email})
    asyncio.get_event_loop().run_until_complete(_rm())


def _google(email, name, slug, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeClient(email, name))
    return asyncio.get_event_loop().run_until_complete(
        auth_mod.google_auth_session({"session_id": "probe"}, _request(slug))
    )


def test_their_own_organisations_address_signs_them_in(lub_person, monkeypatch):
    out = _google(lub_person["email"], "Google Probe", "lubwamas", monkeypatch)
    assert out["user"]["id"] == lub_person["id"], "a different account was returned"
    assert out["user"]["organization_id"] == LUB_ORG
    with org_bypass():
        rows = asyncio.get_event_loop().run_until_complete(
            raw_db.users.find({"email": lub_person["email"]}, {"_id": 0, "id": 1}).to_list(5))
    assert len(rows) == 1, f"a second account was created: {rows}"


def test_another_organisations_address_is_refused_not_duplicated(lub_person, monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _google(lub_person["email"], "Google Probe", "5812global", monkeypatch)
    assert e.value.status_code == 409, e.value.detail
    assert "Lubwamas" in e.value.detail
    # and crucially: no new account, so they are still in their own organisation
    with org_bypass():
        rows = asyncio.get_event_loop().run_until_complete(
            raw_db.users.find({"email": lub_person["email"]}, {"_id": 0, "organization_id": 1}).to_list(5))
    assert [r["organization_id"] for r in rows] == [LUB_ORG], rows


def test_the_bare_address_still_finds_their_own_account(lub_person, monkeypatch):
    out = _google(lub_person["email"], "Google Probe", "", monkeypatch)
    assert out["user"]["id"] == lub_person["id"]
    assert out["user"]["organization_id"] == LUB_ORG


def test_a_genuinely_new_person_is_still_welcomed(monkeypatch):
    email = f"google-new-{uuid.uuid4().hex[:6]}@test.local"
    try:
        out = _google(email, "Brand New", "lubwamas", monkeypatch)
        assert out.get("pending_approval") is True
        assert out["user"]["organization_id"] == LUB_ORG, out["user"]
    finally:
        async def _rm():
            with org_bypass():
                await raw_db.users.delete_many({"email": email})
                await raw_db.guests.delete_many({"email": email})
        asyncio.get_event_loop().run_until_complete(_rm())
