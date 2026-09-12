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
