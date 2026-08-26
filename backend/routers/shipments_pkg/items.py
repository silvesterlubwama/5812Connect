"""Item CRUD, HS-code classification, manifest / commercial-invoice PDFs, bulk import."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import re
import os as _os
from deps import db, logger, _audit, require_admin
from ._common import (
    _normalise_item,
    _shipment_units,
    _add_or_merge_item,
    _persist_shipment_image,
    _classify_hs_with_ai,
    _sort_items_for_manifest,
    _sort_items_by_box,
    _sort_items_for_invoice,
    _loc_str,
    _resolve_group,
    _PDF_STYLES,
    VALID_PRIORITIES,
)

router = APIRouter(prefix="/api", tags=["shipments"])


# ============================================================
# iter228 — Admin-side item scan (same UX as public /scan-item
# but auth via require_admin, no PIN gate). Mirrors public logic
# so a staff member can bulk-scan items from the back office.
# ============================================================

@router.post("/shipments/{shipment_id}/scan-item")
async def admin_scan_item(
    shipment_id: str,
    images: List[UploadFile] = File(default=[]),
    isbn: Optional[str] = None,
    upc: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Identify a shipment item from up to 3 photos and/or a barcode.
    Returns a candidate dict (NOT yet persisted). Admin equivalent of
    /api/public/shipments/{token}/scan-item."""
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "id": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if not images and not isbn and not upc:
        raise HTTPException(status_code=400, detail="Provide at least one image, ISBN, or UPC")

    enriched: dict = {}

    # 1) Barcode lookups (cheap + definitive)
    if isbn:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=6) as cli:
                r = await cli.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn.strip()}")
                if r.status_code == 200:
                    js = r.json()
                    if js.get("totalItems", 0) > 0:
                        v = js["items"][0]["volumeInfo"]
                        enriched = {
                            "name": v.get("title") or "",
                            "author": ", ".join(v.get("authors") or []),
                            "publisher": v.get("publisher") or "",
                            "category": (v.get("categories") or ["Books"])[0],
                            "isbn": isbn.strip(),
                            "photo_url": ((v.get("imageLinks") or {}).get("thumbnail") or "").replace("http://", "https://"),
                            "weight_kg": 0.3,
                            "dims_cm": {"length": 20, "width": 13, "height": 2},
                            "value_usd": float(((js["items"][0].get("saleInfo") or {}).get("listPrice") or {}).get("amount") or 12.0),
                            "ai_identified": False,
                            "source": "google_books",
                        }
        except Exception as e:
            logger.warning(f"[admin_scan_item] google books lookup failed: {e}")

    if upc and not enriched:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=6) as cli:
                r = await cli.get(f"https://world.openfoodfacts.org/api/v2/product/{upc.strip()}.json")
                if r.status_code == 200:
                    js = r.json()
                    if js.get("status") == 1:
                        p = js.get("product") or {}
                        enriched = {
                            "name": p.get("product_name") or p.get("generic_name") or "",
                            "category": (p.get("categories", "").split(",") or ["Food"])[0].strip()[:60],
                            "upc": upc.strip(),
                            "photo_url": p.get("image_front_url") or "",
                            "weight_kg": 0.5,
                            "dims_cm": {"length": 10, "width": 10, "height": 20},
                            "value_usd": 4.0,
                            "ai_identified": False,
                            "source": "openfoodfacts",
                        }
        except Exception as e:
            logger.warning(f"[admin_scan_item] openfoodfacts lookup failed: {e}")

    # 2) AI vision fallback
    image_urls: List[str] = []
    image_bytes_list: List[bytes] = []
    if images:
        for img in images[:3]:
            data = await img.read()
            if not data or len(data) > 8_000_000:
                continue
            image_bytes_list.append(data)
            try:
                url = await _persist_shipment_image(shipment_id, data, img.content_type or "image/jpeg")
                image_urls.append(url)
            except Exception:
                pass

    if not enriched and image_bytes_list:
        api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
        if api_key:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
                import tempfile
                fd, tmp = tempfile.mkstemp(suffix=".jpg")
                with _os.fdopen(fd, "wb") as fh:
                    fh.write(image_bytes_list[0])
                sys_msg = (
                    "You identify physical items from photos for a charity shipment inventory. "
                    "Items can be ANYTHING a humanitarian container carries — books, clothing, "
                    "shoes, food, toys, medical supplies, electronics, household goods, furniture, "
                    "tools, construction, school supplies, agriculture, sports, toiletries, baby "
                    "gear, bicycles. Read any barcodes, ISBNs, titles, or text on the item. "
                    "Cross-reference Amazon/Walmart/eBay/Target/Home Depot/Costco/IKEA listings "
                    "for accurate dimensions, weight and USD retail price. "
                    "Output STRICT JSON: {\"name\":\"\",\"category\":\"\",\"author\":\"\",\"publisher\":\"\",\"isbn\":\"\",\"upc\":\"\",\"weight_kg\":0.5,\"dims_cm\":{\"length\":20,\"width\":13,\"height\":5},\"value_usd\":5.0,\"source\":\"\",\"confidence\":\"high|medium|low\"}. "
                    "No markdown fences."
                )
                chat = LlmChat(
                    api_key=api_key,
                    session_id=f"admin_scan_{uuid.uuid4().hex[:6]}",
                    system_message=sys_msg,
                ).with_model("gemini", "gemini-3-flash-preview")
                msg = UserMessage(
                    text="Identify this item. Return strict JSON.",
                    file_contents=[FileContentWithMimeType(file_path=tmp, mime_type="image/jpeg")],
                )
                raw = await chat.send_message(msg)
                s_text = (raw or "").strip().strip("`")
                if s_text.lower().startswith("json"):
                    s_text = s_text[4:].strip()
                first, last = s_text.find("{"), s_text.rfind("}")
                if first >= 0 and last > first:
                    s_text = s_text[first:last + 1]
                import json as _json
                parsed = _json.loads(s_text)
                enriched = {
                    "name": parsed.get("name") or "",
                    "category": parsed.get("category") or "Other",
                    "author": parsed.get("author") or "",
                    "publisher": parsed.get("publisher") or "",
                    "isbn": parsed.get("isbn") or "",
                    "upc": parsed.get("upc") or "",
                    "weight_kg": float(parsed.get("weight_kg") or 0.5),
                    "dims_cm": parsed.get("dims_cm") or {"length": 20, "width": 13, "height": 5},
                    "value_usd": float(parsed.get("value_usd") or 5.0),
                    "ai_identified": True,
                    "ai_confidence": parsed.get("confidence") or "low",
                    "source": "ai_vision",
                }
                try:
                    _os.remove(tmp)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[admin_scan_item] AI scan failed: {e}")

    # 3) Fallback minimum shape
    if not enriched:
        enriched = {
            "name": "Unidentified item", "category": "Other", "ai_identified": False,
            "ai_confidence": "low", "source": "manual",
            "weight_kg": 0.5, "dims_cm": {"length": 20, "width": 20, "height": 10}, "value_usd": 5.0,
        }
    enriched["image_urls"] = image_urls
    enriched["photo_url"] = enriched.get("photo_url") or (image_urls[0] if image_urls else "")
    enriched["scanned_by"] = current_user.get("name", "admin")
    enriched["scanned_at"] = datetime.now(timezone.utc).isoformat()
    return enriched


