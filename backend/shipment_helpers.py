"""Pure (no-DB) helpers extracted from `routers/shipments.py`.

We keep these together so the route file stays focused on HTTP-shape concerns
and the placement / stacking logic stays unit-testable in isolation. The
functions here mutate dicts in place — that matches how they're used inside
the larger `_add_or_merge_item` flow which already operates on a working
draft of the item before the Mongo write.
"""
from typing import Iterable, Mapping


def auto_place_on_pallet(item: dict, existing_items: Iterable[Mapping], pallets: Iterable[Mapping]) -> None:
    """Mutates `item` in-place to fill in `pallet_id` and/or `parent_id`
    when the caller left them blank.

    - When `container_type` is "pallet"/"box"/"tote" AND `pallet_id` is
      empty → assigns the LIGHTEST pallet by current cumulative weight.
      Marks `auto_placed=True`.
    - When `pallet_id` is set AND `parent_id` is empty → stacks the new
      item on top of the heaviest bottom-layer item on that pallet, IF
      our item is < 90% of the heaviest's weight (otherwise stays
      side-by-side). Marks `auto_stacked=True` and sets `z_cm` to the
      bottom item's height.
    - Loose floor items (`container_type='container'`) are never touched.
    """
    ctype = (item.get("container_type") or "").lower()
    if ctype not in ("pallet", "box", "tote"):
        return
    existing_items = list(existing_items)
    pallets = list(pallets)

    # Step 1 — auto-assign to lightest pallet if none picked
    if not item.get("pallet_id") and pallets:
        per_pallet_weight = {p["id"]: 0.0 for p in pallets}
        for it in existing_items:
            pid = it.get("pallet_id")
            if pid in per_pallet_weight:
                per_pallet_weight[pid] += (
                    float(it.get("weight_kg") or 0) * int(it.get("qty_acquired") or 0)
                )
        lightest = min(per_pallet_weight.items(), key=lambda x: x[1])[0]
        item["pallet_id"] = lightest
        item["auto_placed"] = True

    # Step 2 — auto-stack on the heaviest existing item on the same pallet
    # so the densest layers stay at the bottom. Only stack if our item is
    # noticeably lighter than the candidate (otherwise side-by-side is fine).
    if item.get("pallet_id") and not item.get("parent_id"):
        bottom_layer = [
            it for it in existing_items
            if it.get("pallet_id") == item["pallet_id"]
            and not it.get("parent_id")  # only stack on items that aren't already stacked
        ]
        if bottom_layer:
            our_w = float(item.get("weight_kg") or 0)
            heaviest = max(bottom_layer, key=lambda it: float(it.get("weight_kg") or 0))
            heaviest_w = float(heaviest.get("weight_kg") or 0)
            if heaviest_w > 0 and our_w < heaviest_w * 0.9:
                item["parent_id"] = heaviest["id"]
                item["z_cm"] = float((heaviest.get("dims_cm") or {}).get("height") or 0)
                item["auto_stacked"] = True
