"""Iteration 195 — unit tests for the standalone shipment helpers module.

These run in-process (no HTTP, no DB), so they're orders of magnitude
faster than the integration tests in test_iter186_dedupe.py and they
narrowly cover the placement logic that previously lived inline inside
routers/shipments.py.
"""
import pytest
from shipment_helpers import auto_place_on_pallet


def _make_pallet(pid, label="P"):
    return {"id": pid, "label": label}


def _make_item(**overrides):
    base = {
        "id": "x",
        "container_type": "pallet",
        "weight_kg": 0,
        "qty_acquired": 1,
        "dims_cm": {"length": 0, "width": 0, "height": 0},
    }
    base.update(overrides)
    return base


class TestAutoPlaceOnPallet:
    def test_loose_container_untouched(self):
        item = _make_item(container_type="container", weight_kg=10)
        auto_place_on_pallet(item, [], [_make_pallet("p1")])
        assert item.get("pallet_id") is None
        assert "auto_placed" not in item

    def test_unknown_container_type_untouched(self):
        item = _make_item(container_type="bucket", weight_kg=10)
        auto_place_on_pallet(item, [], [_make_pallet("p1")])
        assert "auto_placed" not in item

    def test_picks_lightest_pallet(self):
        existing = [
            {"id": "a", "pallet_id": "p1", "weight_kg": 25, "qty_acquired": 4},  # 100 kg
            {"id": "b", "pallet_id": "p2", "weight_kg": 5, "qty_acquired": 3},   # 15 kg
        ]
        pallets = [_make_pallet("p1"), _make_pallet("p2")]
        item = _make_item(weight_kg=2)
        auto_place_on_pallet(item, existing, pallets)
        assert item["pallet_id"] == "p2"
        assert item["auto_placed"] is True

    def test_respects_existing_pallet_id(self):
        existing = []
        pallets = [_make_pallet("p1"), _make_pallet("p2")]
        item = _make_item(pallet_id="p1", weight_kg=5)
        auto_place_on_pallet(item, existing, pallets)
        assert item["pallet_id"] == "p1"
        # pallet_id was set by caller — no auto_placed flag should fire
        assert "auto_placed" not in item

    def test_stacks_lighter_on_heaviest(self):
        existing = [
            _make_item(id="bottom", pallet_id="p1", weight_kg=20,
                       dims_cm={"length": 60, "width": 40, "height": 25}),
        ]
        item = _make_item(pallet_id="p1", weight_kg=2,
                          dims_cm={"length": 30, "width": 20, "height": 10})
        auto_place_on_pallet(item, existing, [_make_pallet("p1")])
        assert item["parent_id"] == "bottom"
        assert item["auto_stacked"] is True
        assert item["z_cm"] == 25.0

    def test_similar_weights_stay_side_by_side(self):
        existing = [_make_item(id="bottom", pallet_id="p1", weight_kg=25)]
        item = _make_item(pallet_id="p1", weight_kg=24)
        auto_place_on_pallet(item, existing, [_make_pallet("p1")])
        assert "parent_id" not in item
        assert "auto_stacked" not in item

    def test_does_not_stack_on_already_stacked(self):
        # Only the truly-bottom item is a candidate. If everything is on
        # top of something, leave the new item as a new bottom-layer row.
        existing = [
            _make_item(id="b", pallet_id="p1", weight_kg=20, parent_id="ghost"),
        ]
        item = _make_item(pallet_id="p1", weight_kg=2)
        auto_place_on_pallet(item, existing, [_make_pallet("p1")])
        assert "parent_id" not in item

    def test_pallets_with_no_existing_items_still_get_assigned(self):
        # Brand-new shipment: no existing items, two empty pallets — pick
        # the first one (both have zero weight).
        item = _make_item(weight_kg=8)
        auto_place_on_pallet(item, [], [_make_pallet("p1"), _make_pallet("p2")])
        assert item["pallet_id"] in {"p1", "p2"}
        assert item["auto_placed"] is True