@router.post("/shipments/{shipment_id}/items")
async def add_item(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    units = await _shipment_units(shipment_id)
    item = _normalise_item(data, units)
    return await _add_or_merge_item(shipment_id, item)

@router.put("/shipments/{shipment_id}/items/{item_id}")
async def update_item(shipment_id: str, item_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "category", "qty_needed", "qty_acquired", "weight_kg",
               "dims_cm", "photo_url", "image_urls", "value_usd", "notes", "priority",
               "pallet_id", "parent_id", "container_type", "isbn", "upc",
               "author", "publisher", "ai_identified",
               "x_cm", "y_cm", "z_cm",
               # iter 252 — position on the container floor for loose items
               "floor_x_cm", "floor_y_cm",
               # iter 254 — rotation around vertical axis (degrees)
               "rotation_deg",
               "hs_code", "hs_code_reason", "condition",
               "manifest_group_id", "requires_pvoc", "pvoc_reason",
               "packing_unit_id", "suitcase_id", "passenger_id"}
    set_ops = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        # Clamp numeric fields just like create
        if k in ("qty_needed",):
            set_ops[f"items.$.{k}"] = max(1, int(v or 1))
        elif k in ("qty_acquired",):
            set_ops[f"items.$.{k}"] = max(0, int(v or 0))
        elif k in ("weight_kg", "value_usd"):
            set_ops[f"items.$.{k}"] = max(0, float(v or 0))
        elif k in ("x_cm", "y_cm", "z_cm", "floor_x_cm", "floor_y_cm"):
            # iter 254 — allow negative floor coords so items can be
            # positioned past container walls in full-screen edit mode.
            set_ops[f"items.$.{k}"] = float(v or 0)
        elif k in ("rotation_deg",):
            # iter 254 — rotation around the vertical (Y) axis in degrees.
            # Normalised to 0-360.
            set_ops[f"items.$.{k}"] = float(v or 0) % 360
        elif k == "priority":
            p = (v or "normal").lower()
            set_ops[f"items.$.{k}"] = p if p in VALID_PRIORITIES else "normal"
        elif k == "requires_pvoc":
            set_ops[f"items.$.{k}"] = bool(v)
        elif k == "manifest_group_id":
            # Empty string / null → clear the group
            set_ops[f"items.$.{k}"] = v if v else None
        else:
            set_ops[f"items.$.{k}"] = v
    set_ops["items.$.updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        {"$set": set_ops},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/items/{item_id}")
async def delete_item(shipment_id: str, item_id: str, current_user: dict = Depends(require_admin)):
    r = await db.shipments.update_one(
        {"id": shipment_id}, {"$pull": {"items": {"id": item_id}}}
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": True}


# ============================================================
# iter 249 — Batch box-photo scanning. Different UX from
# /scan-item: this endpoint takes photos of ENTIRE labeled
# boxes (with box numbers + item lists written in marker)
# and:
#   1. reads the box number + items from each photo
#   2. matches box_number to existing packing_units by name
#      (case-insensitive substring), or creates a new one
#   3. for each item on the box, either links an existing
#      shipment item to that packing_unit (fuzzy name match)
#      or adds a fresh item
#   4. boxes marked "Personal Items" collapse into ONE
#      "Household Personal Item" line
#   5. estimates a conservative low-average USD value when
#      the AI can't pull an on-item price
# ============================================================

# Low-average USD fallback prices for the common categories a
# 40' humanitarian container carries. Deliberately conservative
# (bottom of the range) so a customs manifest never over-values.
_LOW_AVG_VALUE_USD = {
    "clothing": 4.0,
    "shoes": 6.0,
    "book": 3.0,
    "books": 3.0,
    "toy": 5.0,
    "toys": 5.0,
    "medical": 8.0,
    "kitchen": 6.0,
    "household": 5.0,
    "electronics": 15.0,
    "personal": 5.0,
    "school": 4.0,
    "food": 3.0,
    "furniture": 30.0,
    "sport": 8.0,
    "sports": 8.0,
    "tool": 12.0,
    "tools": 12.0,
    "linen": 5.0,
    "linens": 5.0,
    "bedding": 8.0,
    "baby": 5.0,
    "other": 5.0,
}


# iter 255 — Typical per-unit weight (kg) for common household categories.
# Kept conservative so we don't inflate container-weight totals. Used only
# when neither the on-box label nor the AI vision output provides a weight.
_LOW_AVG_WEIGHT_KG = {
    "clothing": 0.4,
    "shoes": 0.7,
    "book": 0.6,
    "books": 0.6,
    "toy": 0.5,
    "toys": 0.5,
    "medical": 0.3,
    "kitchen": 1.5,
    "household": 1.0,
    "electronics": 2.5,
    "personal": 0.5,
    "school": 0.5,
    "food": 0.8,
    "furniture": 15.0,
    "sport": 1.5,
    "sports": 1.5,
    "tool": 1.8,
    "tools": 1.8,
    "linen": 0.7,
    "linens": 0.7,
    "bedding": 2.5,
    "baby": 0.4,
    "other": 0.8,
}


def _estimate_value_usd(name: str, category: str, provided: Optional[float]) -> float:
    """Use the AI-supplied value if any, otherwise map to `_LOW_AVG_VALUE_USD`
    on the coarsest bucket that matches the item's name or category. Falls
    back to a very safe $5.00 so no line ever ships with $0 value."""
    if provided and provided > 0:
        return round(float(provided), 2)
    key = ((category or "") + " " + (name or "")).lower()
    for k, v in _LOW_AVG_VALUE_USD.items():
        if k in key:
            return v
    return 5.0


def _estimate_weight_kg(name: str, category: str, provided: Optional[float]) -> float:
    """iter 255 — mirror of `_estimate_value_usd` for line weight. Uses the
    AI-supplied weight if any, otherwise the low-average bucket. Fallback
    of 0.8 kg keeps the manifest realistic without inflating totals."""
    if provided and provided > 0:
        return round(float(provided), 3)
    key = ((category or "") + " " + (name or "")).lower()
    for k, v in _LOW_AVG_WEIGHT_KG.items():
        if k in key:
            return v
    return 0.8


@router.post("/shipments/{shipment_id}/scan-boxes")
async def scan_boxes(
    shipment_id: str,
    images: List[UploadFile] = File(...),
    current_user: dict = Depends(require_admin),
):
    """Scan one or more full-box photos and auto-populate the shipment.

    All items + packing_units created (or updated) here are tagged with the
    same `scan_run_id`, so the whole batch can be reverted in one call via
    `POST .../scan-runs/{run_id}/revert`. A summary of the run is persisted
    in `db.shipment_scan_runs` for the "recent scans" UI + undo button.

    When the SAME box_number shows up in multiple photos of the batch (front,
    side, list — a very common volunteer flow), they auto-collapse onto ONE
    packing_unit, so 3 photos of "Box 12" don't produce 3 boxes. Every photo's
    URL still lands in `packing_unit.photos[]` for the gallery UI.
    """
    if not images:
        raise HTTPException(status_code=400, detail="Upload at least one photo")
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "id": 1, "items": 1, "packing_units": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")

    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI scan unavailable (no LLM key)")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI scan unavailable: {e}")

    import tempfile
    import json as _json

    scan_run_id = f"scn_{uuid.uuid4().hex[:10]}"
    boxes_created = boxes_matched = items_added = items_linked = 0
    errors: list = []
    results: list = []
    created_item_ids: list = []           # for undo — pull these
    created_unit_ids: list = []           # for undo — pull these
    linked_item_updates: list = []        # for undo — reverse packing_unit_id + qty_acquired

    # A stable lookup for existing packing units by name — case-insensitive
    # substring match so "Box 12" written in marker matches "Box 12 – Kitchen".
    def _match_box(name_or_number: str, current_units: list) -> Optional[dict]:
        if not name_or_number:
            return None
        needle = name_or_number.strip().lower()
        for u in current_units:
            nm = (u.get("name") or "").lower()
            if needle == nm:
                return u
            # If the label from the photo is a bare number (e.g. "12"), match
            # any unit whose name contains that token.
            if needle.isdigit() and (f" {needle}" in f" {nm} " or nm.endswith(f" {needle}") or nm == needle):
                return u
        return None

    # Fuzzy shipment-item lookup — same-category-agnostic. Case-insensitive
    # substring both ways so "T-shirts (mens)" matches "mens t shirts".
    def _match_item(name: str, current_items: list) -> Optional[dict]:
        if not name:
            return None
        n = name.strip().lower()
        for it in current_items:
            existing = (it.get("name") or "").strip().lower()
            if not existing:
                continue
            if existing == n or (len(n) >= 4 and (n in existing or existing in n)):
                return it
        return None

    # Prompt Gemini to be strict about what it returns. One JSON object per photo.
    SYS_PROMPT = (
        "You are cataloguing photos of labeled cardboard boxes packed for a shipping container. "
        "Each photo shows one box (occasionally more) with either:\n"
        "  • A box number and a list of items written in marker (e.g. 'Box 12: shoes, kids clothes')\n"
        "  • A 'Personal Items' / 'Household' / 'Personal Effects' label\n"
        "  • Loose items visible with no box\n\n"
        "Return STRICT JSON — no markdown, no prose:\n"
        "{\n"
        '  "box_number": "12" | null,        // exact string on the box, digits+letters as written\n'
        '  "box_label":  "Kitchen" | null,   // any additional label (Kitchen, Books, etc.)\n'
        '  "is_personal": true|false,        // true iff the box is marked personal / household / personal effects\n'
        '  "items": [\n'
        '    {"name":"Kids shoes","qty":1,"category":"shoes","estimated_value_usd":6,"estimated_weight_kg":0.6}\n'
        "  ],\n"
        '  "confidence": "high"|"medium"|"low",\n'
        '  "notes": "anything worth flagging"\n'
        "}\n"
        "Rules:\n"
        "- Read handwriting carefully; if unsure, still return best guess but drop confidence to 'low'.\n"
        "- iter 255 — Personal / household boxes MUST still list every item individually (shampoo, towels, plates, ...). Do NOT collapse into one 'Personal Item' row. The customs manifest needs the individual lines.\n"
        "- For qty, use the count written on the box; default 1 if none.\n"
        "- estimated_value_usd should be a conservative LOW-AVERAGE US retail price for that category, or null.\n"
        "- estimated_weight_kg is the typical per-unit weight in kilograms for that item (e.g. 0.4 for a t-shirt, 0.6 for a book, 1.5 for a kitchen appliance), or null.\n"
        "- If no box number is visible, set box_number=null."
    )

    for idx, img in enumerate(images[:20]):  # cap so a rogue upload can't hammer the LLM
        data = await img.read()
        if not data:
            errors.append({"photo_index": idx, "error": "Empty upload"})
            continue
        if len(data) > 10_000_000:
            errors.append({"photo_index": idx, "error": "Photo > 10 MB"})
            continue
        mime = (img.content_type or "image/jpeg").lower()
        if not mime.startswith("image/"):
            errors.append({"photo_index": idx, "error": "Not an image"})
            continue

        photo_url = None
        try:
            photo_url = await _persist_shipment_image(shipment_id, data, mime)
        except Exception:
            pass

        # Send to Gemini
        try:
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            with _os.fdopen(fd, "wb") as fh:
                fh.write(data)
            chat = LlmChat(
                api_key=api_key,
                session_id=f"box_scan_{shipment_id}_{uuid.uuid4().hex[:6]}",
                system_message=SYS_PROMPT,
            ).with_model("gemini", "gemini-3-flash-preview")
            msg = UserMessage(
                text="Identify the box + items in this photo. Return strict JSON per the schema.",
                file_contents=[FileContentWithMimeType(file_path=tmp, mime_type=mime)],
            )
            raw = await chat.send_message(msg)
            try:
                _os.remove(tmp)
            except Exception:
                pass
            s_text = (raw or "").strip().strip("`")
            if s_text.lower().startswith("json"):
                s_text = s_text[4:].strip()
            first, last = s_text.find("{"), s_text.rfind("}")
            if first >= 0 and last > first:
                s_text = s_text[first:last + 1]
            parsed = _json.loads(s_text)
        except Exception as e:
            errors.append({"photo_index": idx, "error": f"AI parse failed: {str(e)[:120]}"})
            continue

        # ── Reload current shipment state so we see units/items added during
        # earlier photos in this SAME batch. Cheap — one round-trip per photo.
        s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "id": 1, "items": 1, "packing_units": 1})
        cur_units = s.get("packing_units") or []
        cur_items = s.get("items") or []

        box_number = (parsed.get("box_number") or "").strip() or None
        box_label = (parsed.get("box_label") or "").strip() or None
        is_personal = bool(parsed.get("is_personal"))

        # ── Resolve / create the packing unit for this photo ──────────
        target_unit = None
        if box_number:
            target_unit = _match_box(box_number, cur_units)
            if not target_unit:
                # New box — use a standard mid-size cardboard preset. Name it
                # after what's on the box so future scans match.
                name_parts = [f"Box {box_number}"]
                if box_label:
                    name_parts.append(box_label)
                new_unit = {
                    "id": f"pku_{uuid.uuid4().hex[:8]}",
                    "type": "box",
                    "name": " – ".join(name_parts)[:80],
                    "preset_key": "medium_box",
                    "L_cm": 60.0, "W_cm": 40.0, "H_cm": 40.0,
                    "weight_capacity_kg": 20.0,
                    "color": "#94a3b8",
                    "parent_id": None,
                    "floor_x_cm": 0.0, "floor_y_cm": 0.0,
                    "notes": f"Auto-created from box-photo scan on {datetime.now(timezone.utc).date().isoformat()}",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": current_user["id"],
                    "photo_url": photo_url,
                    # iter 250 — every scan-scoped box carries the run id + a
                    # multi-photo gallery so the "Box Photo Gallery" UI can
                    # render every angle a volunteer uploaded.
                    "photos": [photo_url] if photo_url else [],
                    "scan_run_id": scan_run_id,
                    "auto_scanned": True,
                }
                await db.shipments.update_one({"id": shipment_id}, {"$push": {"packing_units": new_unit}})
                target_unit = new_unit
                boxes_created += 1
                created_unit_ids.append(new_unit["id"])
            else:
                # iter 255c — user rule: only keep ONE photo per matched box
                # per scan run (packers often upload the same box from
                # multiple angles). Delete the just-uploaded file we don't
                # need and skip the $addToSet so `packing_units.photos`
                # doesn't balloon. If the user wants multiple angles, they
                # can attach them manually via the per-box gallery.
                if photo_url and photo_url.startswith("/api/uploads/"):
                    try:
                        import os as __os
                        __os.remove("/app/backend" + photo_url[4:])
                    except Exception:
                        pass
                # Only counts as a "matched box" the FIRST time in this run.
                # Repeat photos of a box already-merged-this-run are silent.
                if target_unit["id"] not in created_unit_ids:
                    boxes_matched += 1

        # ── Parse the items from the AI response ─────────────────────
        photo_result_items = []
        raw_items = parsed.get("items") or []
        # iter 255 — Personal boxes are no longer collapsed into a single
        # "Household Personal Item" row. The AI now lists every item and
        # each one is either matched or added individually so the customs
        # manifest and invoice show real line items with per-item weights.
        # If the AI failed to return any items for a personal box, fall back
        # to the single "Household Personal Item" line so we don't lose the
        # box entirely.
        if is_personal and not raw_items:
            raw_items = [{"name": "Household Personal Item", "qty": 1,
                          "category": "personal",
                          "estimated_value_usd": 5,
                          "estimated_weight_kg": 0.5}]

        for row in raw_items:
            if not isinstance(row, dict):
                continue
            item_name = (row.get("name") or "").strip()
            if not item_name:
                continue
            qty = max(1, int(row.get("qty") or 1))
            category = (row.get("category") or "Other").strip()[:60]
            value = _estimate_value_usd(item_name, category, row.get("estimated_value_usd"))
            weight = _estimate_weight_kg(item_name, category, row.get("estimated_weight_kg"))

            existing = _match_item(item_name, cur_items)
            if existing:
                # Link to the box + bump qty_acquired. Track the delta so a
                # subsequent /revert can undo it precisely (subtract qty back
                # off + null the packing_unit_id we set here).
                set_ops = {"items.$.updated_at": datetime.now(timezone.utc).isoformat()}
                prior_unit = existing.get("packing_unit_id")
                if target_unit:
                    set_ops["items.$.packing_unit_id"] = target_unit["id"]
                await db.shipments.update_one(
                    {"id": shipment_id, "items.id": existing["id"]},
                    {"$set": set_ops, "$inc": {"items.$.qty_acquired": qty}},
                )
                items_linked += 1
                linked_item_updates.append({
                    "item_id": existing["id"],
                    "qty_delta": qty,
                    "prior_packing_unit_id": prior_unit,
                    "new_packing_unit_id": target_unit["id"] if target_unit else None,
                })
                photo_result_items.append({
                    "item_id": existing["id"], "name": existing.get("name"),
                    "action": "linked", "qty": qty, "value_usd": value,
                })
            else:
                new_item = _normalise_item({
                    "name": item_name[:120],
                    "category": category,
                    "qty_needed": qty,
                    "qty_acquired": qty,
                    "priority": "normal",
                    "packing_unit_id": target_unit["id"] if target_unit else None,
                    "value_usd": value,
                    # iter 255 — carry an AI/preset-based per-unit weight so
                    # the customs manifest & container-weight totals aren't
                    # zero for scan-added items. `_estimate_weight_kg` uses
                    # the AI hint if provided, otherwise the category preset.
                    "weight_kg": weight,
                    "ai_identified": True,
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                    "notes": f"Auto-added from box photo{' ' + box_number if box_number else ''}",
                })
                # iter 250 — tag the item with the run id for surgical undo.
                new_item["scan_run_id"] = scan_run_id
                await db.shipments.update_one({"id": shipment_id}, {"$push": {"items": new_item}})
                items_added += 1
                created_item_ids.append(new_item["id"])
                photo_result_items.append({
                    "item_id": new_item["id"], "name": new_item["name"],
                    "action": "added", "qty": qty, "value_usd": value,
                })

        results.append({
            "photo_index": idx,
            "photo_url": photo_url,
            "box_number": box_number,
            "box_label": box_label,
            "is_personal": is_personal,
            "matched_box_id": target_unit["id"] if target_unit else None,
            "matched_box_name": target_unit["name"] if target_unit else None,
            "confidence": parsed.get("confidence") or "medium",
            "notes": (parsed.get("notes") or "")[:200],
            "items": photo_result_items,
        })

    await _audit(current_user["id"], "scan_boxes", "shipment", shipment_id,
                 {"photos": len(images), "items_added": items_added,
                  "items_linked": items_linked, "boxes_created": boxes_created,
                  "scan_run_id": scan_run_id})

    # iter 250 — persist the scan run so the "recent scans" list + undo button
    # have everything they need. Small footprint: just the ids we touched.
    run_doc = {
        "id": scan_run_id,
        "shipment_id": shipment_id,
        "photos_processed": len(images),
        "boxes_created": boxes_created,
        "boxes_matched": boxes_matched,
        "items_added": items_added,
        "items_linked": items_linked,
        "errors": errors,
        "created_item_ids": created_item_ids,
        "created_unit_ids": created_unit_ids,
        "linked_item_updates": linked_item_updates,
        "reverted": False,
        "results_summary": [{"photo_index": r["photo_index"], "box_number": r.get("box_number"),
                             "is_personal": r.get("is_personal"), "confidence": r.get("confidence"),
                             "matched_box_id": r.get("matched_box_id"),
                             "item_count": len(r.get("items") or [])} for r in results],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name"),
    }
    await db.shipment_scan_runs.insert_one(run_doc)

    # iter 255c — Persist the last unsaved scan result on the shipment as
    # `scan_draft` so a refresh, tab switch, or network blip doesn't wipe a
    # 20-photo review. Frontend re-hydrates the box-scan dialog from this on
    # load. Cleared by DELETE /shipments/{id}/scan-draft when user hits Done.
    draft = {
        "scan_run_id": scan_run_id,
        "boxes_created": boxes_created,
        "boxes_matched": boxes_matched,
        "items_added": items_added,
        "items_linked": items_linked,
        "errors": errors,
        "results": results,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.shipments.update_one({"id": shipment_id}, {"$set": {"scan_draft": draft}})

    return {
        "scan_run_id": scan_run_id,
        "photos_processed": len(images),
        "boxes_created": boxes_created,
        "boxes_matched": boxes_matched,
        "items_added": items_added,
        "items_linked": items_linked,
        "errors": errors,
        "results": results,
    }


@router.delete("/shipments/{shipment_id}/scan-draft")
async def clear_scan_draft(shipment_id: str, current_user: dict = Depends(require_admin)):
    """iter 255c — Frontend calls this when the user hits Done on the box-scan
    dialog, so subsequent shipment loads don't re-open a stale draft."""
    await db.shipments.update_one(
        {"id": shipment_id}, {"$unset": {"scan_draft": ""}},
    )
    return {"cleared": True}


@router.get("/shipments/{shipment_id}/scan-runs")
async def list_scan_runs(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Recent scan runs for a shipment (newest first, capped at 20). Feeds the
    "recent scans" list on the shipment detail + the Undo button."""
    rows = await db.shipment_scan_runs.find(
        {"shipment_id": shipment_id}, {"_id": 0},
    ).sort("created_at", -1).limit(20).to_list(20)
    return rows


@router.post("/shipments/{shipment_id}/scan-runs/{run_id}/revert")
async def revert_scan_run(shipment_id: str, run_id: str, current_user: dict = Depends(require_admin)):
    """Reverse a scan run:
      • Pull every item created by this run
      • Pull every packing_unit created by this run
      • For items that were LINKED (not added), subtract the qty delta this
        run added, and restore the prior packing_unit_id
    Marks the run `reverted: true` so it can't be reverted twice.
    """
    run = await db.shipment_scan_runs.find_one({"id": run_id, "shipment_id": shipment_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Scan run not found")
    if run.get("reverted"):
        raise HTTPException(status_code=400, detail="This run has already been reverted")

    # 1) Reverse the "linked" updates — undo qty bumps + packing_unit_id sets.
    #    Prior packing_unit_id is restored (may be None, which unsets the field
    #    in practice — Mongo stores null which the visualiser reads as "loose").
    for upd in run.get("linked_item_updates") or []:
        set_ops = {"items.$.packing_unit_id": upd.get("prior_packing_unit_id")}
        await db.shipments.update_one(
            {"id": shipment_id, "items.id": upd["item_id"]},
            {"$set": set_ops, "$inc": {"items.$.qty_acquired": -int(upd.get("qty_delta") or 0)}},
        )

    # 2) Pull the items + units the run created outright.
    if run.get("created_item_ids"):
        await db.shipments.update_one(
            {"id": shipment_id},
            {"$pull": {"items": {"id": {"$in": run["created_item_ids"]}}}},
        )
    if run.get("created_unit_ids"):
        await db.shipments.update_one(
            {"id": shipment_id},
            {"$pull": {"packing_units": {"id": {"$in": run["created_unit_ids"]}}}},
        )
        # Any items that were placed INTO a now-deleted box need their
        # packing_unit_id cleared so they don't dangle. Cheap loop — usually
        # < 50 items per run.
        for uid in run["created_unit_ids"]:
            await db.shipments.update_one(
                {"id": shipment_id, "items.packing_unit_id": uid},
                {"$set": {"items.$[e].packing_unit_id": None}},
                array_filters=[{"e.packing_unit_id": uid}],
            )

    await db.shipment_scan_runs.update_one(
        {"id": run_id},
        {"$set": {"reverted": True, "reverted_at": datetime.now(timezone.utc).isoformat(),
                  "reverted_by": current_user["id"]}},
    )
    await _audit(current_user["id"], "revert_scan", "shipment", shipment_id, {"scan_run_id": run_id})
    return {"reverted": True, "scan_run_id": run_id,
            "items_removed": len(run.get("created_item_ids") or []),
            "boxes_removed": len(run.get("created_unit_ids") or []),
            "items_unlinked": len(run.get("linked_item_updates") or [])}



# iter 256 — Prune over-pledged endpoint removed at user request. Legacy
# tests still reference /prune-over-pledged; those tests will 404 and can be
# retired on next cleanup pass.


# ─── Item photo upload + link-to-size estimation ────────────────

from fastapi import UploadFile, File  # noqa: E402


@router.post("/shipments/{shipment_id}/items/{item_id}/photo")
async def upload_item_photo(
    shipment_id: str, item_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin),
):
    """Upload a product photo for an item. Cloud-storage with disk fallback,
    same pattern as child-extras / receipts."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo must be under 5 MB")
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    unique = f"{shipment_id}-{item_id}-{uuid.uuid4().hex[:6]}.{ext}"
    file_url = None
    try:
        from storage import put_object
        result = put_object(f"shipment-items/{unique}", data, file.content_type)
        file_url = result.get("url", f"/api/storage/shipment-items/{unique}")
    except Exception as e:
        logger.warning(f"Cloud put failed, saving locally: {e}")
        import os as _os
        _os.makedirs("/app/backend/uploads/shipment-items", exist_ok=True)
        with open(f"/app/backend/uploads/shipment-items/{unique}", "wb") as fh:
            fh.write(data)
        file_url = f"/api/uploads/shipment-items/{unique}"
    await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        {"$set": {"items.$.photo_url": file_url}},
    )
    return {"photo_url": file_url}


