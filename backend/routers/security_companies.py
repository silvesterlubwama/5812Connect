"""Security company management.

Contractor security firms whose personnel man the checkpoint kiosk. Each
company has a name, phone, optional logo, and an `active` flag. Individual
Security Contractor users reference a company via `security_company_id`
and carry a `security_rank` string on their user record.

Only directors+ can manage companies (they represent operational
relationships with external vendors). Security Contractors themselves
have no access to these endpoints.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from deps import db, require_director, get_current_user

router = APIRouter(prefix="/api/security-companies", tags=["security-companies"])


class SecurityCompanyCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None


class SecurityCompanyUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None
    active: Optional[bool] = None
    logo_url: Optional[str] = None


@router.get("")
async def list_companies(current_user: dict = Depends(get_current_user)):
    """Anyone signed in can READ (needed by the badge to render the company
    logo when its own record is loaded). Write access is director+."""
    docs = await db.security_companies.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return docs


@router.post("", status_code=201)
async def create_company(body: SecurityCompanyCreate, current_user: dict = Depends(require_director)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    existing = await db.security_companies.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="A company with that name already exists")
    doc = {
        "id": f"secco_{uuid.uuid4().hex[:10]}",
        "name": name,
        "phone": (body.phone or "").strip() or None,
        "contact_email": (body.contact_email or "").strip() or None,
        "address": (body.address or "").strip() or None,
        "logo_url": None,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.security_companies.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{company_id}")
async def update_company(company_id: str, body: SecurityCompanyUpdate, current_user: dict = Depends(require_director)):
    updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None or k == "active"}
    if "name" in updates and updates["name"]:
        updates["name"] = updates["name"].strip()
        clash = await db.security_companies.find_one(
            {"name": {"$regex": f"^{updates['name']}$", "$options": "i"}, "id": {"$ne": company_id}},
            {"_id": 0, "id": 1},
        )
        if clash:
            raise HTTPException(status_code=409, detail="Another company already uses that name")
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.security_companies.update_one({"id": company_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    doc = await db.security_companies.find_one({"id": company_id}, {"_id": 0})
    return doc


@router.delete("/{company_id}")
async def delete_company(company_id: str, current_user: dict = Depends(require_director)):
    # Hard delete only if no user references it — otherwise soft-deactivate so
    # historical checkpoint logs keep their reference intact.
    in_use = await db.users.count_documents({"security_company_id": company_id})
    if in_use:
        await db.security_companies.update_one({"id": company_id}, {"$set": {"active": False}})
        return {"deactivated": True, "linked_users": in_use}
    r = await db.security_companies.delete_one({"id": company_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"deleted": True}


@router.post("/{company_id}/logo")
async def upload_company_logo(company_id: str, file: UploadFile = File(...), current_user: dict = Depends(require_director)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo must be under 2 MB")
    company = await db.security_companies.find_one({"id": company_id}, {"_id": 0, "id": 1})
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "png"
    path = f"security-company-logos/{company_id}.{ext}"
    logo_url = None
    try:
        from storage import put_object
        result = put_object(path, data, file.content_type)
        logo_url = result.get("url", f"/api/storage/{path}")
    except Exception:
        os.makedirs("/app/backend/uploads/security-company-logos", exist_ok=True)
        local_name = f"{company_id}.{ext}"
        with open(f"/app/backend/uploads/security-company-logos/{local_name}", "wb") as fh:
            fh.write(data)
        logo_url = f"/api/uploads/security-company-logos/{local_name}"
    await db.security_companies.update_one(
        {"id": company_id},
        {"$set": {"logo_url": logo_url, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"logo_url": logo_url}
