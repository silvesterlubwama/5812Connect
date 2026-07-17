"""Shipment CRUD, PIN & token endpoints (admin-only)."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
import secrets
import uuid
from deps import db, _audit, require_admin
from ._common import (
    CONTAINER_40FT_HC,
    VALID_STATUSES,
    _hash_pin,
    EDIT_TOKEN_TTL_HOURS,
)

router = APIRouter(prefix="/api", tags=["shipments"])

@router.get("/shipments")
async def list_shipments(current_user: dict = Depends(require_admin)):
    """All shipments. Newest first. Sponsor-token NOT included in the list view
    to avoid accidentally leaking tokens into screenshots — fetch the detail
    endpoint to get the token + share URL."""
    rows = await db.shipments.find({}, {"_id": 0, "token": 0}).sort("created_at", -1).to_list(500)
    # Lightweight rollup so the list shows progress at-a-glance
    for s in rows:
        items = s.get("items") or []
        s["item_count"] = len(items)
        s["total_needed"] = sum(int(i.get("qty_needed") or 0) for i in items)
        s["total_acquired"] = sum(int(i.get("qty_acquired") or 0) for i in items)
        s["total_weight_kg"] = round(sum(
            (float(i.get("weight_kg") or 0) * int(i.get("qty_acquired") or 0)) for i in items
        ), 1)
        # Drop heavy nested arrays from the list payload
        s.pop("items", None)
        s.pop("pallets", None)
    return rows


@router.post("/shipments")
async def create_shipment(data: dict, current_user: dict = Depends(require_admin)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    token = secrets.token_urlsafe(20)  # ~26-char URL-safe random
    doc = {
        "id": f"sh_{uuid.uuid4().hex[:10]}",
        "token": token,
        "name": name[:120],
        "dest_country": (data.get("dest_country") or "Uganda")[:60],
        "description": (data.get("description") or "")[:1000],
        "target_ship_date": (data.get("target_ship_date") or "")[:10],
        "status": "planning",
        "units": "imperial" if (data.get("units") == "imperial") else "metric",
        "max_payload_kg": float(data.get("max_payload_kg") or CONTAINER_40FT_HC["max_payload_kg"]),
        "container_dims_cm": CONTAINER_40FT_HC,
        "items": [],
        "pallets": [],
        "ai_packing_text": "",
        "ai_packing_generated_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.shipments.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "shipment", doc["id"], {"name": name})
    return doc


@router.get("/shipments/{shipment_id}")
async def get_shipment(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Full shipment detail INCLUDING the token + the share URL — only admins
    see this. Public visitors use the /api/public/shipments/{token} path."""
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    # Build a share URL hint — the FE will format it with REACT_APP_BACKEND_URL → site root
    s["share_path"] = f"/donate/shipment/{s.get('token', '')}"
    return s


@router.put("/shipments/{shipment_id}")
async def update_shipment(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    allowed = {"name", "dest_country", "description", "target_ship_date", "status",
               "max_payload_kg", "container_dims_cm", "units",
               # iter223 — mode + waybill/flight tracking fields
               "mode", "waybill_no", "flight_no", "carrier_name", "tracking_url",
               "departure_date", "arrival_date", "origin_country"}
    set_ops = {k: v for k, v in data.items() if k in allowed}
    if "status" in set_ops and set_ops["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    if "units" in set_ops and set_ops["units"] not in ("metric", "imperial"):
        raise HTTPException(status_code=400, detail="units must be 'metric' or 'imperial'")
    if "mode" in set_ops and set_ops["mode"] not in ("container", "airport"):
        raise HTTPException(status_code=400, detail="mode must be 'container' or 'airport'")
    if "container_dims_cm" in set_ops:
        c = set_ops["container_dims_cm"] or {}
        set_ops["container_dims_cm"] = {
            "length_cm": max(50, float(c.get("length_cm") or CONTAINER_40FT_HC["length_cm"])),
            "width_cm":  max(50, float(c.get("width_cm")  or CONTAINER_40FT_HC["width_cm"])),
            "height_cm": max(50, float(c.get("height_cm") or CONTAINER_40FT_HC["height_cm"])),
            "max_payload_kg": float(c.get("max_payload_kg") or CONTAINER_40FT_HC["max_payload_kg"]),
        }
    set_ops["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.shipments.update_one({"id": shipment_id}, {"$set": set_ops})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return {"updated": True}


@router.post("/shipments/{shipment_id}/set-pin")
async def set_shipment_pin(shipment_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Set / change / clear the per-shipment access PIN.
    Body: { pin: '4-32 chars, blank to clear' }
    The hash is one-way; we never store the plaintext."""
    pin = (data.get("pin") or "").strip()
    if pin and (len(pin) < 4 or len(pin) > 32):
        raise HTTPException(status_code=400, detail="PIN must be 4-32 characters")
    update = {"access_pin_hash": _hash_pin(pin) if pin else None,
              "access_pin_set_at": datetime.now(timezone.utc).isoformat() if pin else None}
    r = await db.shipments.update_one({"id": shipment_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")
    await _audit(current_user["id"], "set_pin" if pin else "clear_pin", "shipment", shipment_id, {})
    return {"set": bool(pin), "ttl_hours": EDIT_TOKEN_TTL_HOURS}


@router.delete("/shipments/{shipment_id}")
async def delete_shipment(shipment_id: str, current_user: dict = Depends(require_admin)):
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    s["_deleted_from"] = "shipments"
    s["deleted_at"] = datetime.now(timezone.utc).isoformat()
    s["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(s)
    await db.shipments.delete_one({"id": shipment_id})
    await _audit(current_user["id"], "delete", "shipment", shipment_id)
    return {"deleted": True}


@router.post("/shipments/{shipment_id}/rotate-token")
async def rotate_token(shipment_id: str, current_user: dict = Depends(require_admin)):
    """Invalidate the current public link + issue a new one. Use when a token
    has been over-shared or compromised."""
    s = await db.shipments.find_one({"id": shipment_id}, {"_id": 0, "id": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Shipment not found")
    new_token = secrets.token_urlsafe(20)
    await db.shipments.update_one({"id": shipment_id}, {"$set": {
        "token": new_token,
        "token_rotated_at": datetime.now(timezone.utc).isoformat(),
    }})
    await _audit(current_user["id"], "update", "shipment_token_rotate", shipment_id)
    return {"token": new_token, "share_path": f"/donate/shipment/{new_token}"}

