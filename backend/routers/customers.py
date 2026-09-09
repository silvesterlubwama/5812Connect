"""Customer accounts (the marketplace/POS customer directory).

Extracted from the legacy `routers/financial.py` in iter319. That router lost
its HTTP surface in the iter246 finance reset, which silently took the customer
directory with it — the Sales portal's customer list and "new customer" form,
the Products page Customers tab and the statements page had all been calling a
404 ever since.

Only the directory came across. The rest of `financial.py` (its parallel
donations / expenses / budgets ledger) stays offline on purpose — the one
balanced ledger in `routers/finance` is the source of truth.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime, timezone
import uuid

from deps import db, get_current_user, require_staff, require_manager, get_campus_filter

router = APIRouter(prefix="/api", tags=["customers"])


@router.get("/customers")
async def list_customers(location_id: Optional[str] = None, search: Optional[str] = None,
                         current_user: dict = Depends(get_current_user)):
    """Customer accounts, scoped to the caller's campus unless one is named."""
    query = {}
    if location_id:
        query["location_id"] = location_id
    else:
        campus = await get_campus_filter(current_user)
        if campus:
            query.update(campus)
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
        ]
    return await db.customer_accounts.find(query, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/customers")
async def create_customer(data: dict, current_user: dict = Depends(require_staff)):
    """Create a customer account, auto-linking to a matching guest record."""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    guest_id = data.get("guest_id", "")
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    if not guest_id and (email or phone):
        or_clauses = []
        if email:
            or_clauses.append({"email": email})
        if phone:
            or_clauses.append({"phone": phone})
        guest = await db.guests.find_one({"$or": or_clauses}, {"_id": 0, "id": 1})
        if guest:
            guest_id = guest["id"]
    doc = {
        "id": f"cust_{uuid.uuid4().hex[:8]}",
        "name": name, "email": email, "phone": phone,
        "guest_id": guest_id,
        "location_id": data.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id") or "",
        "notes": data.get("notes", ""),
        "total_purchases": 0, "total_spent": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.customer_accounts.insert_one(doc)
    doc.pop("_id", None)
    if guest_id:
        await db.guests.update_one({"id": guest_id}, {"$set": {"is_customer": True, "customer_id": doc["id"]}})
    return doc


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customer_accounts.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer["purchases"] = await db.sales.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return customer


@router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "email", "phone", "notes", "guest_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.customer_accounts.update_one({"id": customer_id}, {"$set": update})
    return await db.customer_accounts.find_one({"id": customer_id}, {"_id": 0})


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(require_manager)):
    await db.customer_accounts.delete_one({"id": customer_id})
    return {"message": "Customer account deleted"}


@router.get("/customers/{customer_id}/purchases")
async def get_customer_purchases(customer_id: str, current_user: dict = Depends(get_current_user)):
    purchases = await db.sales.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {
        "purchases": purchases,
        "total_count": len(purchases),
        "total_spent": sum(p.get("total", 0) for p in purchases),
    }
