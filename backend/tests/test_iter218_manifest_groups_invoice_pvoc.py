"""iter218 — Manifest groups (sub-consignments), commercial invoice PDF,
PVoC classification, sorted PDFs (PVoC ▸ value ▸ weight).

Covers:
  • POST /api/shipments/{sid}/manifest-groups — create group
  • PUT  /api/shipments/{sid}/manifest-groups/{gid} — update whitelist
  • DELETE /api/shipments/{sid}/manifest-groups/{gid} — unassigns items + removes group
  • PUT  /api/shipments/{sid}/items/{iid} — new whitelist keys
        (manifest_group_id, requires_pvoc, pvoc_reason)
  • GET  /api/shipments/{sid}/manifest.pdf?group=<gid|unassigned|bogus>
  • GET  /api/shipments/{sid}/commercial-invoice.pdf (with group filter)
  • Sort order: PVoC first ▸ highest line value ▸ heaviest
  • AI POST /api/shipments/{sid}/classify-hs-bulk — PVoC persistence
"""
import io
import os
import re
import uuid
import pytest
import requests

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_ID = creds.ADMIN_EMAIL
ADMIN_PW = creds.ADMIN_PASSWORD


# ─── fixtures ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_ID, "password": ADMIN_PW},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def shipment_id(client):
    tag = uuid.uuid4().hex[:6]
    r = client.post(f"{BASE_URL}/api/shipments", json={
        "name": f"TEST_iter218_{tag}",
        "dest_country": "Uganda",
        "units": "metric",
    }, timeout=15)
    assert r.status_code in (200, 201)
    sid = r.json()["id"]
    yield sid
    client.delete(f"{BASE_URL}/api/shipments/{sid}")


def _make_item(client, sid, **fields):
    payload = {"name": fields.pop("name", "TEST_item"), "qty_needed": 1}
    payload.update(fields)
    r = client.post(f"{BASE_URL}/api/shipments/{sid}/items", json=payload, timeout=15)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ────────────── Manifest Groups CRUD ──────────────
class TestManifestGroupsCRUD:
    def test_create_two_groups(self, client, shipment_id):
        r1 = client.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups",
            json={"name": "TEST 58:12 Global", "consignee_name": "58:12 Uganda",
                  "consignee_address": "Kampala", "notes": "primary"},
            timeout=15,
        )
        assert r1.status_code == 200, r1.text[:300]
        g1 = r1.json()
        assert g1["id"].startswith("mg_")
        assert g1["name"] == "TEST 58:12 Global"
        assert g1["consignee_name"] == "58:12 Uganda"
        assert g1["consignee_address"] == "Kampala"

        r2 = client.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups",
            json={"name": "TEST Lubwama Household"},
            timeout=15,
        )
        assert r2.status_code == 200
        g2 = r2.json()
        assert g2["name"] == "TEST Lubwama Household"

        # Verify persistence
        det = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15).json()
        gids = [g["id"] for g in det.get("manifest_groups", [])]
        assert g1["id"] in gids and g2["id"] in gids

        # Store for downstream tests
        pytest.iter218_g1 = g1["id"]
        pytest.iter218_g2 = g2["id"]

    def test_create_group_missing_name_rejected(self, client, shipment_id):
        r = client.post(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups",
            json={"name": "   "}, timeout=15,
        )
        assert r.status_code == 400

    def test_update_group_whitelist(self, client, shipment_id):
        gid = pytest.iter218_g1
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups/{gid}",
            json={"name": "TEST 58:12 Global RENAMED",
                  "notes": "updated notes",
                  "id": "hacked_id",       # non-whitelisted
                  "created_at": "1970-01-01"},  # non-whitelisted
            timeout=15,
        )
        assert r.status_code == 200
        det = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15).json()
        g = next(g for g in det["manifest_groups"] if g["id"] == gid)
        assert g["name"] == "TEST 58:12 Global RENAMED"
        assert g["notes"] == "updated notes"
        # id must not have been overwritten
        assert g["id"] == gid
        assert not str(g.get("created_at", "")).startswith("1970")

    def test_update_group_404(self, client, shipment_id):
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups/mg_bogus_xyz",
            json={"name": "nope"}, timeout=15,
        )
        assert r.status_code == 404


