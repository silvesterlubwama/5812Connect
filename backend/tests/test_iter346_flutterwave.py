"""iter346 — Flutterwave online checkout: config, init, verify-settle, webhook."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deps import db  # noqa: E402
import routers.payments_flutterwave as flw  # noqa: E402


async def main():
    # --- config round-trip (as the admin UI saves it) -----------------
    from routers.system_settings import _load_raw, _mask_for_read, SETTINGS_ID
    raw = await _load_raw()
    prev = dict(raw.get("payments") or {})
    raw["payments"] = {**raw.get("payments", {}), "enabled": True, "mode": "test",
                       "secret_key": "FLWSECK_TEST-abcdef123456", "public_key": "FLWPUBK_TEST-xyz",
                       "webhook_hash": "test-secret-hash", "currency": "UGX",
                       "allow_card": True, "allow_mobile_money": True,
                       "allow_pay_on_collection": True}
    await db.system_settings.update_one({"id": SETTINGS_ID}, {"$set": raw}, upsert=True)
    masked = _mask_for_read(await _load_raw())["payments"]
    assert masked["secret_key_set"] and "abcdef" not in json.dumps(masked), masked
    assert masked["secret_key_masked"].endswith("3456"), masked
    print("PASS config saved + masked on read")

    cfg = await flw._cfg()
    assert cfg["secret_key"].startswith("FLWSECK_TEST")
    print("PASS backend reads the secret internally")

    # --- init_payment: hosted + momo, with the HTTP call stubbed ------
    calls = []

    async def fake_flw(method, path, secret, **kw):
        calls.append((method, path, kw.get("json")))
        if path == "/payments":
            return {"data": {"link": "https://checkout.flutterwave.com/pay/abc"}}
        if path.startswith("/charges"):
            return {"meta": {"authorization": {"redirect": "https://momo.flutterwave.com/auth/xyz"}}}
        if "/verify" in path:
            tx = calls_ctx["tx_ref"]
            return {"data": {"status": "successful", "tx_ref": tx, "currency": "UGX",
                             "amount": 5000, "id": 99887766, "flw_ref": "FLW-REF-1",
                             "payment_type": "mobilemoneyuganda",
                             "customer": {"email": "buyer@example.com"}}}
        raise AssertionError(path)

    calls_ctx = {}
    flw._flw = fake_flw

    sale = {"id": "TEST-SALE-346", "total": 5000, "receipt_number": "TEST-SALE-346"}
    await db.sales.delete_many({"id": sale["id"]})
    await db.sales.insert_one({**sale, "payment_status": "pending", "customer_email": "buyer@example.com",
                               "customer_name": "Test Buyer"})

    hosted = await flw.init_payment(sale, email="buyer@example.com", name="Test Buyer", phone="+256700000000",
                                    method="card", network="", origin="https://shop.example.org")
    assert hosted["payment_url"].startswith("https://checkout.flutterwave.com"), hosted
    assert calls[-1][2]["currency"] == "UGX" and calls[-1][2]["amount"] == 5000
    print("PASS hosted checkout returns a payment link")

    momo = await flw.init_payment(sale, email="buyer@example.com", name="Test Buyer", phone="+256700000000",
                                  method="mobile_money", network="airtel", origin="https://shop.example.org")
    assert momo["payment_url"].startswith("https://momo.flutterwave.com"), momo
    assert calls[-1][2]["network"] == "AIRTEL", calls[-1]
    print("PASS uganda mobile money sends network=AIRTEL")

    try:
        await flw.init_payment(sale, email="b@e.org", name="n", phone="", method="mobile_money",
                               network="", origin="")
        raise AssertionError("expected 400")
    except Exception as ex:
        assert "MTN" in str(getattr(ex, "detail", ex)), ex
    print("PASS momo without phone/network is rejected")

    # --- verify + settle ---------------------------------------------
    doc = await db.sales.find_one({"id": sale["id"]}, {"_id": 0})
    calls_ctx["tx_ref"] = doc["tx_ref"]
    ok = await flw._settle("99887766", doc["tx_ref"])
    assert ok
    doc = await db.sales.find_one({"id": sale["id"]}, {"_id": 0})
    assert doc["online_payment_status"] == "paid", doc
    assert doc["payment_status"] == "pending", "staff must still confirm before the ledger moves"
    assert doc["payment_reference"] == "99887766"
    print("PASS settled sale = paid online, still awaiting staff confirmation")

    # amount mismatch must NOT settle
    await db.sales.update_one({"id": sale["id"]}, {"$set": {"online_payment_status": "initiated", "total": 999999}})
    ok2 = await flw._settle("99887766", doc["tx_ref"])
    assert ok2 is False
    bad = await db.sales.find_one({"id": sale["id"]}, {"_id": 0, "online_payment_status": 1})
    assert bad["online_payment_status"] == "failed", bad
    print("PASS underpayment is refused")

    # --- webhook signature -------------------------------------------
    body = json.dumps({"event": "charge.completed", "id": 1, "data": {"id": 99887766, "tx_ref": doc["tx_ref"]}}).encode()
    good = base64.b64encode(hmac.new(b"test-secret-hash", body, hashlib.sha256).digest()).decode()
    assert flw._valid_signature(body, _Req({"flutterwave-signature": good}), "test-secret-hash")
    assert not flw._valid_signature(body, _Req({"flutterwave-signature": good[:-2] + "xx"}), "test-secret-hash")
    assert flw._valid_signature(body, _Req({"verif-hash": "test-secret-hash"}), "test-secret-hash")
    assert not flw._valid_signature(body, _Req({}), "test-secret-hash")
    print("PASS webhook signature accepts valid + rejects tampered")

    # cleanup
    await db.sales.delete_many({"id": sale["id"]})
    raw = await _load_raw()
    raw["payments"] = prev or {}
    await db.system_settings.update_one({"id": SETTINGS_ID}, {"$set": raw}, upsert=True)
    print("ALL PASS")


class _Req:
    def __init__(self, headers):
        self.headers = headers


if __name__ == "__main__":
    asyncio.run(main())
