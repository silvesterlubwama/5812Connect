"""Biometric + NFC tag endpoints — moved out of server.py in iter303.

Lightweight endpoints used by the kiosk/checkpoint hardware to register
platform authenticators (Touch/Face-ID via WebAuthn) and physical NFC tags
against a member id.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user

router = APIRouter(prefix="/api")


@router.post("/biometric/register")
async def register_biometric(data: dict, current_user: dict = Depends(get_current_user)):
    member_id = data.get("member_id") or current_user["id"]
    credential_id = data.get("credential_id")
    public_key = data.get("public_key")
    authenticator_type = data.get("type", "platform")
    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id required")
    doc = {"id": f"bio_{str(uuid.uuid4())[:8]}", "member_id": member_id, "credential_id": credential_id,
           "public_key": public_key, "type": authenticator_type,
           "created_at": datetime.now(timezone.utc).isoformat(), "last_used": None}
    await db.biometric_credentials.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/biometric/verify")
async def verify_biometric(data: dict):
    credential_id = data.get("credential_id")
    if not credential_id:
        raise HTTPException(status_code=400, detail="credential_id required")
    cred = await db.biometric_credentials.find_one({"credential_id": credential_id}, {"_id": 0})
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    await db.biometric_credentials.update_one(
        {"credential_id": credential_id},
        {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}},
    )
    member = await db.members.find_one({"id": cred["member_id"]}, {"_id": 0, "id": 1, "name": 1, "role": 1})
    return {"verified": True, "member": member, "credential_type": cred.get("type")}


@router.post("/nfc/register")
async def register_nfc(data: dict, current_user: dict = Depends(get_current_user)):
    member_id = data.get("member_id")
    serial_number = data.get("serial_number")
    if not member_id or not serial_number:
        raise HTTPException(status_code=400, detail="member_id and serial_number required")
    existing = await db.nfc_tags.find_one({"serial_number": serial_number})
    if existing:
        raise HTTPException(status_code=409, detail="NFC tag already registered")
    doc = {"id": f"nfc_{str(uuid.uuid4())[:8]}", "member_id": member_id, "serial_number": serial_number,
           "registered_by": current_user["id"], "created_at": datetime.now(timezone.utc).isoformat()}
    await db.nfc_tags.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/nfc/scan")
async def scan_nfc(data: dict):
    serial_number = data.get("serial_number")
    if not serial_number:
        raise HTTPException(status_code=400, detail="serial_number required")
    tag = await db.nfc_tags.find_one({"serial_number": serial_number}, {"_id": 0})
    if not tag:
        raise HTTPException(status_code=404, detail="NFC tag not registered")
    member = await db.members.find_one(
        {"id": tag["member_id"]},
        {"_id": 0, "id": 1, "name": 1, "role": 1, "group": 1},
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"member": member, "tag_id": tag["id"]}
