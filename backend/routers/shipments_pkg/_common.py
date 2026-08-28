"""Common utilities for shipments package — shared by every submodule.

All shared helpers, constants and PIN/security re-exports live here so each
router file can be small + independently readable.
"""
from fastapi import APIRouter, HTTPException  # noqa: F401 — re-exported
from typing import Optional  # noqa: F401
import os as _os  # noqa: F401
import os  # noqa: F401
import asyncio
import uuid
import hmac  # noqa: F401
import hashlib  # noqa: F401
import base64  # noqa: F401
import secrets  # noqa: F401
import re  # noqa: F401
import json  # noqa: F401
from datetime import datetime, timezone, timedelta  # noqa: F401

from deps import db, logger, _audit, get_current_user, require_admin  # noqa: F401
from shipment_helpers import auto_place_on_pallet
from shipment_security import (  # noqa: F401 — intentional re-exports
    _PIN_SECRET,
    _PIN_SALT,
    EDIT_TOKEN_TTL_HOURS,
    hash_pin as _hash_pin,
    make_edit_token as _make_edit_token,
    verify_edit_token as _verify_edit_token,
    require_shipment_editor,
)
from shipment_units import parse_dim_to_cm, parse_weight_to_kg  # noqa: F401

# 40' high-cube interior dimensions in cm — used in the AI packing prompt.
CONTAINER_40FT_HC = {"length_cm": 1203, "width_cm": 235, "height_cm": 269, "max_payload_kg": 26000}

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
VALID_STATUSES = {"planning", "collecting", "packed", "shipped", "delivered", "cancelled"}
VALID_TRANSPORT_MODES = {"container", "suitcase", "holdback"}

