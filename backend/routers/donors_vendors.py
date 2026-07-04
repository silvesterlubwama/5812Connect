"""Donors & Vendors — auto-created profiles from donation/expense entries.

Each donor/vendor profile is upserted automatically the first time a name is
used on a donation (donor) or expense (vendor).  The record then aggregates
all their historical transactions, allowing typeahead suggestions on future
entries and drilldown reporting.

The existing `vendors` collection (used by Banking/AP for bill vendors) is
reused, so a single vendor profile can carry both bill and expense history.
A new `donors` collection is introduced for the donation side.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timezone
import re
import uuid

from deps import (
    db, get_current_user, require_admin, require_manager, _audit,
    get_campus_filter, is_system_admin, logger,
)

router = APIRouter(prefix="/api", tags=["donors-vendors"])


# ============================================================
#  Shared helpers — upsert on donation/expense create/update
# ============================================================

VALID_DONOR_CATEGORIES = {"individual", "corporation", "church", "government", "foundation", "anonymous"}
VALID_VENDOR_CATEGORIES = {"individual", "corporation", "government", "utility", "supplier", "contractor"}
VALID_CONTACT_METHODS = {"email", "phone", "sms", "whatsapp", "in_person", "postal"}


async def upsert_donor_from_donation(donation: dict, current_user: dict) -> Optional[str]:
    """Auto-create or update a donor profile from a donation row.
    Returns the donor_id (existing or newly created)."""
    name = (donation.get("donor_name") or "").strip()
    if not name:
        return None
    # Resolve the effective campus ONCE and use it consistently for BOTH the
    # lookup and the new-row campus_id.  This is what fixes the backfill
    # idempotency bug that surfaced in iter210 tests — previously the dedup
    # lookup used donation.campus_id (empty for legacy rows) while the insert
    # fell back to current_user.active_campus_id, so a second run always
    # missed the previously-inserted donor and created a duplicate.
    effective_campus = (donation.get("campus_id") or current_user.get("active_campus_id") or "").strip()
    # Match case-insensitively by name AND effective campus so re-runs are safe
    existing = await db.donors.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "campus_id": effective_campus},
        {"_id": 0, "id": 1},
    )
    if existing:
        await db.donors.update_one(
            {"id": existing["id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return existing["id"]
    doc = {
        "id": f"dnr_{uuid.uuid4().hex[:10]}",
        "name": name,
        "category": "individual",
        "email": (donation.get("donor_email") or "").strip(),
        "phone": (donation.get("donor_phone") or "").strip(),
        "preferred_contact": "email",
        "campus_id": effective_campus,
        "location_id": donation.get("location_id") or "",
        "notes": "",
        "active": True,
        "auto_created": True,
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.donors.insert_one(doc)
    logger.info(f"Auto-created donor '{name}' (id={doc['id']}, campus={effective_campus}) from donation")
    return doc["id"]


async def upsert_vendor_from_expense(expense: dict, current_user: dict) -> Optional[str]:
    """Auto-create or update a vendor profile from an expense row.
    Returns the vendor_id (existing or newly created)."""
    name = (expense.get("vendor") or expense.get("vendor_name") or "").strip()
    if not name:
        return None
    effective_campus = (expense.get("campus_id") or current_user.get("active_campus_id") or "").strip()
    location_id = expense.get("location_id") or ""
    # Match by name + effective campus (consistent with donor logic)
    existing = await db.vendors.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "campus_id": effective_campus},
        {"_id": 0, "id": 1},
    )
    if existing:
        await db.vendors.update_one(
            {"id": existing["id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return existing["id"]
    doc = {
        "id": f"vnd_{uuid.uuid4().hex[:10]}",
        "name": name,
        "category": "supplier",
        "email": "",
        "phone": "",
        "preferred_contact": "email",
        "address": "",
        "contact_name": "",
        "country": "UG",
        "campus_id": effective_campus,
        "location_id": location_id,
        "notes": "",
        "payment_terms_days": 30,
        "vat_registered": False,
        "tin": "",
        "currency": expense.get("currency", "UGX"),
        "active": True,
        "auto_created": True,
        "created_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.vendors.insert_one(doc)
    logger.info(f"Auto-created vendor '{name}' (id={doc['id']}, campus={effective_campus}) from expense")
    return doc["id"]


async def _donor_stats(donor_id: str, donor_name: str, campus_id: str) -> dict:
    """Aggregate donation totals + count for a donor.  We match by donor_id OR
    donor_name (case-insensitive) — no campus filter, because donation.campus_id
    is often absent on legacy rows and would silently drop matches."""
    q = {"$or": [
        {"donor_id": donor_id},
        {"donor_name": {"$regex": f"^{re.escape(donor_name)}$", "$options": "i"}},
    ]}
    r = await db.donations.aggregate([
        {"$match": q},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}, "last_date": {"$max": "$date"}}},
    ]).to_list(1)
    if not r:
        return {"total_donated": 0.0, "donation_count": 0, "last_donation_date": None}
    return {
        "total_donated": float(r[0].get("total") or 0),
        "donation_count": int(r[0].get("count") or 0),
        "last_donation_date": r[0].get("last_date"),
    }


async def _vendor_stats(vendor_id: str, vendor_name: str) -> dict:
    """Aggregate expense totals + count for a vendor."""
    q = {"$or": [{"vendor_id": vendor_id}, {"vendor": vendor_name}], "status": {"$in": ["approved", None]}}
    r = await db.expenses.aggregate([
        {"$match": q},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}, "last_date": {"$max": "$date"}}},
    ]).to_list(1)
    total = float(r[0].get("total") or 0) if r else 0
    count = int(r[0].get("count") or 0) if r else 0
    last_date = r[0].get("last_date") if r else None
    # Also include bill totals if the vendor has been used in bank/AP module
    bills = await db.bills.aggregate([
        {"$match": {"vendor_id": vendor_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_due"}, "count": {"$sum": 1}}},
    ]).to_list(1) if vendor_id else []
    bills_total = float(bills[0].get("total") or 0) if bills else 0
    bills_count = int(bills[0].get("count") or 0) if bills else 0
    return {
        "total_expenses": total,
        "expense_count": count,
        "last_expense_date": last_date,
        "total_bills": bills_total,
        "bill_count": bills_count,
    }


async def get_campus_filter_for_donor(campus_id: str) -> dict:
    if not campus_id:
        return {}
    return {"campus_id": campus_id}


# ============================================================
#  DONORS API
# ============================================================

@router.get("/donors")
async def list_donors(
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    include_stats: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """List donors — supports search prefix (for typeahead) and campus scoping."""
    campus_filter = await get_campus_filter(current_user)
    q: dict = {**campus_filter, "active": {"$ne": False}}
    if search:
        q["name"] = {"$regex": search, "$options": "i"}
    docs = await db.donors.find(q, {"_id": 0}).sort("name", 1).to_list(limit)
    if include_stats:
        for d in docs:
            stats = await _donor_stats(d["id"], d["name"], d.get("campus_id", ""))
            d.update(stats)
    return docs


@router.get("/donors/suggest")
async def suggest_donors(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
    current_user: dict = Depends(get_current_user),
):
    """Lightweight typeahead — returns only id + name for donor autosuggest."""
    campus_filter = await get_campus_filter(current_user)
    query = {**campus_filter, "active": {"$ne": False}, "name": {"$regex": f"^{q}", "$options": "i"}}
    return await db.donors.find(query, {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "category": 1}).sort("name", 1).to_list(limit)


@router.get("/donors/{donor_id}")
async def get_donor(donor_id: str, current_user: dict = Depends(get_current_user)):
    d = await db.donors.find_one({"id": donor_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Donor not found")
    d.update(await _donor_stats(d["id"], d["name"], d.get("campus_id", "")))
    return d


@router.get("/donors/{donor_id}/transactions")
async def donor_transactions(
    donor_id: str,
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    donor = await db.donors.find_one({"id": donor_id}, {"_id": 0, "name": 1, "campus_id": 1})
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    # Match by id OR by name (case-insensitive) — no campus filter here so
    # legacy donations that lack campus_id still surface in the drilldown.
    q = {"$or": [
        {"donor_id": donor_id},
        {"donor_name": {"$regex": f"^{re.escape(donor['name'])}$", "$options": "i"}},
    ]}
    return await db.donations.find(q, {"_id": 0}).sort("date", -1).to_list(limit)


@router.put("/donors/{donor_id}")
async def update_donor(donor_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Enrich the auto-created donor profile — category, contact info, notes."""
    allowed = {"name", "category", "email", "phone", "preferred_contact", "notes", "address", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "category" in update and update["category"] not in VALID_DONOR_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of {sorted(VALID_DONOR_CATEGORIES)}")
    if "preferred_contact" in update and update["preferred_contact"] not in VALID_CONTACT_METHODS:
        raise HTTPException(status_code=400, detail=f"Invalid contact method. Must be one of {sorted(VALID_CONTACT_METHODS)}")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.donors.update_one({"id": donor_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Donor not found")
    await _audit(current_user["id"], "update", "donor", donor_id, {"fields": list(update.keys())})
    return {"message": "Donor updated"}


@router.delete("/donors/{donor_id}")
async def delete_donor(donor_id: str, current_user: dict = Depends(require_admin)):
    r = await db.donors.update_one({"id": donor_id}, {"$set": {"active": False, "deleted_at": datetime.now(timezone.utc).isoformat()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Donor not found")
    await _audit(current_user["id"], "delete", "donor", donor_id)
    return {"message": "Donor deactivated"}


# ============================================================
#  VENDORS API (Read/List/Suggest — reuses existing vendors coll)
#
#  Note: The Banking module already exposes vendor CRUD at
#  /api/bank/vendors.  This module adds a lightweight
#  read/suggest/drilldown surface at /api/vendors for the
#  expense-typeahead + drilldown page.  Full CRUD lives in Banking.
# ============================================================

@router.get("/vendors")
async def list_vendors(
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    include_stats: bool = True,
    current_user: dict = Depends(get_current_user),
):
    campus_filter = await get_campus_filter(current_user)
    q: dict = {"active": {"$ne": False}}
    q.update(campus_filter)
    if search:
        q["name"] = {"$regex": search, "$options": "i"}
    docs = await db.vendors.find(q, {"_id": 0}).sort("name", 1).to_list(limit)
    if include_stats:
        for v in docs:
            v.update(await _vendor_stats(v["id"], v["name"]))
    return docs


@router.get("/vendors/suggest")
async def suggest_vendors(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
    current_user: dict = Depends(get_current_user),
):
    campus_filter = await get_campus_filter(current_user)
    query = {"active": {"$ne": False}, "name": {"$regex": f"^{q}", "$options": "i"}}
    query.update(campus_filter)
    return await db.vendors.find(query, {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "category": 1}).sort("name", 1).to_list(limit)


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, current_user: dict = Depends(get_current_user)):
    v = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    v.update(await _vendor_stats(v["id"], v["name"]))
    return v


@router.get("/vendors/{vendor_id}/transactions")
async def vendor_transactions(
    vendor_id: str,
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
):
    v = await db.vendors.find_one({"id": vendor_id}, {"_id": 0, "name": 1})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    expenses = await db.expenses.find(
        {"$or": [{"vendor_id": vendor_id}, {"vendor": v["name"]}]},
        {"_id": 0},
    ).sort("date", -1).to_list(limit)
    bills = await db.bills.find({"vendor_id": vendor_id}, {"_id": 0}).sort("bill_date", -1).to_list(limit)
    return {"expenses": expenses, "bills": bills}


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Enrich the vendor profile — category, contact info, notes, preferred contact method."""
    allowed = {"name", "category", "email", "phone", "preferred_contact", "notes", "address",
               "contact_name", "country", "payment_terms_days", "vat_registered", "tin",
               "currency", "default_account_id", "active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "category" in update and update["category"] not in VALID_VENDOR_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of {sorted(VALID_VENDOR_CATEGORIES)}")
    if "preferred_contact" in update and update["preferred_contact"] not in VALID_CONTACT_METHODS:
        raise HTTPException(status_code=400, detail=f"Invalid contact method. Must be one of {sorted(VALID_CONTACT_METHODS)}")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.vendors.update_one({"id": vendor_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    await _audit(current_user["id"], "update", "vendor", vendor_id, {"fields": list(update.keys())})
    return {"message": "Vendor updated"}


# ============================================================
#  BACKFILL — one-time repair to create profiles from historical
#  donations/expenses that pre-dated the auto-create hook.
# ============================================================

@router.post("/donors-vendors/backfill")
async def backfill_donors_vendors(current_user: dict = Depends(require_admin)):
    """One-time backfill (idempotent): scan every historical donation and
    expense and auto-create any missing donor/vendor profile.  Safe to re-run —
    uses the SAME effective-campus resolution as the auto-upsert helpers so
    dedup lookups match on subsequent runs."""
    donors_created = 0
    vendors_created = 0
    admin_campus = (current_user.get("active_campus_id") or "").strip()
    # Donors
    seen_donors: set = set()
    async for d in db.donations.find({"donor_name": {"$exists": True, "$ne": ""}}, {"_id": 0, "donor_name": 1, "campus_id": 1, "location_id": 1}):
        name = (d.get("donor_name") or "").strip()
        eff_campus = (d.get("campus_id") or admin_campus).strip()
        key = (name.lower(), eff_campus)
        if not name or key in seen_donors:
            continue
        seen_donors.add(key)
        existing = await db.donors.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "campus_id": eff_campus},
            {"_id": 0, "id": 1},
        )
        if existing:
            continue
        new_id = await upsert_donor_from_donation(d, current_user)
        if new_id:
            donors_created += 1
    # Vendors
    seen_vendors: set = set()
    async for e in db.expenses.find({"vendor": {"$exists": True, "$nin": [None, ""]}}, {"_id": 0, "vendor": 1, "campus_id": 1, "location_id": 1, "currency": 1}):
        name = (e.get("vendor") or "").strip()
        eff_campus = (e.get("campus_id") or admin_campus).strip()
        key = (name.lower(), eff_campus)
        if not name or key in seen_vendors:
            continue
        seen_vendors.add(key)
        existing = await db.vendors.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "campus_id": eff_campus},
            {"_id": 0, "id": 1},
        )
        if existing:
            continue
        new_id = await upsert_vendor_from_expense(e, current_user)
        if new_id:
            vendors_created += 1
    await _audit(current_user["id"], "backfill", "donors_vendors", None, {"donors_created": donors_created, "vendors_created": vendors_created})
    return {
        "donors_created": donors_created,
        "vendors_created": vendors_created,
        "message": f"Backfill complete — created {donors_created} donor profiles and {vendors_created} vendor profiles from historical entries.",
    }
