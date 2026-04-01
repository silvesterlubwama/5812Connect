"""Shared test fixtures — credentials from environment or defaults"""
import os
import pytest

TEST_ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@5812uganda.org")
TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@5812")
TEST_API_URL = os.environ.get("TEST_API_URL", "http://localhost:8001")

@pytest.fixture
def admin_credentials():
    return {"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD}

@pytest.fixture
def api_url():
    return TEST_API_URL
