"""iter223 — Container/airport modes, packing units, passengers, suitcases, AI tracking.

Covers:
  • PUT /api/shipments/{sid}: mode + waybill/flight/carrier/tracking_url/dates/origin
  • GET /api/shipments/presets/packing-units — 12 presets
  • POST/PUT/DELETE /api/shipments/{sid}/packing-units — with stacking + cascade
  • POST/PUT/DELETE /api/shipments/{sid}/passengers — cascade to suitcases + items
  • POST/PUT/DELETE /api/shipments/{sid}/suitcases — tracking_no + defaults
  • PUT items whitelist extended with packing_unit_id/suitcase_id/passenger_id
  • POST /api/shipments/{sid}/ai-tracking — URL generation + Gemini summary
"""
import os
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
        "name": f"TEST_iter223_{tag}",
        "dest_country": "Uganda",
        "units": "metric",
    }, timeout=15)
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    yield sid
    client.delete(f"{BASE_URL}/api/shipments/{sid}")


# ─── Presets ─────────────────────────────────────────────────────
class TestPresets:
    def test_get_presets_has_12(self, client):
        r = client.get(f"{BASE_URL}/api/shipments/presets/packing-units")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        expected = {"eur_pallet", "us_pallet", "large_box", "medium_box", "small_box",
                    "plastic_tote", "crate_wood", "banana_box", "suitcase_lg",
                    "suitcase_md", "carry_on", "duffel"}
        assert expected.issubset(set(data.keys()))
        assert len(data) >= 12
        eur = data["eur_pallet"]
        for k in ("L_cm", "W_cm", "H_cm", "cap_kg", "label"):
            assert k in eur
        assert eur["L_cm"] == 120 and eur["W_cm"] == 80


# ─── Mode + Tracking fields ─────────────────────────────────────
class TestModeAndTracking:
    def test_mode_container(self, client, shipment_id):
        r = client.put(f"{BASE_URL}/api/shipments/{shipment_id}", json={"mode": "container"})
        assert r.status_code == 200
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        assert g["mode"] == "container"

    def test_mode_airport(self, client, shipment_id):
        r = client.put(f"{BASE_URL}/api/shipments/{shipment_id}", json={"mode": "airport"})
        assert r.status_code == 200
        assert client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()["mode"] == "airport"

    def test_mode_invalid(self, client, shipment_id):
        r = client.put(f"{BASE_URL}/api/shipments/{shipment_id}", json={"mode": "truck"})
        assert r.status_code == 400

    def test_tracking_fields_persist(self, client, shipment_id):
        payload = {
            "waybill_no": "KQ411-BOL-777",
            "flight_no": "KQ411",
            "carrier_name": "Kenya Airways",
            "tracking_url": "https://example.com/track/KQ411",
            "departure_date": "2026-02-01",
            "arrival_date": "2026-02-05",
            "origin_country": "USA",
        }
        r = client.put(f"{BASE_URL}/api/shipments/{shipment_id}", json=payload)
        assert r.status_code == 200
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        for k, v in payload.items():
            assert g.get(k) == v, f"{k}: expected {v}, got {g.get(k)}"