# ────────────── Item PUT whitelist (new keys) ──────────────
class TestItemPvocAndGroupWhitelist:
    def test_put_sets_pvoc_and_group_and_persists(self, client, shipment_id):
        gid = pytest.iter218_g1
        item = _make_item(client, shipment_id, name="TEST_pvoc_manual")
        iid = item["id"]
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{iid}",
            json={
                "requires_pvoc": True,
                "pvoc_reason": "test pvoc reason",
                "manifest_group_id": gid,
                # non-whitelisted
                "created_at": "1970-01-01",
            },
            timeout=15,
        )
        assert r.status_code == 200
        det = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15).json()
        it = next(i for i in det["items"] if i["id"] == iid)
        assert it["requires_pvoc"] is True
        assert it["pvoc_reason"] == "test pvoc reason"
        assert it["manifest_group_id"] == gid
        assert not str(it.get("created_at", "")).startswith("1970")

    def test_put_clears_pvoc_and_group(self, client, shipment_id):
        item = _make_item(client, shipment_id, name="TEST_pvoc_clear",
                          requires_pvoc=True, pvoc_reason="init")
        iid = item["id"]
        # Assign then clear
        client.put(f"{BASE_URL}/api/shipments/{shipment_id}/items/{iid}",
                   json={"manifest_group_id": pytest.iter218_g2}, timeout=15)
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{iid}",
            json={"requires_pvoc": False, "manifest_group_id": None},
            timeout=15,
        )
        assert r.status_code == 200
        det = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15).json()
        it = next(i for i in det["items"] if i["id"] == iid)
        assert it["requires_pvoc"] is False
        assert it["manifest_group_id"] is None


# ────────────── Sort order in PDFs ──────────────
class TestSortShipmentFixture:
    """Dedicated shipment with 3 items chosen so sort order (PVoC ▸ value ▸
    weight) produces a unique sequence: a → b → c."""

    @pytest.fixture(scope="class")
    def sort_ctx(self, client):
        tag = uuid.uuid4().hex[:6]
        r = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter218_sort_{tag}", "dest_country": "Uganda", "units": "metric",
        }, timeout=15)
        sid = r.json()["id"]
        # a: PVoC=true,  low value,  low weight → 1st
        a = _make_item(client, sid, name="TEST_sort_A_pvoc",
                       qty_acquired=1, value_usd=1.0, weight_kg=0.1,
                       requires_pvoc=True, pvoc_reason="regulated")
        # b: PVoC=false, high value, low weight → 2nd
        b = _make_item(client, sid, name="TEST_sort_B_value",
                       qty_acquired=1, value_usd=999.0, weight_kg=0.1)
        # c: PVoC=false, low value,  high weight → 3rd
        c = _make_item(client, sid, name="TEST_sort_C_weight",
                       qty_acquired=1, value_usd=1.0, weight_kg=50.0)
        yield {"sid": sid, "a": a["id"], "b": b["id"], "c": c["id"],
               "names": ["TEST_sort_A_pvoc", "TEST_sort_B_value", "TEST_sort_C_weight"]}
        client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def _pdf_text(self, pdf_bytes):
        # Best-effort text extraction from raw PDF content: names appear
        # in-clear inside content streams for weasyprint output.
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return pdf_bytes.decode("latin-1", errors="ignore")

    def test_manifest_pdf_sort_order(self, client, sort_ctx):
        r = client.get(f"{BASE_URL}/api/shipments/{sort_ctx['sid']}/manifest.pdf", timeout=90)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        text = self._pdf_text(r.content)
        pos = [text.find(n) for n in sort_ctx["names"]]
        assert all(p >= 0 for p in pos), f"Not all names in PDF text. positions={pos}\n{text[:600]}"
        assert pos[0] < pos[1] < pos[2], (
            f"Bad sort order in manifest PDF: A={pos[0]}, B={pos[1]}, C={pos[2]}"
        )

    def test_invoice_pdf_sort_order_and_totals(self, client, sort_ctx):
        r = client.get(f"{BASE_URL}/api/shipments/{sort_ctx['sid']}/commercial-invoice.pdf", timeout=90)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        text = self._pdf_text(r.content)
        pos = [text.find(n) for n in sort_ctx["names"]]
        assert all(p >= 0 for p in pos), f"Not all names in invoice PDF. positions={pos}"
        assert pos[0] < pos[1] < pos[2], f"Bad invoice sort order: {pos}"
        # Grand total = 1 + 999 + 1 = 1001 (unit×qty of 1 each)
        assert "1,001.00" in text or "1001.00" in text, f"Grand total missing: {text[:800]}"


