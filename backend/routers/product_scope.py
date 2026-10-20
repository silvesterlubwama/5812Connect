"""Shared products: one catalogue entry that several stores can sell.

A product is "shared" when it is flagged `is_universal` (every store) or lists
specific `store_ids`. Name, SKU and the base price travel with the product;
**stock is counted per store** in `store_stock`, and a store may charge its own
price via `store_prices`.

Anything that is not shared behaves exactly as it always has — a single
`location_id`, a single `stock`, a single `price` — so existing products need no
migration.

Products with variants cannot be shared: per-store-per-variant stock would need
a second dimension that nothing downstream (barcode labels, reorder rules, void
restores) understands, and silently reporting the wrong number is worse than
saying no.
"""
from typing import Optional

# A product saved with no store at all predates the shared-product idea. The
# products list used to filter it out of every campus, so it vanished; it is
# treated as available everywhere.
LEGACY_BLANK_IS_UNIVERSAL = True


def is_shared(product: dict) -> bool:
    return bool(product.get("is_universal") or (product.get("store_ids") or []))


def _has_no_home(product: dict) -> bool:
    return (not (product.get("location_id") or "")
            and not (product.get("store_ids") or [])
            and not product.get("is_universal"))


def available_at(product: dict, store_id: str) -> bool:
    """Can this store sell this product?"""
    if product.get("is_universal"):
        return True
    if store_id and store_id in (product.get("store_ids") or []):
        return True
    if store_id and product.get("location_id") == store_id:
        return True
    return LEGACY_BLANK_IS_UNIVERSAL and _has_no_home(product)


def availability_query(allowed_locations: Optional[list] = None, store_id: str = "") -> dict:
    """Mongo `$or` for the products a caller may see."""
    ors: list = [
        {"is_universal": True},
        # Legacy blank-store products — no home campus and no store list.
        {"location_id": {"$in": ["", None]}, "store_ids": {"$in": [None, []]}},
    ]
    if store_id:
        ors.append({"location_id": store_id})
        ors.append({"store_ids": store_id})
    elif allowed_locations:
        locs = list(allowed_locations)
        ors.append({"location_id": {"$in": locs}})
        ors.append({"store_ids": {"$in": locs}})
    return {"$or": ors}


def locations_from_campus_filter(campus: dict) -> list:
    """Pull the campus ids out of whatever shape `get_campus_filter` returned —
    it may be `{"location_id": {"$in": [...]}}`, a bare string, or an `$or` of
    both `location_id` and `location_ids`."""
    found: list = []

    def _take(clause: dict) -> None:
        for key in ("location_id", "location_ids"):
            value = clause.get(key)
            if isinstance(value, dict) and isinstance(value.get("$in"), list):
                found.extend(v for v in value["$in"] if isinstance(v, str) and v)
            elif isinstance(value, str) and value:
                found.append(value)

    if not campus:
        return []
    for clause in campus.get("$or") or []:
        if isinstance(clause, dict):
            _take(clause)
    _take(campus)
    return list(dict.fromkeys(found))


def stock_at(product: dict, store_id: str = "") -> int:
    """On-hand at one store. A shared product keeps its counts in `store_stock`;
    everything else keeps using the single `stock` field."""
    if not is_shared(product):
        return int(product.get("stock") or 0)
    per_store = product.get("store_stock") or {}
    if store_id:
        return int(per_store.get(store_id) or 0)
    # No store in context (reports, totals): the whole chain's on-hand.
    return sum(int(v or 0) for v in per_store.values())


def price_at(product: dict, store_id: str = "") -> float:
    """Base price unless this store overrides it."""
    base = float(product.get("price") or 0)
    if not store_id:
        return base
    override = (product.get("store_prices") or {}).get(store_id)
    if override in (None, ""):
        return base
    try:
        return float(override)
    except (TypeError, ValueError):
        return base


def stock_field(product: dict, store_id: str = "") -> str:
    """Mongo field to `$inc` when stock moves. Keeping shared stock in a
    sub-document is what lets one store sell without touching another's count."""
    if is_shared(product) and store_id:
        return f"store_stock.{store_id}"
    return "stock"


def resolve_for_store(product: dict, store_id: str = "") -> dict:
    """Flatten a product to how one store sees it, so every existing consumer
    (POS grid, public shop, receipts) can carry on reading `stock` and `price`."""
    out = dict(product)
    out["stock"] = stock_at(product, store_id)
    out["price"] = price_at(product, store_id)
    out["shared"] = is_shared(product)
    out["store_id"] = store_id or product.get("location_id") or ""
    if is_shared(product):
        out["total_stock"] = stock_at(product, "")
    return out


def stores_for(product: dict, all_location_ids: list) -> list:
    """Stores whose on-hand is worth reporting. A universal product is only
    really stocked where it has a count (plus its home store) — alerting for
    every campus in the organisation would be noise, not news."""
    if product.get("store_ids"):
        return list(product["store_ids"])
    counted = [s for s in (product.get("store_stock") or {}) if s]
    home = product.get("location_id") or ""
    if product.get("is_universal") or (LEGACY_BLANK_IS_UNIVERSAL and _has_no_home(product)):
        stores = counted or list(all_location_ids)
        if home and home not in stores:
            stores = [home, *stores]
        return stores
    return [home] if home else []