async def _derive_shape3d_for_item(shipment_id: str, item: dict, current_user: dict) -> dict:
    """Core Gemini classification for a single item. Returns the persisted
    shape3d dict. Raises HTTPException on missing photo / AI failure so both
    the single-item and batch endpoints can surface a consistent error.
    """
    item_id = item["id"]
    photo_url = item.get("photo_url") or ((item.get("image_urls") or [None])[0])
    if not photo_url:
        raise HTTPException(status_code=400, detail="Item has no photo yet")

    # Fetch the image bytes. Support both local (/api/uploads/*) and cloud URLs.
    try:
        if photo_url.startswith("/api/uploads/"):
            local_path = "/app/backend" + photo_url[4:]  # strip /api → /uploads/…
            with open(local_path, "rb") as fh:
                data = fh.read()
            mime = "image/jpeg"
        else:
            import httpx
            async with httpx.AsyncClient(timeout=15) as hc:
                resp = await hc.get(photo_url)
                resp.raise_for_status()
                data = resp.content
                mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch item photo: {str(e)[:100]}")

    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI unavailable (no LLM key)")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI unavailable: {e}")

    import tempfile
    import json as _json

    fd, tmp = tempfile.mkstemp(suffix=".jpg")
    with _os.fdopen(fd, "wb") as fh:
        fh.write(data)

    dims = item.get("dims_cm") or {}
    fallback_L = float(dims.get("length") or 30)
    fallback_W = float(dims.get("width") or 30)
    fallback_H = float(dims.get("height") or 30)

    SYS = (
        "You classify a household / appliance item photo into a rough 3D shape primitive "
        "so a container packing app can draw something better than a plain box. Output STRICT JSON:\n"
        "{\n"
        '  "kind": "box" | "cylinder" | "sphere" | "compound",  // compound = base + head like a mixer\n'
        '  "primary": {"L_cm": float, "W_cm": float, "H_cm": float},  // rough bounding box in centimetres\n'
        '  "secondary": {"L_cm": float, "W_cm": float, "H_cm": float, "y_offset_cm": float, "shape": "cylinder"|"box"} | null,\n'
        '  "primary_color": "#RRGGBB",     // dominant colour, lowercase hex\n'
        '  "confidence": "high" | "medium" | "low"\n'
        "}\n"
        "Rules:\n"
        "- Prefer `box` for boxy items (books, boxes, monitors flat), `cylinder` for round/tubular (cans, lamps, stools, mixing bowls), `sphere` for balls / round bulbs.\n"
        "- Use `compound` for items with a distinct base + narrower head (kitchen mixer, blender, table lamp with base+shade). The `secondary` block describes the head with y_offset_cm = distance from the base's TOP to where the head starts.\n"
        f"- If you can't estimate real cm, use the given fallback dims: L={fallback_L}, W={fallback_W}, H={fallback_H} and scale the primary/secondary proportions from that.\n"
        "- primary_color must match the dominant visible colour of the item."
    )
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"shape3d_{item_id}_{uuid.uuid4().hex[:6]}",
            system_message=SYS,
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(
            text="Return the JSON per the schema. One item, best fit.",
            file_contents=[FileContentWithMimeType(file_path=tmp, mime_type=mime)],
        ))
    finally:
        try: _os.remove(tmp)
        except Exception: pass

    s_text = (raw or "").strip().strip("`")
    if s_text.lower().startswith("json"):
        s_text = s_text[4:].strip()
    first, last = s_text.find("{"), s_text.rfind("}")
    if first >= 0 and last > first:
        s_text = s_text[first:last + 1]
    try:
        parsed = _json.loads(s_text)
    except Exception:
        raise HTTPException(status_code=502, detail="AI returned unparseable JSON")

    kind = (parsed.get("kind") or "box").lower()
    if kind not in {"box", "cylinder", "sphere", "compound"}:
        kind = "box"
    primary = parsed.get("primary") or {}
    shape3d = {
        "kind": kind,
        "primary": {
            "L_cm": float(primary.get("L_cm") or fallback_L),
            "W_cm": float(primary.get("W_cm") or fallback_W),
            "H_cm": float(primary.get("H_cm") or fallback_H),
        },
        "secondary": None,
        "primary_color": (parsed.get("primary_color") or "#94a3b8")[:16],
        "confidence": (parsed.get("confidence") or "medium").lower(),
        "derived_at": datetime.now(timezone.utc).isoformat(),
        "derived_by": current_user["id"],
        "source_photo_url": photo_url,
    }
    sec = parsed.get("secondary")
    if kind == "compound" and isinstance(sec, dict):
        shape3d["secondary"] = {
            "L_cm": float(sec.get("L_cm") or 0),
            "W_cm": float(sec.get("W_cm") or 0),
            "H_cm": float(sec.get("H_cm") or 0),
            "y_offset_cm": float(sec.get("y_offset_cm") or 0),
            "shape": (sec.get("shape") or "cylinder").lower(),
        }

    await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        # iter 254d — clear any prior shape3d_error on success so the
        # "Retry" pill on the item card goes away automatically.
        {"$set": {"items.$.shape3d": shape3d}, "$unset": {"items.$.shape3d_error": ""}},
    )
    await _audit(current_user["id"], "derive_shape3d", "shipment_item", item_id,
                 {"kind": kind, "confidence": shape3d["confidence"]})
    return shape3d