# ─── Packing Units ──────────────────────────────────────────────
class TestPackingUnits:
    def test_create_with_preset(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units",
                        json={"type": "pallet", "preset_key": "eur_pallet"})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["type"] == "pallet"
        assert u["L_cm"] == 120 and u["W_cm"] == 80
        assert u["weight_capacity_kg"] == 1500
        assert "eur_pallet" in u["preset_key"]
        # ensure persisted
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        assert any(x["id"] == u["id"] for x in g.get("packing_units", []))

    def test_create_invalid_type_400(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units",
                        json={"type": "spaceship"})
        assert r.status_code == 400

    def test_stacking_parent_and_child_orphaning(self, client, shipment_id):
        parent = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units",
                             json={"type": "pallet", "preset_key": "us_pallet",
                                   "name": "TEST_parent"}).json()
        child = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units",
                            json={"type": "box", "preset_key": "large_box",
                                  "name": "TEST_child", "parent_id": parent["id"]}).json()
        assert child["parent_id"] == parent["id"]
        # delete parent — child should be orphaned but survive
        r = client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units/{parent['id']}")
        assert r.status_code == 200
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        surviving = [u for u in g["packing_units"] if u["id"] == child["id"]]
        assert len(surviving) == 1
        assert surviving[0]["parent_id"] is None
        # cleanup
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units/{child['id']}")

    def test_update_whitelist(self, client, shipment_id):
        u = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units",
                        json={"type": "box"}).json()
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/packing-units/{u['id']}",
            json={"name": "renamed", "L_cm": 55.5, "color": "#ff0000",
                  "floor_x_cm": 100, "notes": "n",
                  "not_allowed_field": "hackery"},
        )
        assert r.status_code == 200 and r.json().get("updated") is True
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        got = [x for x in g["packing_units"] if x["id"] == u["id"]][0]
        assert got["name"] == "renamed" and got["L_cm"] == 55.5
        assert got["color"] == "#ff0000" and got["floor_x_cm"] == 100
        assert "not_allowed_field" not in got

    def test_delete_unassigns_items(self, client, shipment_id):
        # create unit, item, assign, delete unit → item unassigned
        u = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units",
                        json={"type": "tote", "preset_key": "plastic_tote"}).json()
        item = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                           json={"name": "TEST_item", "qty": 1}).json()
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{item['id']}",
            json={"packing_unit_id": u["id"]},
        )
        assert r.status_code == 200
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        assigned = [i for i in g["items"] if i["id"] == item["id"]][0]
        assert assigned["packing_unit_id"] == u["id"]
        # delete unit
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/packing-units/{u['id']}")
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        after = [i for i in g["items"] if i["id"] == item["id"]][0]
        assert after["packing_unit_id"] is None
        # cleanup
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/items/{item['id']}")


# ─── Passengers + Suitcases ────────────────────────────────────
class TestPassengersAndSuitcases:
    def test_passenger_requires_name(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers", json={})
        assert r.status_code == 400
        r2 = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers",
                         json={"name": "   "})
        assert r2.status_code == 400

    def test_passenger_create_and_update(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers",
                        json={"name": "TEST_John Doe", "passport_no": "P12345",
                              "flight_no": "KQ411",
                              "suitcase_allowance_kg": 32})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["name"] == "TEST_John Doe"
        assert p["passport_no"] == "P12345"
        assert p["flight_no"] == "KQ411"
        assert p["suitcase_allowance_kg"] == 32
        # update
        r2 = client.put(f"{BASE_URL}/api/shipments/{shipment_id}/passengers/{p['id']}",
                        json={"name": "TEST_Jane"})
        assert r2.status_code == 200
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        assert [x for x in g["passengers"] if x["id"] == p["id"]][0]["name"] == "TEST_Jane"
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/passengers/{p['id']}")

    def test_suitcase_requires_passenger(self, client, shipment_id):
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/suitcases",
                        json={"type": "suitcase"})
        assert r.status_code == 400

    def test_suitcase_preset_and_default_type(self, client, shipment_id):
        p = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers",
                        json={"name": "TEST_Pax"}).json()
        # invalid type falls back to 'suitcase'
        sc = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/suitcases",
                         json={"passenger_id": p["id"], "type": "invalidtype",
                               "preset_key": "suitcase_lg",
                               "tracking_no": "KQ411-BAG-001"}).json()
        assert sc["type"] == "suitcase"
        assert sc["L_cm"] == 76 and sc["W_cm"] == 51
        assert sc["weight_limit_kg"] == 23
        assert sc["tracking_no"] == "KQ411-BAG-001"
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/passengers/{p['id']}")

    def test_passenger_delete_cascade(self, client, shipment_id):
        # passenger + suitcase + item assigned — delete pax should clear both from item + pull suitcase
        p = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers",
                        json={"name": "TEST_Cascade"}).json()
        sc = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/suitcases",
                         json={"passenger_id": p["id"], "preset_key": "carry_on"}).json()
        item = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                           json={"name": "TEST_bag_item", "qty": 1}).json()
        r = client.put(
            f"{BASE_URL}/api/shipments/{shipment_id}/items/{item['id']}",
            json={"passenger_id": p["id"], "suitcase_id": sc["id"]},
        )
        assert r.status_code == 200
        # verify assignment
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        it_before = [i for i in g["items"] if i["id"] == item["id"]][0]
        assert it_before["passenger_id"] == p["id"] and it_before["suitcase_id"] == sc["id"]
        # delete passenger
        rd = client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/passengers/{p['id']}")
        assert rd.status_code == 200
        g2 = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        it_after = [i for i in g2["items"] if i["id"] == item["id"]][0]
        assert it_after["passenger_id"] is None and it_after["suitcase_id"] is None
        assert not any(s["id"] == sc["id"] for s in g2.get("suitcases", []))
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/items/{item['id']}")

    def test_suitcase_delete_unassigns_items(self, client, shipment_id):
        p = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers",
                        json={"name": "TEST_SCDel"}).json()
        sc = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/suitcases",
                         json={"passenger_id": p["id"]}).json()
        item = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/items",
                           json={"name": "TEST_x", "qty": 1}).json()
        client.put(f"{BASE_URL}/api/shipments/{shipment_id}/items/{item['id']}",
                   json={"suitcase_id": sc["id"]})
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/suitcases/{sc['id']}")
        g = client.get(f"{BASE_URL}/api/shipments/{shipment_id}").json()
        it = [i for i in g["items"] if i["id"] == item["id"]][0]
        assert it["suitcase_id"] is None
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/passengers/{p['id']}")
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/items/{item['id']}")