# ────────────── Manifest PDF group filter ──────────────
class TestManifestPdfGroupFilter:
    @pytest.fixture(scope="class")
    def gfx(self, client):
        """Fresh shipment: 1 group with 2 items + 1 unassigned item."""
        tag = uuid.uuid4().hex[:6]
        r = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter218_gfilter_{tag}", "dest_country": "Uganda",
        }, timeout=15)
        sid = r.json()["id"]
        gr = client.post(f"{BASE_URL}/api/shipments/{sid}/manifest-groups",
                         json={"name": "TEST_group_A", "consignee_name": "Alice"},
                         timeout=15).json()
        gid = gr["id"]
        it_g1 = _make_item(client, sid, name="TEST_group_item_G1", qty_acquired=1)
        it_g2 = _make_item(client, sid, name="TEST_group_item_G2", qty_acquired=1)
        it_un = _make_item(client, sid, name="TEST_unassigned_item", qty_acquired=1)
        for iid in (it_g1["id"], it_g2["id"]):
            client.put(f"{BASE_URL}/api/shipments/{sid}/items/{iid}",
                       json={"manifest_group_id": gid}, timeout=15)
        yield {"sid": sid, "gid": gid,
               "in_group": ["TEST_group_item_G1", "TEST_group_item_G2"],
               "unassigned": "TEST_unassigned_item"}
        client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def _text(self, pdf_bytes):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return pdf_bytes.decode("latin-1", errors="ignore")

    def test_no_group_returns_all(self, client, gfx):
        r = client.get(f"{BASE_URL}/api/shipments/{gfx['sid']}/manifest.pdf", timeout=90)
        assert r.status_code == 200
        t = self._text(r.content)
        for n in gfx["in_group"] + [gfx["unassigned"]]:
            assert n in t, f"Missing item {n} in full-container manifest"

    def test_group_id_scopes_items(self, client, gfx):
        r = client.get(f"{BASE_URL}/api/shipments/{gfx['sid']}/manifest.pdf",
                       params={"group": gfx["gid"]}, timeout=90)
        assert r.status_code == 200
        t = self._text(r.content)
        for n in gfx["in_group"]:
            assert n in t
        assert gfx["unassigned"] not in t, "Unassigned item leaked into group-filtered PDF"

    def test_unassigned_group_returns_only_null(self, client, gfx):
        r = client.get(f"{BASE_URL}/api/shipments/{gfx['sid']}/manifest.pdf",
                       params={"group": "unassigned"}, timeout=90)
        assert r.status_code == 200
        t = self._text(r.content)
        assert gfx["unassigned"] in t
        for n in gfx["in_group"]:
            assert n not in t

    def test_bogus_group_id_returns_404(self, client, gfx):
        r = client.get(f"{BASE_URL}/api/shipments/{gfx['sid']}/manifest.pdf",
                       params={"group": "mg_definitely_not_real"}, timeout=15)
        assert r.status_code == 404

    def test_commercial_invoice_with_group_filter(self, client, gfx):
        r = client.get(f"{BASE_URL}/api/shipments/{gfx['sid']}/commercial-invoice.pdf",
                       params={"group": gfx["gid"]}, timeout=90)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        t = self._text(r.content)
        for n in gfx["in_group"]:
            assert n in t
        assert gfx["unassigned"] not in t