@router.post("/shipments/{shipment_id}/items/{item_id}/derive-shape")
async def derive_item_shape3d(
    shipment_id: str, item_id: str,
    current_user: dict = Depends(require_admin),
):
    """iter 253 — Ask Gemini to classify the item's photo into a 3D shape
    primitive so the packing layout renders a rough visual instead of a plain
    block. Cheap alternative to real photogrammetry — surprisingly good for
    consumer appliances (mixers/blenders/lamps/stools) because Gemini reads
    silhouette + aspect ratios reliably.
    """
    ship = await db.shipments.find_one(
        {"id": shipment_id, "items.id": item_id},
        {"_id": 0, "items.$": 1},
    )
    if not ship or not ship.get("items"):
        raise HTTPException(status_code=404, detail="Item not found")
    try:
        shape3d = await _derive_shape3d_for_item(shipment_id, ship["items"][0], current_user)
    except HTTPException as e:
        # iter 254d — persist the error onto the item so the item card can
        # show a "Retry" pill next to the failed one.
        await db.shipments.update_one(
            {"id": shipment_id, "items.id": item_id},
            {"$set": {"items.$.shape3d_error": str(e.detail)[:140]}},
        )
        raise
    except Exception as e:
        await db.shipments.update_one(
            {"id": shipment_id, "items.id": item_id},
            {"$set": {"items.$.shape3d_error": str(e)[:140]}},
        )
        raise HTTPException(status_code=500, detail=str(e)[:140])
    return {"shape3d": shape3d}


