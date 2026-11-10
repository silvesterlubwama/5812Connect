"""One-off: collapse duplicate store_settings rows (iter416).

`PUT /store-settings/{id}` upserts on `{location_id}`, but the collection had no
unique key, so a race (or an older write path) left up to eight rows per store.
`find_one` then returned whichever Mongo felt like — which is why a shop's name
or payment methods could look unsaved. Keeps the most recently updated row for
each organisation+location and drops the rest.

    python scripts/dedupe_store_settings.py [--apply]
"""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402


async def main(apply: bool) -> None:
    groups: dict = {}
    async for doc in raw_db.store_settings.find({}):
        key = (doc.get("organization_id"), doc.get("location_id"))
        groups.setdefault(key, []).append(doc)

    removed = 0
    for key, docs in groups.items():
        if len(docs) < 2:
            continue
        docs.sort(key=lambda d: str(d.get("updated_at") or ""), reverse=True)
        keep, drop = docs[0], docs[1:]
        print(f"{key}: keeping {keep.get('updated_at')} — dropping {len(drop)}")
        if apply:
            await raw_db.store_settings.delete_many({"_id": {"$in": [d["_id"] for d in drop]}})
        removed += len(drop)

    print(f"{'Removed' if apply else 'Would remove'} {removed} duplicate row(s)")
    if apply:
        await raw_db.store_settings.create_index(
            [("organization_id", 1), ("location_id", 1)], name="org_location_unique", unique=True)
        print("Unique index in place")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
