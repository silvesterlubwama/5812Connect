"""Shared test fixtures — credentials resolved from the environment.

No login strings live in the repo: see `tests/creds.py`, which reads
`TEST_ADMIN_*` from `backend/.env` (or the shell).
"""
import pytest

import creds

TEST_ADMIN_EMAIL = creds.ADMIN_EMAIL
TEST_ADMIN_PASSWORD = creds.ADMIN_PASSWORD
TEST_API_URL = creds.BASE_URL


@pytest.fixture
def admin_credentials():
    return {"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD}


@pytest.fixture
def api_url():
    return TEST_API_URL


# ---------------------------------------------------------------------------
# iter392 — organisation stamping for tests that seed Mongo directly.
#
# Application writes are stamped with the tenant automatically by the scoped db
# proxy. Tests that bypass the API and insert straight into Mongo would produce
# rows belonging to nobody, which the API then (correctly) refuses to see. This
# stamps direct inserts with the default organisation so fixtures behave like
# real data.
# ---------------------------------------------------------------------------
import os as _os

import pymongo.collection as _pc
from pymongo import MongoClient as _MC

_UNSCOPED = {
    "organizations", "org_audit_log", "counters", "app_config", "cron_runs",
    "public_endpoint_hits", "login_attempts", "sessions", "password_reset_tokens",
}
_DEFAULT_ORG = None


def _default_org_id():
    global _DEFAULT_ORG
    if _DEFAULT_ORG is None:
        c = _MC(_os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        d = c[_os.environ.get("DB_NAME", "5812global")]
        doc = d.organizations.find_one({"is_default": True}) or d.organizations.find_one({})
        _DEFAULT_ORG = (doc or {}).get("id", "")
        c.close()
    return _DEFAULT_ORG


_orig_insert_one = _pc.Collection.insert_one
_orig_insert_many = _pc.Collection.insert_many


def _stamped_insert_one(self, document, *a, **kw):
    if self.name not in _UNSCOPED and isinstance(document, dict):
        document.setdefault("organization_id", _default_org_id())
    return _orig_insert_one(self, document, *a, **kw)


def _stamped_insert_many(self, documents, *a, **kw):
    if self.name not in _UNSCOPED:
        documents = [
            ({**d, "organization_id": d.get("organization_id") or _default_org_id()}
             if isinstance(d, dict) else d)
            for d in documents
        ]
    return _orig_insert_many(self, documents, *a, **kw)


_pc.Collection.insert_one = _stamped_insert_one
_pc.Collection.insert_many = _stamped_insert_many
