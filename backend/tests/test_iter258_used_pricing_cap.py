"""iter 258 — USED / secondhand pricing fix for AI item scanning.

Covers:
  1. `_estimate_value_usd` AI safety cap (thrift categories capped, regulated not)
  2. Prompt-string audit: admin_scan_item sys_msg + box-scan SYS_PROMPT contain
     USED / secondhand guidance
  3. Regression: /api/shipments/{id}/scan-boxes contract + admin_scan_item
     `condition` field presence
"""
import inspect
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ITEMS_SRC = Path("/app/backend/routers/shipments_pkg/items.py").read_text(encoding="utf-8")


# ── 1. Unit tests for _estimate_value_usd ────────────────────────────────
class TestEstimateValueCap:
    @staticmethod
    def _fn():
        from routers.shipments_pkg.items import _estimate_value_usd
        return _estimate_value_usd

    def test_clothing_high_ai_price_is_capped_to_15(self):
        assert self._fn()("Jacket", "clothing", 180.0) == 15.00

    def test_furniture_is_not_capped(self):
        assert self._fn()("Chair", "furniture", 150.0) == 150.00

    def test_already_low_clothing_price_passes_through(self):
        assert self._fn()("T-shirt", "clothing", 3.0) == 3.0

    def test_books_none_falls_back_to_preset(self):
        assert self._fn()("Book", "books", None) == 3.0

    def test_electronics_uncapped(self):
        assert self._fn()("Laptop", "electronics", 300.0) == 300.0

    def test_shoes_capped_at_18(self):
        # shoes low avg = 6.0 -> ceiling max(18, 15) = 18
        assert self._fn()("Nike sneakers", "shoes", 120.0) == 18.0

    def test_unknown_category_no_bucket_no_cap(self):
        assert self._fn()("Widget", "gizmo", 999.0) == 999.0

    def test_zero_and_negative_provided_fall_back(self):
        assert self._fn()("Shirt", "clothing", 0.0) == 4.0
        assert self._fn()("Shirt", "clothing", -5.0) == 4.0

    def test_no_match_default_five(self):
        assert self._fn()("Widget", "gizmo", None) == 5.0

    # iter 258b — category-first bucket resolution: furniture names containing
    # a thrift keyword must NOT be capped.
    def test_bookshelf_false_positive(self):
        assert self._fn()("Bookshelf", "furniture", 200.0) == 200.0

    def test_toy_box_furniture_not_capped(self):
        assert self._fn()("Toy box", "furniture", 120.0) == 120.0

    def test_kitchen_table_furniture_not_capped(self):
        assert self._fn()("Kitchen table", "furniture", 300.0) == 300.0

    def test_baby_bucket_still_capped(self):
        assert self._fn()("Baby stroller", "baby", 60.0) == 15.0

    def test_capped_categories_still_capped_after_fix(self):
        fn = self._fn()
        assert fn("Winter jacket", "clothing", 180.0) == 15.0
        assert fn("Paperback novel", "books", 40.0) == 15.0
        assert fn("Bed sheets", "linens", 90.0) == 15.0

    def test_furniture_bucket_fallback_when_no_value(self):
        assert self._fn()("Bookshelf", "furniture", None) == 30.0


# ── 2. Prompt-string audit ───────────────────────────────────────────────
class TestPromptsContainUsedPricingRule:
    def test_admin_scan_item_sys_msg(self):
        from routers.shipments_pkg.items import admin_scan_item
        src = inspect.getsource(admin_scan_item)
        assert "sys_msg = (" in src
        block = src.split("sys_msg = (", 1)[1].split("chat = LlmChat", 1)[0]
        assert "USED" in block, "admin sys_msg missing 'USED'"
        low = block.lower()
        assert "secondhand" in low or "thrift-store" in low
        assert "value_usd" in block

    def test_box_scan_sys_prompt(self):
        assert "SYS_PROMPT = (" in ITEMS_SRC
        block = ITEMS_SRC.split("SYS_PROMPT = (", 1)[1].split("for idx, img in enumerate", 1)[0]
        assert "USED" in block, "box-scan SYS_PROMPT missing 'USED'"
        low = block.lower()
        assert "secondhand" in low or "thrift-store" in low
        assert "estimated_value_usd" in block

    def test_admin_scan_persists_condition(self):
        from routers.shipments_pkg.items import admin_scan_item
        src = inspect.getsource(admin_scan_item)
        assert re.search(r'"condition":\s*\(parsed\.get\("condition"\)', src)


