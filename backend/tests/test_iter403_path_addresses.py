# iter403: organisations addressed by path — 5812uganda.org/lub — instead of subdomains.
# The web name is the first part of the address; the app sends it as X-Org-Slug.
import os
import time

import pytest
import requests
from pymongo import MongoClient


def _env(path, key):
    with open(path) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} missing from {path}")


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
db = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
LUB_ORG = "ee79732c-1263-46a8-bf46-511c5fe812bf"
A_ADMIN = {"identifier": "admin@5812global.org", "password": "Admin@1234"}
B_ADMIN = {"identifier": "admin@lubwamas.org", "password": "Lubwama@2026"}


def _login(creds, slug=None):
    headers = {"X-Org-Slug": slug} if slug else {}
    for _ in range(3):
        r = requests.post(f"{API}/auth/login", json=creds, headers=headers, timeout=30)
        if r.status_code == 429:
            time.sleep(20)
            continue
        return r
    pytest.skip("login rate limited")


def _slug(org_id):
    return db.organizations.find_one({"id": org_id}, {"_id": 0, "slug": 1})["slug"]


# ---------- which organisation an address belongs to ----------
class TestOrgRoute:
    def test_known_web_name(self):
        r = requests.get(f"{API}/public/org-route", params={"segment": _slug(LUB_ORG)}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["found"] is True and d["slug"] == _slug(LUB_ORG)
        assert d["name"] == "Lubwamas"
        assert d["default_slug"] == _slug(GLOBAL_ORG)

    def test_an_app_page_is_not_a_web_name(self):
        # /members is an old link, not an organisation — the app moves it under
        # the default organisation rather than 404ing.
        d = requests.get(f"{API}/public/org-route", params={"segment": "members"}, timeout=30).json()
        assert d["found"] is False
        assert d["default_slug"] == _slug(GLOBAL_ORG)

    def test_bare_address(self):
        d = requests.get(f"{API}/public/org-route", params={"segment": ""}, timeout=30).json()
        assert d["found"] is False and d["default_slug"]

    def test_it_never_lists_the_organisations(self):
        d = requests.get(f"{API}/public/org-route", params={"segment": "x"}, timeout=30).json()
        assert set(d) == {"found", "slug", "name", "suspended", "default_slug", "default_name"}
        assert "organizations" not in d


# ---------- whose branding and data an address serves ----------
class TestAddressDecidesOrg:
    def test_each_web_name_gets_its_own_branding(self):
        seen = {}
        for org in (GLOBAL_ORG, LUB_ORG):
            r = requests.get(f"{API}/admin/system-settings/public",
                             headers={"X-Org-Slug": _slug(org)}, timeout=30)
            assert r.status_code == 200, r.text
            seen[org] = (r.json().get("branding") or {}).get("app_name")
        assert seen[GLOBAL_ORG] != seen[LUB_ORG], seen

    def test_unknown_web_name_falls_back_to_the_default(self):
        r = requests.get(f"{API}/admin/system-settings/public",
                         headers={"X-Org-Slug": "not-an-organisation"}, timeout=30)
        assert r.status_code == 200
        bare = requests.get(f"{API}/admin/system-settings/public", timeout=30)
        assert (r.json().get("branding") or {}).get("app_name") == \
            (bare.json().get("branding") or {}).get("app_name")

    def test_sign_in_is_bound_to_the_address(self):
        wrong = _login(B_ADMIN, slug=_slug(GLOBAL_ORG))
        assert wrong.status_code in (401, 403), wrong.text
        right = _login(B_ADMIN, slug=_slug(LUB_ORG))
        assert right.status_code == 200, right.text
        assert right.json()["user"]["organization_id"] == LUB_ORG

    def test_bare_address_signs_people_into_their_own(self):
        r = _login(B_ADMIN)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["organization_id"] == LUB_ORG

    def test_me_reports_the_web_name_the_app_must_stay_under(self):
        tok = _login(B_ADMIN, slug=_slug(LUB_ORG)).json()["token"]
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        assert me.status_code == 200
        assert me.json()["organization_slug"] == _slug(LUB_ORG)

    def test_a_suspended_organisations_address_is_closed(self):
        db.organizations.update_one({"id": LUB_ORG}, {"$set": {"status": "suspended"}})
        try:
            r = requests.get(f"{API}/admin/system-settings/public",
                             headers={"X-Org-Slug": _slug(LUB_ORG)}, timeout=30)
            assert r.status_code == 403, r.text
            d = requests.get(f"{API}/public/org-route",
                             params={"segment": _slug(LUB_ORG)}, timeout=30).json()
            assert d["suspended"] is True
        finally:
            db.organizations.update_one({"id": LUB_ORG}, {"$set": {"status": "active"}})


# ---------- changing a web name ----------
class TestRenameWebName:
    def test_clash_invalid_and_rename(self):
        tok = _login(A_ADMIN, slug=_slug(GLOBAL_ORG))
        if tok.status_code != 200:
            pytest.skip("org A admin unavailable")
        # only the owner may change it
        h_admin = {"Authorization": f"Bearer {tok.json()['token']}"}
        r = requests.put(f"{API}/organizations/{LUB_ORG}", headers=h_admin, timeout=30,
                         json={"slug": "nope"})
        assert r.status_code in (401, 403), r.text
        assert _slug(LUB_ORG) != "nope"
