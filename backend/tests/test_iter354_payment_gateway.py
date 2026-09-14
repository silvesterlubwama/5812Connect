"""iter354 — generic payment gateway: catalogue, offline transfer checkout,
signed webhook -> inbox (matched + unmatched), manual logging + match."""
import asyncio
import hashlib
import hmac
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
SECRET = "iter354-test-secret"
RUN = os.urandom(3).hex()


def sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


async def main():
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(f"{name} {extra}".strip())
        print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra else ""))

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        r = await c.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        tok = r.json().get("access_token") or r.json().get("token")
        H = {"Authorization": f"Bearer {tok}"}
        check("admin login", bool(tok))

        # 1. catalogue
        r = await c.get("/api/payments/providers", headers=H)
        cat = r.json()
        ids = {p["id"] for p in cat["providers"]}
        check("provider catalogue", {"manual", "pesapal", "mtn_momo", "airtel_money", "flutterwave", "generic"} <= ids)
        check("webhook urls absolute", all(u.startswith("http") for u in cat["webhook_urls"].values()),
              str(cat["webhook_urls"]))
        original_provider = cat["active"]
        original_enabled = cat["enabled"]

        # 2. save credentials — secrets must come back masked, never in clear
        r = await c.put("/api/admin/system-settings", headers=H, json={"payments": {
            "provider": original_provider, "enabled": original_enabled,
            "providers": {
                "pesapal": {"consumer_key": "pk_test_iter354", "consumer_secret": "sec_iter354_abcd"},
                "generic": {"webhook_secret": SECRET, "base_url": "https://bank.example",
                            "api_key": "api_iter354", "webhook_header": "x-bank-signature"},
            },
            "offline": {"bank_name": "QA Bank", "account_name": "58:12 Global",
                        "account_number": "01234567890", "branch": "Kampala",
                        "mtn_number": "0770000000", "mtn_name": "58:12 Global",
                        "mtn_is_merchant": True},
        }})
        check("save provider keys", r.status_code == 200, r.text[:200])
        r = await c.get("/api/admin/system-settings", headers=H)
        pay = r.json()["payments"]
        blob = json.dumps(pay)
        check("secrets masked on read", "sec_iter354_abcd" not in blob and SECRET not in blob)
        check("pesapal key kept", pay["providers"]["pesapal"].get("consumer_secret_set") is True,
              str(pay["providers"].get("pesapal")))
        check("offline details kept", pay["offline"]["account_number"] == "01234567890")

        # 3. providers without keys must refuse, not crash
        r = await c.get("/api/public/products")
        shop = r.json()
        prods = shop.get("products") if isinstance(shop, dict) else shop
        check("public shop has products", bool(prods), str(shop)[:200])
        basket = [{"product_id": prods[0]["id"], "qty": 1}] if prods else []
        for prov in ("mtn_momo", "airtel_money"):
            await c.put("/api/admin/system-settings", headers=H,
                        json={"payments": {"provider": prov, "enabled": True}})
            r = await c.post("/api/public/orders", json={
                "name": "Cfg Test", "email": "cfg@example.com", "phone": "0770000001",
                "items": basket, "payment_option": "online", "online_method": "mobile_money",
                "network": "MTN"})
            check(f"{prov} unconfigured refused", r.status_code in (400, 503)
                  and "missing" in r.text.lower(), f"{r.status_code} {r.text[:160]}")

        # 4. bank-transfer checkout
        await c.put("/api/admin/system-settings", headers=H,
                    json={"payments": {"provider": "manual", "enabled": False}})
        sale_ref = None
        if prods:
            pid = prods[0]["id"]
            r = await c.post("/api/public/orders", json={
                "name": "Iter354 Buyer", "email": "buyer354@example.com", "phone": "0770000002",
                "items": [{"product_id": pid, "qty": 1}], "payment_option": "transfer"})
            body = r.json()
            check("transfer order accepted", r.status_code == 200, r.text[:250])
            ins = body.get("payment_instructions") or {}
            sale_ref = ins.get("reference") or body.get("receipt_number")
            check("instructions carry reference", bool(sale_ref), str(body)[:200])
            check("instructions list methods", any(m["kind"] == "bank_transfer" for m in ins.get("methods", [])),
                  str(ins.get("methods"))[:200])

        # 5. signed webhook -> matched inbox entry + sale flagged paid online
        await c.put("/api/admin/system-settings", headers=H,
                    json={"payments": {"provider": "generic", "enabled": True}})
        if sale_ref:
            payload = json.dumps({"event_id": f"evt_iter354_a_{RUN}", "reference": sale_ref,
                                  "amount": 1, "currency": "UGX", "status": "successful",
                                  "payer": "0770000002"}).encode()
            r = await c.post("/api/payments/generic/inbound", content=payload,
                             headers={"Content-Type": "application/json",
                                      "x-bank-signature": sign(payload)})
            check("signed webhook accepted", r.status_code == 200, r.text[:200])
            check("webhook matched the order", r.json().get("settled") is True, r.text[:200])
            # replay must not double-settle
            r2 = await c.post("/api/payments/generic/inbound", content=payload,
                              headers={"Content-Type": "application/json",
                                       "x-bank-signature": sign(payload)})
            check("webhook replay deduped", r2.json().get("duplicate") is True, r2.text[:150])

        # bad signature rejected
        bad = json.dumps({"event_id": f"evt_iter354_bad_{RUN}", "reference": "nope", "amount": 5,
                          "status": "successful"}).encode()
        r = await c.post("/api/payments/generic/inbound", content=bad,
                         headers={"Content-Type": "application/json", "x-bank-signature": "deadbeef"})
        check("bad signature rejected", r.status_code == 401, str(r.status_code))

        # unmatched money still lands in the inbox
        unk = json.dumps({"event_id": f"evt_iter354_unmatched_{RUN}", "reference": f"WHO-KNOWS-{RUN}",
                          "amount": 45000, "currency": "UGX", "status": "successful",
                          "payer": "0780000009"}).encode()
        r = await c.post("/api/payments/generic/inbound", content=unk,
                         headers={"Content-Type": "application/json", "x-bank-signature": sign(unk)})
        check("unmatched webhook stored", r.status_code == 200 and r.json().get("settled") is False, r.text[:200])
        unmatched_id = r.json().get("inbox_id")

        # 6. inbox + manual log + manual match
        r = await c.get("/api/payments/inbox?status=unmatched", headers=H)
        inbox = r.json()
        check("inbox lists unmatched", any(p["id"] == unmatched_id for p in inbox["payments"]), str(inbox)[:200])
        check("inbox hides raw payloads", all("raw" not in p for p in inbox["payments"]))

        r = await c.post("/api/payments/inbox/manual", headers=H, json={
            "reference": f"MANUAL-{RUN}", "amount": 12345, "payer": "Walk-in donor",
            "method": "manual", "note": "iter354 test"})
        check("manual payment logged", r.status_code == 200 and r.json()["status"] == "unmatched", r.text[:200])
        manual_id = r.json().get("id")

        r = await c.post("/api/payments/inbox/manual", headers=H, json={"reference": "X", "amount": 0})
        check("zero amount rejected", r.status_code == 400, str(r.status_code))

        if manual_id and sale_ref:
            r = await c.post(f"/api/payments/inbox/{manual_id}/match", headers=H, json={"sale_id": sale_ref})
            check("manual match to order", r.status_code == 200 and r.json()["status"] == "matched", r.text[:200])
        if unmatched_id:
            r = await c.post(f"/api/payments/inbox/{unmatched_id}/match", headers=H,
                             json={"ignore": True, "note": "iter354 not ours"})
            check("ignore unmatched", r.status_code == 200 and r.json()["status"] == "ignored", r.text[:150])
            r = await c.post("/api/payments/inbox/pin_doesnotexist/match", headers=H, json={"sale_id": "x"})
            check("unknown inbox entry 404", r.status_code == 404, str(r.status_code))

        # restore the provider the admin had selected
        await c.put("/api/admin/system-settings", headers=H, json={"payments": {
            "provider": original_provider, "enabled": original_enabled}})
        r = await c.get("/api/payments/providers", headers=H)
        check("provider restored", r.json()["active"] == original_provider, r.json()["active"])

    print(f"\n{len(ok)} passed, {len(fail)} failed")
    if fail:
        print("FAILURES: " + " | ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