@router.post("/shipments/{shipment_id}/items/derive-shapes-batch")
async def derive_shapes_batch(
    shipment_id: str,
    limit: int = 3,
    current_user: dict = Depends(require_admin),
):
    """iter 254c — Chunked derive. Processes up to `limit` items that have a
    photo but no `shape3d` yet, then returns. The frontend loops until
    `remaining == 0`. Small chunks (default 3) keep every HTTP call well
    under the 120s proxy timeout and make progress visible after each
    batch — even on production where a worker recycle would kill an
    untracked background task.
    """
    limit = max(1, min(int(limit or 3), 5))
    ship = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "items": 1})
    if not ship:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items = ship.get("items") or []

    all_candidates = [
        it for it in items
        if not it.get("shape3d") and (
            it.get("photo_url") or (it.get("image_urls") and it["image_urls"][0])
        )
    ]
    chunk = all_candidates[:limit]

    succeeded = 0
    failed: list[dict] = []
    for it in chunk:
        try:
            await _derive_shape3d_for_item(shipment_id, it, current_user)
            succeeded += 1
        except HTTPException as e:
            msg = str(e.detail)[:140]
            failed.append({"item_id": it["id"], "name": it.get("name") or "", "error": msg})
            # iter 254d — persist per-item error so the frontend can show a
            # small Retry pill exactly on the items that need a re-try.
            await db.shipments.update_one(
                {"id": shipment_id, "items.id": it["id"]},
                {"$set": {"items.$.shape3d_error": msg}},
            )
        except Exception as e:
            msg = str(e)[:140]
            failed.append({"item_id": it["id"], "name": it.get("name") or "", "error": msg})
            await db.shipments.update_one(
                {"id": shipment_id, "items.id": it["id"]},
                {"$set": {"items.$.shape3d_error": msg}},
            )

    return {
        "succeeded": succeeded,
        "failed": failed,
        "remaining": max(0, len(all_candidates) - len(chunk)),
        "total_untagged": len(all_candidates),
        "skipped_no_photo": sum(
            1 for it in items
            if not it.get("shape3d") and not it.get("photo_url") and not (it.get("image_urls") or [])
        ),
        "already_analysed": sum(1 for it in items if it.get("shape3d")),
    }