# ─── AI Tracking ────────────────────────────────────────────────
class TestAITracking:
    def test_ai_tracking_urls_and_summary(self, client, shipment_id):
        # Ensure fields set
        client.put(f"{BASE_URL}/api/shipments/{shipment_id}", json={
            "waybill_no": "KQ411-WB",
            "flight_no": "KQ411",
            "carrier_name": "Kenya Airways",
            "tracking_url": "https://example.com/direct",
        })
        # Add a suitcase w/ tracking_no
        p = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/passengers",
                        json={"name": "TEST_AI"}).json()
        client.post(f"{BASE_URL}/api/shipments/{shipment_id}/suitcases",
                    json={"passenger_id": p["id"], "tracking_no": "BAG12345"})
        r = client.post(f"{BASE_URL}/api/shipments/{shipment_id}/ai-tracking",
                        timeout=60)
        # If no LLM key, expect 503; otherwise 200
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            data = r.json()
            assert "summary" in data
            assert isinstance(data.get("tracking_urls"), list)
            urls = data["tracking_urls"]
            labels = " ".join(u.get("label", "") for u in urls)
            joined = " ".join(u.get("url", "") for u in urls)
            assert "example.com/direct" in joined  # direct URL
            assert "google.com/search" in joined  # waybill google
            assert "flightaware.com" in joined  # flight
            assert "BAG12345" in joined  # bag tag
            assert data.get("waybill_no") == "KQ411-WB"
            assert data.get("flight_no") == "KQ411"
            assert data.get("carrier") == "Kenya Airways"
            assert len(data["summary"]) <= 600
        # cleanup
        client.delete(f"{BASE_URL}/api/shipments/{shipment_id}/passengers/{p['id']}")

    def test_ai_tracking_shipment_not_found(self, client):
        r = client.post(f"{BASE_URL}/api/shipments/nonexistent-xxx/ai-tracking", timeout=15)
        # 404 if key exists, 503 if key not configured
        assert r.status_code in (404, 503)