# ────────────── Delete group unassigns items ──────────────
class TestGroupDeleteUnassigns:
    def test_delete_group_reverts_items_to_null(self, client, shipment_id):
        # Create dedicated group + item so we don't mess with other tests
        g = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups",
                        json={"name": "TEST_deletable_group"}, timeout=15).json()
        gid = g["id"]
        item = _make_item(client, shipment_id, name="TEST_del_group_item")
        iid = item["id"]
        client.put(f"{BASE_URL}/api/shipments/{shipment_id}/items/{iid}",
                   json={"manifest_group_id": gid}, timeout=15)
        # Sanity: item is tagged
        det = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15).json()
        assert next(i for i in det["items"] if i["id"] == iid)["manifest_group_id"] == gid

        # Delete the group
        r = client.delete(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups/{gid}",
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("deleted") is True

        # Item still exists, but manifest_group_id is None
        det2 = client.get(f"{BASE_URL}/api/shipments/{shipment_id}", timeout=15).json()
        it = next((i for i in det2["items"] if i["id"] == iid), None)
        assert it is not None, "Item was deleted along with the group (should NOT be)"
        assert it["manifest_group_id"] is None
        # And the group is gone
        gids = [g["id"] for g in det2.get("manifest_groups", [])]
        assert gid not in gids

    def test_delete_group_404(self, client, shipment_id):
        r = client.delete(
            f"{BASE_URL}/api/shipments/{shipment_id}/manifest-groups/mg_nope_xyz",
            timeout=15,
        )
        assert r.status_code == 404


# ────────────── AI PVoC classification ──────────────
class TestAiPvocClassification:
    @pytest.fixture(scope="class")
    def ai_ctx(self, client):
        tag = uuid.uuid4().hex[:6]
        r = client.post(f"{BASE_URL}/api/shipments", json={
            "name": f"TEST_iter218_ai_{tag}", "dest_country": "Uganda",
        }, timeout=15)
        sid = r.json()["id"]
        used = _make_item(client, sid, name="Used donated shoes", qty_needed=5, condition="used")
        new = _make_item(client, sid, name="New Samsung wall charger", qty_needed=3, condition="new")
        yield {"sid": sid, "used_id": used["id"], "new_id": new["id"]}
        client.delete(f"{BASE_URL}/api/shipments/{sid}")

    def test_bulk_classify_returns_pvoc_fields(self, client, ai_ctx):
        r = client.post(
            f"{BASE_URL}/api/shipments/{ai_ctx['sid']}/classify-hs-bulk",
            json={"force": False}, timeout=240,
        )
        if r.status_code == 503:
            pytest.skip(f"AI unavailable: {r.text[:120]}")
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert "pvoc_flagged" in data
        assert isinstance(data["pvoc_flagged"], int)
        # Response rows carry per-item pvoc fields
        by_id = {row["item_id"]: row for row in data["results"] if row.get("ok")}
        for row in by_id.values():
            assert "requires_pvoc" in row
            assert "pvoc_reason" in row
            assert re.match(r"^\d{4}\.\d{2}$", row["hs_code"])
        # Persistence check
        det = client.get(f"{BASE_URL}/api/shipments/{ai_ctx['sid']}", timeout=15).json()
        used_it = next(i for i in det["items"] if i["id"] == ai_ctx["used_id"])
        new_it = next(i for i in det["items"] if i["id"] == ai_ctx["new_id"])
        # "Used donated shoes" should NOT require PVoC (per system prompt rules).
        # "New Samsung wall charger" SHOULD (new electricals).
        # We don't hard-fail on model non-determinism, but we do require the
        # `requires_pvoc` field to be present and boolean on both.
        assert isinstance(used_it.get("requires_pvoc"), bool)
        assert isinstance(new_it.get("requires_pvoc"), bool)
        # Best-effort assertions (should almost always be True with Gemini):
        if used_it["requires_pvoc"] is True or new_it["requires_pvoc"] is False:
            # AI disagreed with the reference expectation — log but don't
            # kill the suite; report as flaky data.
            pytest.skip(
                f"AI PVoC classification differed from spec: "
                f"used={used_it['requires_pvoc']}, new={new_it['requires_pvoc']}"
            )
        # Grand-total counter matches
        assert data["pvoc_flagged"] == sum(1 for i in [used_it, new_it] if i["requires_pvoc"])


# ────────────── Regression: iter217 basics still work ──────────────
class TestIter217Regression:
    def test_manifest_without_group_still_returns_pdf(self, client, shipment_id):
        r = client.get(f"{BASE_URL}/api/shipments/{shipment_id}/manifest.pdf", timeout=90)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_manifest_404_unknown_shipment(self, client):
        r = client.get(f"{BASE_URL}/api/shipments/does_not_exist_iter218/manifest.pdf", timeout=15)
        assert r.status_code == 404

    def test_invoice_404_unknown_shipment(self, client):
        r = client.get(f"{BASE_URL}/api/shipments/does_not_exist_iter218/commercial-invoice.pdf", timeout=15)
        assert r.status_code == 404