@router.post("/shipments/{shipment_id}/items/{item_id}/find-link")
async def find_link_for_item(shipment_id: str, item_id: str, current_user: dict = Depends(require_admin)):
    """Given an item that has no `source_url` yet, ask Gemini to pick the
    best retailer for its category and return a guaranteed-working SEARCH
    URL. We deliberately don't ask for deep ASIN/SKU links because those
    drift / 404 — search URLs always resolve.

    Returns: { url: str, retailer: str, query: str } and stores `source_url`
    on the item so volunteers can click straight from the wishlist.
    """
    s = await db.shipments.find_one(
        {"id": shipment_id, "items.id": item_id},
        {"_id": 0, "items.$": 1},
    )
    if not s:
        raise HTTPException(status_code=404, detail="Item not found")
    item = s["items"][0]
    name = (item.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Item has no name to search")
    category = (item.get("category") or "").strip()
    isbn = (item.get("isbn") or "").strip()
    upc = (item.get("upc") or "").strip()

    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI unavailable (no LLM key configured)")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI client unavailable: {e}")

    sys_msg = (
        "You pick the best retailer to buy a shipment-bound item and return a "
        "SEARCH URL (never a deep ASIN/SKU — those rot). Retailers to choose "
        "from, by category fit:\n"
        "  Books / educational           → amazon, abebooks, betterworldbooks\n"
        "  Food / pantry / baby formula  → walmart, amazon, target\n"
        "  Medical / first-aid           → amazon, walmart, henryschein\n"
        "  Electronics                   → amazon, bestbuy, walmart\n"
        "  Household / kitchen / linen   → walmart, ikea, amazon\n"
        "  Furniture                     → ikea, wayfair, amazon, macbid\n"
        "  Tools / Construction          → homedepot, lowes, harborfreight, amazon\n"
        "  Agriculture / Seeds           → tractor_supply, amazon\n"
        "  Sports                        → dickssportinggoods, amazon, walmart\n"
        "  Toiletries / personal care    → walmart, target, amazon\n"
        "  BabyGear / strollers          → target, amazon, buybuybaby\n"
        "  Bicycle                       → walmart, amazon, decathlon\n"
        "  Toys                          → target, walmart, amazon\n"
        "Output STRICT JSON: {\"retailer\": str, \"query\": str (≤80 chars, "
        "what to put in the retailer's search box), \"reason\": str (≤80 chars)}."
        " Strip brand spam from the query; keep it precise."
    )
    user_text = (
        f"Item: {name}\n"
        f"Category: {category or '(unspecified)'}\n"
        f"ISBN: {isbn or '-'}\n"
        f"UPC: {upc or '-'}\n"
        "Pick the BEST retailer and a clean search query."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"shipment_findlink_{item_id}_{uuid.uuid4().hex[:6]}",
        system_message=sys_msg,
    ).with_model("gemini", "gemini-3-flash-preview")
    raw = await chat.send_message(UserMessage(text=user_text))
    s_text = (raw or "").strip()
    if s_text.startswith("```"):
        s_text = s_text.strip("`")
        if s_text.lower().startswith("json"):
            s_text = s_text[4:].strip()
    first, last = s_text.find("{"), s_text.rfind("}")
    if first >= 0 and last > first:
        s_text = s_text[first:last + 1]
    import json as _json
    try:
        parsed = _json.loads(s_text)
    except Exception:
        # Fallback — Amazon search of the item name
        parsed = {"retailer": "amazon", "query": name, "reason": "AI fallback"}
    retailer = (parsed.get("retailer") or "amazon").strip().lower()
    query = (parsed.get("query") or name).strip()
    # ISBN/UPC short-circuit — always more specific than a name search.
    if isbn and retailer in ("amazon", "abebooks", "betterworldbooks"):
        query = isbn
    elif upc:
        query = upc

    import urllib.parse as _u
    q = _u.quote_plus(query)
    SEARCH_URLS = {
        "amazon": f"https://www.amazon.com/s?k={q}",
        "walmart": f"https://www.walmart.com/search?q={q}",
        "target": f"https://www.target.com/s?searchTerm={q}",
        "ebay": f"https://www.ebay.com/sch/i.html?_nkw={q}",
        "homedepot": f"https://www.homedepot.com/s/{q}",
        "lowes": f"https://www.lowes.com/search?searchTerm={q}",
        "harborfreight": f"https://www.harborfreight.com/search?q={q}",
        "bestbuy": f"https://www.bestbuy.com/site/searchpage.jsp?st={q}",
        "ikea": f"https://www.ikea.com/us/en/search/?q={q}",
        "wayfair": f"https://www.wayfair.com/keyword.php?keyword={q}",
        "macbid": f"https://www.mac.bid/search?text={q}",
        "abebooks": f"https://www.abebooks.com/servlet/SearchResults?kn={q}",
        "betterworldbooks": f"https://www.betterworldbooks.com/search/results?q={q}",
        "tractor_supply": f"https://www.tractorsupply.com/tsc/search/{q}",
        "buybuybaby": f"https://www.buybuybaby.com/store/s/{q}",
        "dickssportinggoods": f"https://www.dickssportinggoods.com/search/SearchDisplay?searchTerm={q}",
        "decathlon": f"https://www.decathlon.com/search?q={q}",
        "henryschein": f"https://www.henryschein.com/us-en/Search.aspx?searchkeyWord={q}",
        "aliexpress": f"https://www.aliexpress.com/wholesale?SearchText={q}",
    }
    url = SEARCH_URLS.get(retailer) or SEARCH_URLS["amazon"]
    await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        {"$set": {
            "items.$.source_url": url,
            "items.$.source_retailer": retailer,
            "items.$.source_found_at": datetime.now(timezone.utc).isoformat(),
            "items.$.updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"url": url, "retailer": retailer, "query": query, "reason": parsed.get("reason") or ""}
@router.post("/shipments/{shipment_id}/manifest-groups")
async def add_manifest_group(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Create a new manifest group (sub-consignment) inside a shipment."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Group name is required")
    group = {
        "id": f"mg_{uuid.uuid4().hex[:8]}",
        "name": name[:120],
        "consignee_name": (data.get("consignee_name") or "")[:120],
        "consignee_address": (data.get("consignee_address") or "")[:500],
        "notes": (data.get("notes") or "")[:500],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    r = await db.shipments.update_one(
        {"id": shipment_id},
        {"$push": {"manifest_groups": group}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return group


@router.put("/shipments/{shipment_id}/manifest-groups/{group_id}")
async def update_manifest_group(shipment_id: str, group_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Rename or edit a manifest group's metadata."""
    allowed = {"name", "consignee_name", "consignee_address", "notes"}
    set_ops = {}
    for k, v in data.items():
        if k in allowed:
            set_ops[f"manifest_groups.$.{k}"] = (v or "")[:500 if k != "name" else 120]
    if not set_ops:
        return {"updated": False}
    r = await db.shipments.update_one(
        {"id": shipment_id, "manifest_groups.id": group_id},
        {"$set": set_ops},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"updated": True}


@router.delete("/shipments/{shipment_id}/manifest-groups/{group_id}")
async def delete_manifest_group(shipment_id: str, group_id: str, current_user: dict = Depends(require_admin)):
    """Delete a manifest group.  All items currently tagged with this group
    are moved back to the 'unassigned' pool (they stay on the container)."""
    # Un-assign items first
    await db.shipments.update_one(
        {"id": shipment_id},
        {"$set": {"items.$[itm].manifest_group_id": None}},
        array_filters=[{"itm.manifest_group_id": group_id}],
    )
    r = await db.shipments.update_one(
        {"id": shipment_id},
        {"$pull": {"manifest_groups": {"id": group_id}}},
    )
    if r.modified_count == 0:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"deleted": True}


# ========== HS CODE CLASSIFICATION + PRINTABLE MANIFEST (iter216) ==========
@router.post("/shipments/{shipment_id}/items/{item_id}/classify-hs")
async def classify_item_hs(shipment_id: str, item_id: str, current_user: dict = Depends(require_admin)):
    """Ask AI to classify one item's HS code and store on the item."""
    s = await db.shipments.find_one({"id": shipment_id, "items.id": item_id}, {"_id": 0, "items.$": 1, "dest_country": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Item not found")
    item = s["items"][0]
    result = await _classify_hs_with_ai(
        item.get("name", ""), item.get("category", ""),
        item.get("condition", "used"), s.get("dest_country", "") or "",
    )
    await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        {"$set": {
            "items.$.hs_code": result["hs_code"],
            "items.$.hs_code_reason": result["reason"],
            "items.$.updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return result


@router.post("/shipments/{shipment_id}/classify-hs-bulk")
async def bulk_classify_hs(
    shipment_id: str,
    data: dict = None,
    limit: int = 3,
    current_user: dict = Depends(require_admin),
):
    """iter 256 — HS-only chunked classifier. Small chunks (default 3, cap
    10), per-call hard timeout of 35s per item (in `_classify_hs_with_ai`),
    and every branch returns a JSON body so Cloudflare never sees a
    malformed / empty response. PVoC classification removed at user request.

    Frontend loops until `remaining == 0`.
    """
    force = bool((data or {}).get("force"))
    try:
        limit = max(1, min(int(limit or 3), 10))
        s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "items": 1, "dest_country": 1})
        if not s:
            raise HTTPException(status_code=404, detail="Shipment not found")
        items = s.get("items") or []
        dest_country = s.get("dest_country", "") or ""
        all_targets = [i for i in items if force or not (i.get("hs_code") or "").strip()]
        chunk = all_targets[:limit]

        classified = 0
        failed: list[dict] = []
        for it in chunk:
            try:
                r = await _classify_hs_with_ai(
                    it.get("name", ""), it.get("category", ""),
                    it.get("condition", "used"), dest_country,
                )
                await db.shipments.update_one(
                    {"id": shipment_id, "items.id": it["id"]},
                    {"$set": {
                        "items.$.hs_code": r["hs_code"],
                        "items.$.hs_code_reason": r["reason"],
                        "items.$.updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                classified += 1
            except HTTPException as ex:
                failed.append({"item_id": it["id"], "name": it.get("name") or "", "error": str(ex.detail)[:120]})
            except Exception as ex:
                failed.append({"item_id": it["id"], "name": it.get("name") or "", "error": str(ex)[:120]})

        return {
            "classified": classified,
            "failed": failed,
            "remaining": max(0, len(all_targets) - len(chunk)),
            "total_untagged": len(all_targets),
        }
    except HTTPException:
        raise
    except Exception as ex:
        # iter 256 — guarantee a JSON body so Cloudflare never surfaces a
        # "could not parse origin response" 520 to the packer.
        logger.exception(f"bulk_classify_hs unexpected error: {ex}")
        return {
            "classified": 0,
            "failed": [{"item_id": None, "name": "", "error": str(ex)[:200] or "internal error"}],
            "remaining": 0,
            "total_untagged": 0,
        }


# ────── Shared helpers for manifest/invoice PDFs ────────────────────────
@router.get("/shipments/{shipment_id}/manifest.pdf")
async def shipment_manifest_pdf(shipment_id: str, group: Optional[str] = None, current_user: dict = Depends(require_admin)):
    """Server-rendered printable customs manifest PDF.

    Optional query param `group=<manifest_group_id>` scopes the PDF to a single
    sub-consignment (e.g. "Lubwama Household Relocation").  Use `group=unassigned`
    for items not tagged with any group.  No `group` = the whole container.

    Items are sorted by box number (Box 1 → Box 10 → un-boxed) so packers
    can walk down the container and check off one full box at a time.
    """
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items, group_meta = _resolve_group(s, group)
    # iter 255 — manifest sorted by box number (Box 1 → Box 2 → Box 10 → …
    # then un-boxed) so packers can walk down the container and check off
    # a full box at a time.
    items = _sort_items_by_box(items, s.get("packing_units") or [])
    packing_units = s.get("packing_units") or []
    shipment_title = s.get("name", "")
    heading = shipment_title
    if group_meta:
        heading = f"{shipment_title} · {group_meta.get('name', '')}"
    rows_html = ""
    for i, it in enumerate(items, 1):
        rows_html += (
            f"<tr>"
            f"<td class='n'>{i}</td>"
            f"<td>{(it.get('name') or '')[:80]}</td>"
            f"<td class='hs'>{(it.get('hs_code') or '—')}</td>"
            f"<td class='loc'>{_loc_str(it, packing_units)}</td>"
            f"<td class='c'><span class='cond {it.get('condition','used')}'>{(it.get('condition') or 'used').upper()}</span></td>"
            f"<td class='n'>{it.get('qty_acquired', 0)}</td>"
            f"</tr>"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='6' style='text-align:center;color:#94a3b8;padding:24px'>No items in this manifest</td></tr>"
    total_items = sum(int(it.get("qty_acquired") or 0) for it in items)
    total_weight = sum(float(it.get("weight_kg") or 0) * int(it.get("qty_acquired") or 0) for it in items)
    total_value = sum(float(it.get("value_usd") or 0) * int(it.get("qty_acquired") or 0) for it in items)
    # iter 256 — PVoC classification removed from bulk endpoint. Any legacy
    # `requires_pvoc` values on old items are still counted for continuity but
    # we no longer add new ones.
    consignee_html = ""
    if group_meta and (group_meta.get("consignee_name") or group_meta.get("consignee_address")):
        consignee_html = (
            f"<div class='consignee'><strong>Consignee:</strong> "
            f"{group_meta.get('consignee_name', '')}"
            f"{' — ' + group_meta.get('consignee_address', '') if group_meta.get('consignee_address') else ''}"
            f"</div>"
        )
    html = f"""<html><head><meta charset='utf-8' /><style>{_PDF_STYLES}</style></head><body>
  <div class='head'>
    <div>
      <h1>Container Manifest — {heading}</h1>
      <p class='meta'>Shipment ID: {s.get('id', '')} · Destination: {s.get('dest_country', '—')} · Target ship: {s.get('target_ship_date', '—')}</p>
      <div class='totals'>
        <div><span>Line items:</span> <strong>{len(items)}</strong></div>
        <div><span>Units:</span> <strong>{total_items:,}</strong></div>
        <div><span>Total weight:</span> <strong>{total_weight:,.1f} kg</strong></div>
        <div><span>Declared value:</span> <strong>USD {total_value:,.2f}</strong></div>
      </div>
    </div>
    <div style='text-align:right'>
      <p class='meta'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      <p class='meta'>Customs manifest · HS-6 · Sorted by box number</p>
    </div>
  </div>
  {consignee_html}
  <table>
    <thead><tr><th class='n' style='width:32px'>#</th><th>Item</th><th style='width:80px'>HS Code</th><th style='width:180px'>Location</th><th class='c' style='width:70px'>Condition</th><th class='n' style='width:60px'>Qty</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p class='meta' style='margin-top:8mm; text-align:center'>HS codes are 6-digit WCO Harmonized System classifications. Country-specific 8/10-digit suffixes must be applied at destination customs.</p>
</body></html>"""
    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Manifest PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", (heading or "manifest"))[:60]
    filename = f"manifest_{safe_name}_{shipment_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/shipments/{shipment_id}/commercial-invoice.pdf")
async def shipment_commercial_invoice_pdf(shipment_id: str, group: Optional[str] = None, current_user: dict = Depends(require_admin)):
    """Printable commercial invoice PDF (customs-grade).

    Columns: # · Item · HS · Origin · Qty · Unit Value · Line Total.
    Same `?group=<gid>` filter + sorted by value / box (see `_sort_items_for_invoice`).
    """
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    items, group_meta = _resolve_group(s, group)
    # iter 255 — invoice sorted by declared line value (highest first) and
    # then by box number, so the highest-value / most-scrutinised lines
    # land at the top of every page for a customs officer.
    items = _sort_items_for_invoice(items, s.get("packing_units") or [])
    packing_units = s.get("packing_units") or []
    shipment_title = s.get("name", "")
    heading = shipment_title
    if group_meta:
        heading = f"{shipment_title} · {group_meta.get('name', '')}"
    rows_html = ""
    grand_qty = 0
    grand_total = 0.0
    for i, it in enumerate(items, 1):
        qty = int(it.get("qty_acquired") or 0)
        unit_val = float(it.get("value_usd") or 0)
        line_total = unit_val * qty
        grand_qty += qty
        grand_total += line_total
        origin = "USED" if it.get("condition") == "used" else (it.get("condition") or "used").upper()
        rows_html += (
            f"<tr>"
            f"<td class='n'>{i}</td>"
            f"<td>{(it.get('name') or '')[:80]}</td>"
            f"<td class='hs'>{(it.get('hs_code') or '—')}</td>"
            f"<td class='loc'>{origin}</td>"
            f"<td class='n'>{qty}</td>"
            f"<td class='n'>${unit_val:,.2f}</td>"
            f"<td class='n'>${line_total:,.2f}</td>"
            f"</tr>"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='7' style='text-align:center;color:#94a3b8;padding:24px'>No items in this invoice</td></tr>"
    consignee_html = ""
    if group_meta and (group_meta.get("consignee_name") or group_meta.get("consignee_address")):
        consignee_html = (
            f"<div class='consignee'><strong>Consignee:</strong> "
            f"{group_meta.get('consignee_name', '')}"
            f"{' — ' + group_meta.get('consignee_address', '') if group_meta.get('consignee_address') else ''}"
            f"</div>"
        )
    html = f"""<html><head><meta charset='utf-8' /><style>{_PDF_STYLES}</style></head><body>
  <div class='head'>
    <div>
      <h1>Commercial Invoice — {heading}</h1>
      <p class='meta'>Invoice #: CI-{shipment_id[:8].upper()}{'-' + group[:6].upper() if group and group != 'unassigned' else ''} · Destination: {s.get('dest_country', '—')} · Target ship: {s.get('target_ship_date', '—')}</p>
      <p class='meta'>Currency: USD · Terms: Non-commercial personal effects unless marked NEW · Incoterms: as agreed</p>
    </div>
    <div style='text-align:right'>
      <p class='meta'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      <p class='meta'>HS-6 · Sorted value ▸ box</p>
    </div>
  </div>
  {consignee_html}
  <table>
    <thead><tr>
      <th class='n' style='width:32px'>#</th>
      <th>Description of Goods</th>
      <th style='width:70px'>HS Code</th>
      <th style='width:170px'>Condition / Origin</th>
      <th class='n' style='width:50px'>Qty</th>
      <th class='n' style='width:75px'>Unit USD</th>
      <th class='n' style='width:85px'>Line Total</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    <tfoot><tr>
      <td colspan='4' style='text-align:right'>TOTAL</td>
      <td class='n'>{grand_qty:,}</td>
      <td></td>
      <td class='n'>${grand_total:,.2f}</td>
    </tr></tfoot>
  </table>
  <div style='margin-top:14mm; display:flex; justify-content:space-between; font-size:10px; color:#334155'>
    <div style='width:45%'>
      <p><strong>Declaration:</strong></p>
      <p>I declare that the information above is true and complete to the best of my knowledge. Items marked USED are donated goods with no commercial value; declared values are for customs valuation purposes only.</p>
      <div style='margin-top:14mm;border-top:1px solid #94a3b8;padding-top:4px'>Authorized signature / Date</div>
    </div>
    <div style='width:45%; text-align:right'>
      <p class='meta'>&nbsp;</p>
    </div>
  </div>
</body></html>"""
    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Commercial invoice PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", (heading or "invoice"))[:60]
    filename = f"invoice_{safe_name}_{shipment_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/shipments/{shipment_id}/items/{item_id}/estimate-from-link")
async def estimate_item_from_link(shipment_id: str, item_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """AI-estimate weight + dimensions from a product URL (Amazon, Walmart, etc.).

    Pulls the page title + first content image (best-effort, no fancy scraping)
    and asks Gemini-3-flash to estimate weight_kg + dims_cm + value_usd. Writes
    the estimate onto the item — operator can edit afterward if it's off.

    Body: { url: str }
    """
    url = (data.get("url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="url must start with http/https")
    s = await db.shipments.find_one({"id": shipment_id, "items.id": item_id}, {"_id": 0, "items.$": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Item not found")
    item = s["items"][0]

    import os as _os
    api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI estimation unavailable (no LLM key configured)")

    # Pull the page title + first image hint with a 6s timeout. Don't try to be
    # clever; just grab whatever's in <title>, <meta og:image>, <meta og:title>.
    title_hint = ""
    image_hint = ""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (compatible; 5812Connect/1.0)"}) as client:
            r = await client.get(url)
            html = (r.text or "")[:50000]
            import re
            m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
            if m:
                title_hint = m.group(1).strip()[:300]
            m = re.search(r'<meta[^>]*property=[\"\']og:image[\"\'][^>]*content=[\"\']([^\"\']+)', html, re.I)
            if m:
                image_hint = m.group(1).strip()[:500]
            if not title_hint:
                m = re.search(r'<meta[^>]*property=[\"\']og:title[\"\'][^>]*content=[\"\']([^\"\']+)', html, re.I)
                if m:
                    title_hint = m.group(1).strip()[:300]
    except Exception as e:
        logger.warning(f"link fetch failed: {e}")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI client unavailable: {e}")
    sys_msg = (
        "You estimate physical dimensions, weight, and US dollar value for a product. "
        "Output STRICT JSON: {\"weight_kg\": float, \"dims_cm\": {\"length\": float, \"width\": float, \"height\": float}, "
        "\"value_usd\": float, \"confidence\": \"high\"|\"medium\"|\"low\", \"reasoning\": str (≤120 chars)}\n"
        "Use the product NAME + URL TITLE HINT to identify the item, then estimate per typical retail-packaging dimensions. "
        "If you can't identify the product confidently, set confidence=low and use conservative round-number defaults."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"shipment_estimate_{item_id}_{uuid.uuid4().hex[:6]}",
        system_message=sys_msg,
    ).with_model("gemini", "gemini-3-flash-preview")
    user_text = (
        f"Item name: {item.get('name', '')}\n"
        f"Category: {item.get('category', '')}\n"
        f"Product URL: {url}\n"
        f"Page title hint: {title_hint or '(could not fetch)'}\n"
        f"OG image hint: {image_hint or '(none)'}\n"
        "Estimate the per-unit weight, dimensions, and USD value."
    )
    raw = await chat.send_message(UserMessage(text=user_text))
    s_text = (raw or "").strip()
    if s_text.startswith("```"):
        s_text = s_text.strip("`")
        if s_text.lower().startswith("json"):
            s_text = s_text[4:].strip()
    first, last = s_text.find("{"), s_text.rfind("}")
    if first >= 0 and last > first:
        s_text = s_text[first:last + 1]
    import json as _json
    try:
        parsed = _json.loads(s_text)
    except Exception:
        raise HTTPException(status_code=502, detail="AI returned an unparseable response — please fill in dimensions manually")
    weight = max(0.0, float(parsed.get("weight_kg") or 0))
    dims = parsed.get("dims_cm") or {}
    dims_cm = {
        "length": max(0.0, float(dims.get("length") or 0)),
        "width": max(0.0, float(dims.get("width") or 0)),
        "height": max(0.0, float(dims.get("height") or 0)),
    }
    value = max(0.0, float(parsed.get("value_usd") or 0))
    set_ops = {
        "items.$.weight_kg": weight,
        "items.$.dims_cm": dims_cm,
        "items.$.value_usd": value,
        "items.$.source_url": url,
        "items.$.ai_estimate": {
            "confidence": (parsed.get("confidence") or "medium").lower(),
            "reasoning": (parsed.get("reasoning") or "")[:200],
            "estimated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    await db.shipments.update_one(
        {"id": shipment_id, "items.id": item_id},
        {"$set": set_ops},
    )
    return {
        "weight_kg": weight, "dims_cm": dims_cm, "value_usd": value,
        "confidence": (parsed.get("confidence") or "medium").lower(),
        "reasoning": parsed.get("reasoning") or "",
    }


@router.post("/shipments/{shipment_id}/items/bulk-import")
async def bulk_import_items(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Body: { items: [{name, qty_needed, weight_kg, ...}] }. Skips rows with no name."""
    rows = data.get("items") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="items must be a list")
    units = await _shipment_units(shipment_id)
    items = []
    for r in rows:
        if not (r.get("name") or "").strip():
            continue
        try:
            items.append(_normalise_item(r, units))
        except HTTPException:
            continue
    if items:
        await db.shipments.update_one({"id": shipment_id}, {"$push": {"items": {"$each": items}}})
    return {"imported": len(items)}


