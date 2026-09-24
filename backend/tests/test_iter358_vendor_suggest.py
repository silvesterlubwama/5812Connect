"""iter358 — vendor typeahead matches anywhere in the name.

The suggest endpoint was prefix-anchored and interpolated raw user input into a
regex, so "supplies" never found "ACME Supplies Ltd" and a name typed with a
bracket blew up the query.
"""
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))
from tests.creds import ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
NAMES = ["ACME Supplies Ltd (iter358)", "Kampala Hardware iter358", "acme spares iter358"]


async def main():
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(f"{name} {extra}".strip())
        print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra else ""))

    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        r = await c.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        H = {"Authorization": f"Bearer {r.json()['token']}"}

        # Vendors are auto-created from expense entry, there is no POST /vendors,
        # so the fixtures go in directly.
        mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        loc = (await c.get("/api/locations", headers=H)).json()
        loc_id = (loc if isinstance(loc, list) else loc["locations"])[0]["id"]
        fixtures = NAMES + ["Dupe Vendor iter358"] * 3
        for i, n in enumerate(fixtures):
            mdb.vendors.insert_one({"id": f"ven_iter358_{i}", "name": n, "category": "supplies",
                                    "location_id": loc_id, "active": True})
        check("vendors created", mdb.vendors.count_documents({"id": {"$regex": "^ven_iter358_"}}) == len(fixtures))

        async def suggest(q):
            r = await c.get("/api/vendors/suggest", headers=H, params={"q": q})
            return r.status_code, [v["name"] for v in (r.json() if r.status_code == 200 else [])]

        st, names = await suggest("supplies")
        check("matches a word in the middle", st == 200 and any("ACME Supplies" in n for n in names), str(names))

        st, names = await suggest("acme")
        check("matches the start, case-insensitively", st == 200 and len([n for n in names if "cme" in n.lower()]) >= 2, str(names))
        if names:
            check("prefix matches come first", names[0].lower().startswith("acme"), str(names[:3]))

        st, names = await suggest("hardware")
        check("finds the second vendor by its word", st == 200 and any("Hardware" in n for n in names), str(names))

        st, names = await suggest("(iter358)")
        check("regex characters don't break it", st == 200, f"status {st}")
        check("bracketed text still matches", any("(iter358)" in n for n in names), str(names))

        st, names = await suggest("nothing-like-this-358")
        check("no match returns an empty list", st == 200 and names == [], str(names))

        # duplicates collapse — the app makes a vendor from free text
        st, names = await suggest("Dupe Vendor iter358")
        check("duplicate names collapse to one row", names.count("Dupe Vendor iter358") == 1, str(names))

        mdb.vendors.delete_many({"id": {"$regex": "^ven_iter358_"}})

    print(f"\n{len(ok)} passed, {len(fail)} failed")
    if fail:
        print("FAILURES: " + " | ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