def _normalise_item(data: dict, units: str = "metric") -> dict:
    """Coerce + clamp item fields. Used by both create and bulk-import.

    `units` lets the caller pass imperial OR metric inputs — `weight_kg`,
    `dims_cm`, `x_cm`, `y_cm`, `z_cm` all run through the unit parsers
    which accept strings like `2'9"`, `5lb 8oz`, `33in`, `0.84m`, `84cm`,
    or bare numbers (which fall back to the shipment's unit preference)."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="item.name is required")
    priority = (data.get("priority") or "normal").lower()
    if priority not in VALID_PRIORITIES:
        priority = "normal"
    container_type = (data.get("container_type") or "container").lower()
    if container_type not in ("container", "pallet", "box", "tote"):
        container_type = "container"
    dims_in = data.get("dims_cm") or {}
    return {
        "id": f"sit_{uuid.uuid4().hex[:8]}",
        "name": name[:160],
        "category": (data.get("category") or "")[:60],
        "qty_needed": max(1, int(data.get("qty_needed") or 1)),
        "qty_acquired": max(0, int(data.get("qty_acquired") or 0)),
        "weight_kg": max(0.0, parse_weight_to_kg(data.get("weight_kg") or 0, units)),
        "dims_cm": {
            "length": max(0.0, parse_dim_to_cm(dims_in.get("length") or 0, units)),
            "width":  max(0.0, parse_dim_to_cm(dims_in.get("width")  or 0, units)),
            "height": max(0.0, parse_dim_to_cm(dims_in.get("height") or 0, units)),
        },
        "photo_url": (data.get("photo_url") or "")[:500],
        # Multiple photos from the AI scanner — cover, back, spine, etc.
        "image_urls": [(u or "")[:500] for u in (data.get("image_urls") or []) if u],
        # Customs manifest fields (iter216) — HS code + new/used condition
        "hs_code": (data.get("hs_code") or "")[:20],
        "hs_code_reason": (data.get("hs_code_reason") or "")[:200],
        "condition": (data.get("condition") or "used").lower() if (data.get("condition") or "used").lower() in ("new", "used", "refurbished") else "used",
        # PVoC (Pre-Export Verification of Conformity) — required by EAC customs
        # for regulated goods (new electricals, cosmetics, food, chemicals, etc.).
        # Can be set manually by the operator or auto-inferred by the AI classifier.
        "requires_pvoc": bool(data.get("requires_pvoc", False)),
        "pvoc_reason": (data.get("pvoc_reason") or "")[:200],
        # Sub-manifest grouping — an item belongs to at most one manifest group
        # (e.g. "58:12 Global Shipment" vs "Lubwama Household Relocation").
        # null / absent = "unassigned" (still appears on the full-container manifest).
        "manifest_group_id": data.get("manifest_group_id") or None,
        "value_usd": max(0, float(data.get("value_usd") or 0)),
        "notes": (data.get("notes") or "")[:500],
        "priority": priority,
        "pallet_id": data.get("pallet_id") or None,
        # iter223 — polymorphic packing units (pallet/box/tote/crate) with
        # stacking parent, AND airport-mode suitcase / passenger references.
        # At most ONE of packing_unit_id / suitcase_id should be set.
        "packing_unit_id": data.get("packing_unit_id") or None,
        "suitcase_id": data.get("suitcase_id") or None,
        "passenger_id": data.get("passenger_id") or None,
        # Stacking: if `parent_id` points to another item, this item sits ON TOP
        # of that one. Otherwise it sits on its pallet (or on the container floor
        # when container_type=container).
        "parent_id": data.get("parent_id") or None,
        "container_type": container_type,
        # Acquired ≠ packed. `qty_acquired` counts what has physically arrived at
        # the warehouse; `qty_packed` counts what's been loaded for shipping.
        # Independent counters — an item can be 20 acquired, 15 packed, 5 held back.
        "qty_packed": max(0, int(data.get("qty_packed") or 0)),
        # How this item is travelling: sea container, staff suitcase, or held
        # back entirely for a future shipment. Determines the visibility rules
        # on the donor page.
        "transport_mode": (data.get("transport_mode") or "container").lower()
            if (data.get("transport_mode") or "container").lower() in VALID_TRANSPORT_MODES
            else "container",
        # Barcode identifiers from the scanner — used for waybill + dedupe.
        "isbn": (data.get("isbn") or "")[:30],
        "upc": (data.get("upc") or "")[:30],
        "author": (data.get("author") or "")[:120],         # Books: author
        "publisher": (data.get("publisher") or "")[:120],
        # Audit fields — set when added via the PIN-gated public scanner
        "scanned_by_pin_hint": (data.get("scanned_by_pin_hint") or "")[:8],
        "scanned_at": data.get("scanned_at"),
        "ai_identified": bool(data.get("ai_identified", False)),
        # Position WITHIN the assigned pallet (cm from pallet's back-left
        # corner). Optional — admin can set via the form-based item editor.
        # iter 260 — items linked to a packing unit auto-snap to the box
        # origin (0,0,0) so bulk imports / AI-linked items never carry a
        # stale offset. Loose items keep whatever coords the caller set.
        "x_cm": 0.0 if data.get("packing_unit_id") else max(0.0, parse_dim_to_cm(data.get("x_cm") or 0, units)),
        "y_cm": 0.0 if data.get("packing_unit_id") else max(0.0, parse_dim_to_cm(data.get("y_cm") or 0, units)),
        "z_cm": 0.0 if data.get("packing_unit_id") else max(0.0, parse_dim_to_cm(data.get("z_cm") or 0, units)),
        "donations": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _shipment_units(shipment_id: str) -> str:
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "units": 1})
    return (s or {}).get("units") or "metric"


async def _add_or_merge_item(shipment_id: str, item: dict) -> dict:
    """Add an item, OR — if another item in this shipment has the same
    ISBN/UPC AND the same pallet placement — increment its qty_acquired
    instead of creating a near-duplicate row.

    Also annotates the response with `over_pledged: true` when the merged
    qty exceeds qty_needed so the UI can warn the packer.
    """
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "items": 1, "pallets": 1, "container_dims_cm": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    existing_items = s.get("items") or []
    # Dedupe key: same ISBN or same UPC AND same pallet+container_type
    # (so the same book on two different pallets stays as two rows).
    dedupe_id = None
    if item.get("isbn") or item.get("upc"):
        for it in existing_items:
            if it.get("pallet_id") != item.get("pallet_id"):
                continue
            if it.get("container_type") != item.get("container_type"):
                continue
            same_isbn = item.get("isbn") and it.get("isbn") == item["isbn"]
            same_upc = item.get("upc") and it.get("upc") == item["upc"]
            if same_isbn or same_upc:
                dedupe_id = it["id"]
                break
    if dedupe_id:
        # Increment qty + refresh photo if we have a new one
        new_qty_delta = max(1, int(item.get("qty_acquired") or 1))
        set_ops = {"items.$.updated_at": datetime.now(timezone.utc).isoformat()}
        if item.get("photo_url"):
            set_ops["items.$.photo_url"] = item["photo_url"]
        await db.shipments.update_one(
            {"id": shipment_id, "items.id": dedupe_id},
            {"$inc": {"items.$.qty_acquired": new_qty_delta}, "$set": set_ops},
        )
        # Re-read the merged item so we can report over-pledge status
        s2 = await db.shipments.find_one(
            {"id": shipment_id, "items.id": dedupe_id},
            {"_id": 0, "items.$": 1},
        )
        merged = (s2 or {}).get("items", [{}])[0]
        merged["merged"] = True
        merged["over_pledged"] = merged.get("qty_acquired", 0) > merged.get("qty_needed", 1)
        return merged
    # iter 254 — auto-placement DISABLED. Previously we auto-assigned an
    # item to the lightest pallet and auto-stacked lighter items on top of
    # heavier ones, but that "snapping" made it impossible for admins to
    # place items exactly where they wanted. Items now land wherever the
    # caller specifies (or unassigned/loose when nothing is picked), and
    # stacking is 100% manual via drag-and-drop onto another item.
    # auto_place_on_pallet(item, existing_items, s.get("pallets") or [])
    # iter 260 — Staging area for loose items with real dims. A brand new
    # item that has no pallet, no packing_unit AND has known dimensions
    # (either from the caller's dims_cm or an AI shape3d) is dropped just
    # past the container's back wall so packers can see it and drag it in.
    # Items still get shape3d/dims later via derive-shape which also
    # auto-stages when needed — this hook covers items imported with dims.
    dims_cm = item.get("dims_cm") or {}
    has_real_dims = any(float(dims_cm.get(k) or 0) > 0 for k in ("length", "width", "height"))
    if (
        has_real_dims
        and not item.get("pallet_id")
        and not item.get("packing_unit_id")
        and item.get("floor_x_cm") in (None, 0, 0.0)
        and item.get("floor_y_cm") in (None, 0, 0.0)
    ):
        cont = s.get("container_dims_cm") or {}
        cont_L = float(cont.get("length_cm") or 1203)
        cont_W = float(cont.get("width_cm") or 235)
        staged_count = sum(
            1 for it in existing_items
            if not it.get("pallet_id")
            and not it.get("packing_unit_id")
            and (it.get("floor_x_cm") or 0) >= cont_L
        )
        slot = 80.0
        cols = max(1, int(cont_W // slot))
        item["floor_x_cm"] = cont_L + 30.0 + (staged_count // cols) * slot
        item["floor_y_cm"] = (staged_count % cols) * slot
    # New row
    await db.shipments.update_one({"id": shipment_id}, {"$push": {"items": item}})
    item["over_pledged"] = item.get("qty_acquired", 0) > item.get("qty_needed", 1)
    return item


# Backwards-compat shim — older code paths in this module called
# `_auto_place_on_pallet(...)` directly. The real logic now lives in
# `shipment_helpers.auto_place_on_pallet` (pure, unit-testable). Leaving
# this thin wrapper keeps any straggler call sites working.
def _auto_place_on_pallet(item: dict, existing_items: list, pallets: list) -> None:
    auto_place_on_pallet(item, existing_items, pallets)


async def _classify_hs_with_ai(name: str, category: str, condition: str = "used", dest_country: str = "") -> dict:
    """iter 256 — Simplified. Returns just `{hs_code, reason}` for a single item.
    PVoC classification removed at user request — it was too expensive per call
    and pushed the batch endpoint past Cloudflare's 120s wall. HS codes still
    populated for every item; downstream code that still reads `requires_pvoc`
    falls back to False.

    Timeout-bound (35s max per call) so a slow LLM response can never hang the
    request past the proxy timeout window.
    """
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI unavailable (no LLM key configured)")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI client unavailable: {e}")
    dest_hint = dest_country.strip().upper() or "UGANDA"
    sys_msg = (
        "You are a customs classification assistant for East African Community "
        "shipments (Uganda, Kenya, Tanzania, Rwanda). For each item, return "
        'STRICT JSON: {"hs_code": "XXXX.XX", "reason": "<=100 chars"}\n'
        "HS RULES:\n"
        "- ALWAYS 6 digits formatted as XXXX.XX (e.g. 4901.99 for printed books).\n"
        "- Used clothing / worn textiles → 6309.00.\n"
        "- Books & printed matter → 4901.xx.\n"
        "- Toys → 9503.00.\n"
        "- Medical supplies (bandages, first-aid) → 3005.90.\n"
        "- Consumer electronics with radio/wifi → 8517.62.\n"
        f"Destination country: {dest_hint}\n"
        "No commentary, no markdown fences — JSON only."
    )
    user_text = f"Item: {name}\nCategory: {category or '(unspecified)'}\nCondition: {condition}\n"
    chat = LlmChat(
        api_key=api_key,
        session_id=f"shipment_hs_{uuid.uuid4().hex[:8]}",
        system_message=sys_msg,
    ).with_model("gemini", "gemini-3-flash-preview")
    # iter 256 — hard 35s per call. If Gemini stalls, we surface a retryable
    # timeout instead of dragging the whole batch past 120s.
    try:
        raw = await asyncio.wait_for(
            chat.send_message(UserMessage(text=user_text)),
            timeout=35.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI HS classification timed out (>35s)")
    text = (raw or "").strip()
    # Strip markdown fences if the model added any
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Second-chance: extract the first {...} block (may span newlines)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise HTTPException(status_code=502, detail=f"AI returned invalid JSON: {text[:120]}")
        parsed = json.loads(m.group(0))
    hs_code = (parsed.get("hs_code") or "").strip()
    if not re.match(r"^\d{4}\.\d{2}$", hs_code):
        raise HTTPException(status_code=502, detail=f"AI returned malformed HS code: {hs_code!r}")
    return {
        "hs_code": hs_code,
        "reason": (parsed.get("reason") or "")[:200],
    }


def _sort_items_for_manifest(items: list) -> list:
    """Manifest sort order (per user spec):
      1. PVoC-required first (regulated goods go to top for customs attention)
      2. Highest declared line-value first (value_usd × qty_acquired)
      3. Heaviest first (weight_kg × qty_acquired)
    """
    def key(it):
        qty = int(it.get("qty_acquired") or 0)
        line_val = float(it.get("value_usd") or 0) * qty
        line_wt = float(it.get("weight_kg") or 0) * qty
        # False sorts before True → invert so PVoC-required comes first
        return (0 if it.get("requires_pvoc") else 1, -line_val, -line_wt)
    return sorted(items, key=key)


def _box_sort_key(name: str) -> tuple:
    """iter 255 — human-friendly box-number sort. Splits the packing unit
    name into (digit-run, alpha-run) tuples so "Box 2" < "Box 10" < "Box 12A"
    exactly the way a warehouse worker would read them.
    """
    import re as _re
    tokens = _re.findall(r"\d+|\D+", (name or "").lower())
    key = []
    for t in tokens:
        if t.isdigit():
            key.append((0, int(t)))
        else:
            key.append((1, t.strip()))
    return tuple(key) if key else ((1, ""),)


def _sort_items_by_box(items: list, packing_units: list) -> list:
    """iter 255 — Ship-manifest sort: items grouped by the box they're in,
    boxes ordered by the number written on them (Box 1 → Box 2 → Box 10),
    and un-boxed items pushed to the end.
    """
    unit_by_id = {u["id"]: u for u in (packing_units or []) if u.get("id")}

    def key(it):
        uid = it.get("packing_unit_id")
        if not uid or uid not in unit_by_id:
            return ((2,), (it.get("name") or "").lower())
        unit = unit_by_id[uid]
        return ((1,) + _box_sort_key(unit.get("name") or unit["id"]),
                (it.get("name") or "").lower())
    return sorted(items, key=key)


def _sort_items_for_invoice(items: list, packing_units: list) -> list:
    """iter 255 — Commercial invoice sort: highest line-value first, then by
    box-number. Puts the biggest customs-attention items at the top so a
    reviewer scans them first, then continues in the packer's box order.
    """
    unit_by_id = {u["id"]: u for u in (packing_units or []) if u.get("id")}

    def key(it):
        qty = int(it.get("qty_acquired") or 0)
        line_val = float(it.get("value_usd") or 0) * qty
        uid = it.get("packing_unit_id")
        if not uid or uid not in unit_by_id:
            box_key = ((2,),)
        else:
            unit = unit_by_id[uid]
            box_key = ((1,) + _box_sort_key(unit.get("name") or unit["id"]),)
        # Negative line_val → highest first. Then box order. Then item name.
        return (-line_val,) + box_key + ((it.get("name") or "").lower(),)
    return sorted(items, key=key)


def _loc_str(it: dict, packing_units: Optional[list] = None) -> str:
    parts = []
    # iter 255 — prefer the human-readable box name so the manifest shows
    # "Box 12 – Kitchen" instead of an opaque pallet id fragment.
    uid = it.get("packing_unit_id")
    if uid and packing_units:
        u = next((u for u in packing_units if u.get("id") == uid), None)
        if u and u.get("name"):
            parts.append(str(u["name"])[:40])
    if it.get("pallet_id"):
        parts.append(f"Pallet {it['pallet_id'][-4:]}")
    for k, label in (("x_cm", "X"), ("y_cm", "Y"), ("z_cm", "Z")):
        if it.get(k):
            parts.append(f"{label}={it[k]:.0f}cm")
    return " · ".join(parts) or "—"


def _resolve_group(shipment: dict, group_id: Optional[str]):
    """Resolve a ?group= query param → filtered items + group metadata."""
    items = shipment.get("items") or []
    groups = shipment.get("manifest_groups") or []
    group_meta = None
    if group_id:
        if group_id == "unassigned":
            items = [i for i in items if not i.get("manifest_group_id")]
            group_meta = {"name": "Unassigned Items", "consignee_name": "", "consignee_address": ""}
        else:
            group_meta = next((g for g in groups if g.get("id") == group_id), None)
            if not group_meta:
                raise HTTPException(status_code=404, detail="Manifest group not found")
            items = [i for i in items if i.get("manifest_group_id") == group_id]
    return items, group_meta


_PDF_STYLES = """
@page { size: A4 landscape; margin: 14mm; }
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #0f172a; }
h1 { font-size: 20px; margin: 0 0 4px 0; }
h2 { font-size: 13px; margin: 4px 0 2px 0; color: #334155; }
.meta { font-size: 10px; color: #64748b; }
.head { display: flex; justify-content: space-between; padding-bottom: 10px; border-bottom: 2px solid #0f172a; margin-bottom: 12px; }
.totals { display: flex; gap: 24px; font-size: 11px; margin-top: 6px; flex-wrap: wrap; }
.totals span { color: #64748b; }
.consignee { background: #f1f5f9; padding: 6px 10px; border-left: 3px solid #0891b2; margin-bottom: 10px; font-size: 10.5px; }
table { width: 100%; border-collapse: collapse; font-size: 10.5px; }
th, td { padding: 5px 7px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; }
th { font-size: 10px; color: #64748b; background: #f8fafc; text-transform: uppercase; }
td.n { text-align: right; font-variant-numeric: tabular-nums; }
td.hs { font-family: 'Menlo', monospace; font-size: 10.5px; }
td.loc { font-size: 10px; color: #475569; }
td.c { text-align: center; }
.cond { display: inline-block; padding: 1px 6px; border-radius: 99px; font-size: 9px; font-weight: 600; }
.cond.new { background: #dcfce7; color: #166534; }
.cond.used { background: #fef3c7; color: #92400e; }
.cond.refurbished { background: #dbeafe; color: #1e3a8a; }
.pvoc { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 700; background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
tr.pvoc-row td { background: #fef2f2; }
tfoot td { font-weight: 700; background: #f8fafc; border-top: 2px solid #0f172a; }
"""


def _normalise_pallet(data: dict) -> dict:
    """Coerce + clamp pallet fields. Used by add and update."""
    label = (data.get("label") or "").strip() or f"Pallet {datetime.now(timezone.utc).strftime('%H%M%S')}"
    return {
        "id": f"plt_{uuid.uuid4().hex[:8]}",
        "label": label[:60],
        "notes": (data.get("notes") or "")[:300],
        # Physical pallet dims (cm). Default = standard EUR pallet 120×80×15cm
        # the height field represents the stack height (so a "tall pallet stack"
        # can be e.g. 150 cm tall once items are stacked on it).
        "length_cm": max(10, float(data.get("length_cm") or 120)),
        "width_cm":  max(10, float(data.get("width_cm")  or 80)),
        "height_cm": max(5,  float(data.get("height_cm") or 150)),
        # Position within the container floor (cm from the back-left interior
        # corner). 0,0 = back-left. Used by the 2D visualizer for placement.
        "x_cm": max(0, float(data.get("x_cm") or 0)),
        "y_cm": max(0, float(data.get("y_cm") or 0)),
        "color": (data.get("color") or "")[:16],   # optional hex tag e.g. "#10b981"
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


PUBLIC_ITEM_WISHLIST_FIELDS = {
    "id", "name", "category", "qty_needed", "qty_acquired",
    "photo_url", "priority", "source_url", "source_retailer",
}
async def _persist_shipment_image(shipment_id: str, data: bytes, mime: str) -> str:
    """Persist a scanned-item photo and return a URL. iter 264 — now uses
    the shared `upload_helper.save_upload` so the cloud-first + disk-fallback
    logic lives in one place instead of being duplicated per module."""
    ext = (mime.split("/")[-1] if "/" in mime else "jpg")
    filename = f"{uuid.uuid4().hex}.{ext}"
    from upload_helper import save_upload
    return await save_upload(f"shipments/{shipment_id}/scans", filename, data, mime)


def _waybill_html(s: dict) -> str:
    """Render an HTML waybill. Used both for the printable preview AND as the
    source for the PDF route below."""
    items = s.get("items") or []
    pallets = s.get("pallets") or []
    total_value = sum((it.get("value_usd") or 0) * (it.get("qty_acquired") or 1) for it in items)
    total_weight = sum((it.get("weight_kg") or 0) * (it.get("qty_acquired") or 1) for it in items)
    by_pallet: dict = {None: []}
    for p in pallets:
        by_pallet[p["id"]] = []
    for it in items:
        by_pallet.setdefault(it.get("pallet_id"), []).append(it)

    rows = []
    for p in pallets:
        rows.append(f"<tr style='background:#eef;'><td colspan=7><strong>Pallet {p.get('label') or p['id'][:6]}</strong> · {p.get('dims_cm', {}).get('length', 100)}×{p.get('dims_cm', {}).get('width', 80)}×{p.get('dims_cm', {}).get('height', 15)} cm</td></tr>")
        for it in by_pallet.get(p["id"], []):
            rows.append(
                f"<tr><td>{it.get('name', '')}</td>"
                f"<td>{it.get('category', '')}</td>"
                f"<td>{it.get('isbn') or it.get('upc') or ''}</td>"
                f"<td>{it.get('qty_acquired', 1)}</td>"
                f"<td>${(it.get('value_usd') or 0):.2f}</td>"
                f"<td>{(it.get('weight_kg') or 0):.2f} kg</td>"
                f"<td>{p.get('label') or p['id'][:6]}</td></tr>"
            )
    # Unassigned items
    if by_pallet.get(None):
        rows.append("<tr style='background:#fee;'><td colspan=7><strong>Loose (no pallet)</strong></td></tr>")
        for it in by_pallet.get(None, []):
            rows.append(
                f"<tr><td>{it.get('name', '')}</td>"
                f"<td>{it.get('category', '')}</td>"
                f"<td>{it.get('isbn') or it.get('upc') or ''}</td>"
                f"<td>{it.get('qty_acquired', 1)}</td>"
                f"<td>${(it.get('value_usd') or 0):.2f}</td>"
                f"<td>{(it.get('weight_kg') or 0):.2f} kg</td>"
                f"<td>—</td></tr>"
            )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Waybill — {s.get('name', '')}</title>
<style>
body {{ font-family: Inter, system-ui, sans-serif; margin: 24px; color: #111; }}
h1 {{ margin-bottom: 4px; }}
.subtitle {{ color: #555; margin-bottom: 16px; font-size: 13px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
th {{ background: #fafafa; }}
.totals {{ margin-top: 18px; font-size: 13px; }}
.totals strong {{ display: inline-block; min-width: 140px; }}
</style></head><body>
<h1>Waybill / Manifest</h1>
<p class="subtitle">{s.get('name', 'Untitled shipment')} · {len(items)} items · {len(pallets)} pallets · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
<p class="subtitle"><strong>Origin:</strong> {s.get('origin', '—')} · <strong>Destination:</strong> {s.get('destination', '—')} · <strong>Ship date:</strong> {s.get('ship_date') or '—'}</p>
<table>
<thead><tr><th>Item</th><th>Category</th><th>ISBN / UPC</th><th>Qty</th><th>Unit value</th><th>Weight</th><th>Pallet</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<div class="totals">
<p><strong>Total items:</strong> {sum((it.get('qty_acquired') or 1) for it in items)}</p>
<p><strong>Total value:</strong> ${total_value:.2f}</p>
<p><strong>Total weight:</strong> {total_weight:.2f} kg</p>
</div>
</body></html>"""


# ============================================================
# iter223 — Polymorphic packing units, passengers/suitcases, AI tracking
# ============================================================

# Standard packing-unit dimension presets — populated from real freight specs.
PACKING_PRESETS = {
    "eur_pallet":   {"L_cm": 120, "W_cm": 80,  "H_cm": 14.5, "cap_kg": 1500, "label": "EUR pallet (EPAL)"},
    "us_pallet":    {"L_cm": 122, "W_cm": 102, "H_cm": 14.5, "cap_kg": 1360, "label": "US pallet (48\"×40\")"},
    "large_box":    {"L_cm": 60,  "W_cm": 45,  "H_cm": 40,   "cap_kg": 30,   "label": "Large moving box"},
    "medium_box":   {"L_cm": 45,  "W_cm": 35,  "H_cm": 30,   "cap_kg": 20,   "label": "Medium box"},
    "small_box":    {"L_cm": 30,  "W_cm": 25,  "H_cm": 20,   "cap_kg": 10,   "label": "Small box"},
    "plastic_tote": {"L_cm": 70,  "W_cm": 45,  "H_cm": 40,   "cap_kg": 40,   "label": "Plastic tote (54L)"},
    "crate_wood":   {"L_cm": 100, "W_cm": 60,  "H_cm": 60,   "cap_kg": 200,  "label": "Wooden crate"},
    "banana_box":   {"L_cm": 50,  "W_cm": 40,  "H_cm": 25,   "cap_kg": 18,   "label": "Banana box"},
    # iter 251 — round bin. 24" diameter ≈ 61 cm. Height a common 30" (≈76 cm)
    # heavy-duty utility bin. We still expose L/W (both = diameter) so the
    # existing rectangular packing solver keeps working; the visualiser reads
    # the `shape:"cylinder"` metadata to draw a cylinder in 3D instead.
    "round_bin_24": {"L_cm": 61,  "W_cm": 61,  "H_cm": 76,   "cap_kg": 45,   "label": "Round bin (24\" ø)", "shape": "cylinder", "diameter_cm": 61},
    "suitcase_lg":  {"L_cm": 76,  "W_cm": 51,  "H_cm": 31,   "cap_kg": 23,   "label": "Large suitcase (28\")"},
    "suitcase_md":  {"L_cm": 66,  "W_cm": 46,  "H_cm": 27,   "cap_kg": 23,   "label": "Medium suitcase (24\")"},
    "carry_on":     {"L_cm": 55,  "W_cm": 40,  "H_cm": 22,   "cap_kg": 10,   "label": "Carry-on (22\")"},
    "duffel":       {"L_cm": 76,  "W_cm": 36,  "H_cm": 36,   "cap_kg": 20,   "label": "Duffel bag"},
}

# `bin` is a new type — round/cylindrical. Solver treats it as a bounding
# box; visualiser renders as a cylinder using preset.shape or unit.shape.
VALID_UNIT_TYPES = {"pallet", "box", "tote", "crate", "bin", "suitcase", "carry_on", "duffel"}
VALID_MODES = {"container", "airport"}

