"""Test credentials — resolved from the environment, never hardcoded.

Every test account password now comes from `backend/.env` (or the shell), so
the repo carries no login strings. Override per-environment with:

    TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD,
    TEST_NEW_USER_PASSWORD, TEST_CUSTOM_PASSWORD, TEST_RESET_PASSWORD

`TEST_NEW_USER_PASSWORD` / `TEST_CUSTOM_PASSWORD` / `TEST_RESET_PASSWORD` are
deliberately distinct: several tests assert that a user created WITH a custom
password cannot log in with the default one, so re-using a single value would
make those assertions pass for the wrong reason.

The dev-seed values live in /app/memory/test_credentials.md.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")
NEW_USER_PASSWORD = os.environ.get("TEST_NEW_USER_PASSWORD", "")
CUSTOM_PASSWORD = os.environ.get("TEST_CUSTOM_PASSWORD", "")
RESET_PASSWORD = os.environ.get("TEST_RESET_PASSWORD", "")

BASE_URL = (
    os.environ.get("TEST_API_URL")
    or os.environ.get("REACT_APP_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")


def require(*names: str) -> None:
    """Skip the calling test module when a credential isn't configured."""
    import pytest

    missing = [n for n in names if not globals().get(n)]
    if missing:
        pytest.skip(f"Test credentials not configured: {', '.join(missing)}")