# ── 3. HTTP regression on the live preview backend ───────────────────────
SHIPMENT_ID = "sh_1091d195ee"


@pytest.fixture(scope="module")
def admin_client():
    creds_file = Path("/app/memory/test_credentials.md")
    if not creds_file.exists():
        pytest.skip("missing test_credentials.md")
    txt = creds_file.read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*[-*]?\s*\*\*Email\*\*\s*:\s*(\S+)', txt).group(1)
    pwd = re.search(r'(?im)^\s*[-*]?\s*\*\*Password\*\*\s*:\s*(\S+)', txt).group(1)
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"identifier": email, "password": pwd}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"no token in login response: {list(r.json().keys())}")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


class TestScanBoxesRegression:
    def test_shipment_exists(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/shipments/{SHIPMENT_ID}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("id") == SHIPMENT_ID

    def test_scan_boxes_requires_image(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/shipments/{SHIPMENT_ID}/scan-boxes", timeout=60)
        assert r.status_code == 422, f"expected validation error, got {r.status_code}"

    def test_scan_boxes_unknown_shipment_404(self, admin_client):
        files = {"images": ("a.jpg", b"\xff\xd8\xff\xdbnotanimage", "image/jpeg")}
        r = admin_client.post(f"{BASE_URL}/api/shipments/nope_xyz/scan-boxes", files=files, timeout=90)
        assert r.status_code in (404, 503), r.text[:300]

    def test_scan_boxes_unauth(self):
        files = {"images": ("a.jpg", b"\xff\xd8\xff\xdb", "image/jpeg")}
        r = requests.post(f"{BASE_URL}/api/shipments/{SHIPMENT_ID}/scan-boxes", files=files, timeout=60)
        assert r.status_code in (401, 403)

    def test_scan_boxes_contract_with_garbage_image(self, admin_client):
        """A non-decodable image should still return the documented envelope
        (results/errors/scan_run_id) rather than a 500."""
        files = {"images": ("junk.jpg", b"\x00" * 64, "image/jpeg")}
        r = admin_client.post(f"{BASE_URL}/api/shipments/{SHIPMENT_ID}/scan-boxes",
                              files=files, timeout=180)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        for k in ("scan_run_id", "results", "errors", "items_added", "items_linked",
                  "boxes_created", "boxes_matched"):
            assert k in d, f"missing {k} in scan-boxes response: {list(d.keys())}"
        assert isinstance(d["results"], list)
        # Undo whatever this created so the preview shipment stays clean
        if d.get("items_added") or d.get("boxes_created"):
            rv = admin_client.post(
                f"{BASE_URL}/api/shipments/{SHIPMENT_ID}/scan-runs/{d['scan_run_id']}/revert",
                timeout=60)
            assert rv.status_code == 200, rv.text[:300]

    def test_admin_scan_item_returns_condition(self, admin_client):
        files = {"images": ("junk.jpg", b"\x00" * 64, "image/jpeg")}
        r = admin_client.post(f"{BASE_URL}/api/shipments/{SHIPMENT_ID}/scan-item",
                              files=files, timeout=180)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert "name" in d and "category" in d and "value_usd" in d
        # condition present when AI identified the item; fallback shape omits it
        if d.get("ai_identified"):
            assert "condition" in d, f"condition missing from enriched: {list(d.keys())}"


# ── 4. End-to-end cap proof at the persistence layer ─────────────────────
class TestCapAppliedOnPersistedItem:
    def test_box_scan_row_value_is_capped_before_persist(self):
        """Mirror the exact call scan_boxes makes for a $180 clothing row."""
        from routers.shipments_pkg.items import _estimate_value_usd
        row = {"name": "Mens winter jacket", "qty": 1, "category": "clothing",
               "estimated_value_usd": 180}
        value = _estimate_value_usd(row["name"], row["category"], row.get("estimated_value_usd"))
        assert value <= 15.0, value

    def test_admin_scan_item_value_is_capped(self):
        """iter 258 follow-up: admin_scan_item must route the parsed AI
        value_usd through `_estimate_value_usd`."""
        from routers.shipments_pkg import items as mod
        src = inspect.getsource(mod.admin_scan_item)
        assert re.search(
            r'"value_usd"\s*:\s*_estimate_value_usd\(\s*_ai_name\s*,\s*_ai_cat\s*,\s*parsed\.get\("value_usd"\)\s*\)',
            src,
        ), ("admin_scan_item does not apply _estimate_value_usd(_ai_name, _ai_cat, "
            "parsed.get('value_usd')) — AI safety cap missing for admin AI Scan flow")
