"""NFC tag CRUD + write logging + signed-payload generation + verification."""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, require_staff, require_director
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["members"])


async def _resolve_member(person_id: str) -> dict:
    """Return a member document for the given id, treating it as either a
    member_id or a user_id. Auto-creates a minimal member row for users
    who never had a member profile (e.g. Security Contractors created
    directly from the admin dialog) so their NFC/QR data has somewhere to
    live and the checkpoint kiosk can recognise them.
    """
    member = await db.members.find_one({"id": person_id}, {"_id": 0})
    if member:
        return member
    # Fall back to treating it as a user id — auto-create linked member.
    user = await db.users.find_one({"id": person_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Person not found")
    member = await db.members.find_one({"user_id": user["id"]}, {"_id": 0})
    if member:
        return member
    new_member = {
        "id": f"mbr_{uuid.uuid4().hex[:10]}",
        "user_id": user["id"],
        "name": user.get("name", ""),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role"),
        "location_id": user.get("location_id"),
        "photo_url": user.get("photo_url"),
        "nfc_tags": [],
        "status": user.get("status", "active"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "auto_created_from_user": True,
    }
    await db.members.insert_one(new_member)
    return new_member


@router.get("/members/{member_id}/nfc-tags")
async def get_member_nfc_tags(member_id: str, current_user: dict = Depends(get_current_user)) -> list:
    """Get NFC tags associated with a member."""
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "nfc_tags": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member.get("nfc_tags", [])


@router.post("/members/{member_id}/nfc-tags")
async def add_nfc_tag(member_id: str, data: dict, current_user: dict = Depends(require_staff)) -> dict:
    """Add an NFC tag to a member profile. Body: { serial_number, label? }"""
    serial = (data.get("serial_number") or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="NFC serial_number is required")
    # Check if tag is already assigned to another member
    existing = await db.members.find_one(
        {"nfc_tags.serial_number": serial, "id": {"$ne": member_id}},
        {"_id": 0, "id": 1, "name": 1}
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"This NFC tag is already assigned to {existing.get('name', 'another member')}")
    tag = {
        "id": f"nfc_{uuid.uuid4().hex[:8]}",
        "serial_number": serial,
        "label": data.get("label", ""),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "added_by": current_user["id"],
    }
    await db.members.update_one({"id": member_id}, {"$push": {"nfc_tags": tag}})
    # Also store on user record if linked
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "user_id": 1})
    if member and member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$push": {"nfc_tags": tag}})
    await _audit(current_user["id"], "create", "nfc_tag", member_id, {"serial": serial})
    return tag


@router.delete("/members/{member_id}/nfc-tags/{tag_id}")
async def remove_nfc_tag(member_id: str, tag_id: str, current_user: dict = Depends(require_staff)) -> dict:
    """Remove an NFC tag from a member profile."""
    result = await db.members.update_one(
        {"id": member_id},
        {"$pull": {"nfc_tags": {"id": tag_id}}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="NFC tag not found")
    # Also remove from user record
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "user_id": 1})
    if member and member.get("user_id"):
        await db.users.update_one({"id": member["user_id"]}, {"$pull": {"nfc_tags": {"id": tag_id}}})
    await _audit(current_user["id"], "delete", "nfc_tag", member_id, {"tag_id": tag_id})
    return {"message": "NFC tag removed"}


@router.post("/members/{member_id}/nfc-write")
async def write_nfc_tag(member_id: str, data: dict, current_user: dict = Depends(require_director)) -> dict:
    """Record that an NFC tag was written with this member's data. Director+ only.
    Body: { serial_number, written_data?, label? }
    This also adds the tag to the member's profile if not already present.
    Accepts either a member_id or a user_id in the path — will auto-create a
    linked member profile for a raw user so their NFC data has somewhere to live."""
    serial = (data.get("serial_number") or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="NFC serial_number is required")
    member = await _resolve_member(member_id)
    member_id = member["id"]
    # Check duplicate on other members
    existing = await db.members.find_one(
        {"nfc_tags.serial_number": serial, "id": {"$ne": member_id}},
        {"_id": 0, "id": 1, "name": 1}
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"NFC tag already assigned to {existing.get('name', 'another member')}")
    # Add tag if not already present on this member
    current_tags = member.get("nfc_tags") or []
    already_has = any(t.get("serial_number") == serial for t in current_tags)
    tag = None
    if not already_has:
        tag = {
            "id": f"nfc_{uuid.uuid4().hex[:8]}",
            "serial_number": serial,
            "label": data.get("label", ""),
            "added_at": datetime.now(timezone.utc).isoformat(),
            "added_by": current_user["id"],
            "written": True,
        }
        await db.members.update_one({"id": member_id}, {"$push": {"nfc_tags": tag}})
        if member.get("user_id"):
            await db.users.update_one({"id": member["user_id"]}, {"$push": {"nfc_tags": tag}})
    else:
        # Mark existing tag as written
        await db.members.update_one(
            {"id": member_id, "nfc_tags.serial_number": serial},
            {"$set": {"nfc_tags.$.written": True, "nfc_tags.$.written_at": datetime.now(timezone.utc).isoformat(), "nfc_tags.$.written_by": current_user["id"]}}
        )
        tag = next((t for t in current_tags if t.get("serial_number") == serial), None)
    # Log the write event
    await db.nfc_write_log.insert_one({
        "id": str(uuid.uuid4()),
        "member_id": member_id,
        "member_name": member.get("name", ""),
        "serial_number": serial,
        "written_data": data.get("written_data", member_id),
        "written_by": current_user["id"],
        "written_at": datetime.now(timezone.utc).isoformat(),
    })
    await _audit(current_user["id"], "create", "nfc_write", member_id, {"serial": serial})
    return {"message": "NFC tag written and linked", "tag": tag, "member_id": member_id, "member_name": member.get("name", "")}


@router.post("/members/{member_id}/nfc-payload")
async def generate_nfc_payload(member_id: str, current_user: dict = Depends(require_director)) -> dict:
    """Generate a signed, encrypted NFC payload for writing to a tag.
    The payload includes the member_id + HMAC signature so it can be verified on read.
    Accepts either member_id or user_id (auto-resolves)."""
    import hmac
    import hashlib
    import os
    member = await _resolve_member(member_id)
    member_id = member["id"]
    secret = os.environ.get("NFC_SECRET_KEY", "5812-global-nfc-secret-2026")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    payload = f"{member_id}|{timestamp}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    signed_payload = f"5812:{member_id}:{timestamp}:{signature}"
    return {
        "payload": signed_payload,
        "member_id": member_id,
        "member_name": member.get("name", ""),
        "instructions": "Write this payload to the NFC tag, then lock it as read-only."
    }


@router.post("/nfc/verify")
async def verify_nfc_payload(data: dict, current_user: dict = Depends(get_current_user)) -> dict:
    """Verify a signed NFC payload read from a tag."""
    import hmac
    import hashlib
    import os
    payload_str = (data.get("payload") or "").strip()
    if not payload_str or not payload_str.startswith("5812:"):
        return {"valid": False, "reason": "Not a 58:12 Global NFC tag"}
    parts = payload_str.split(":")
    if len(parts) < 4:
        return {"valid": False, "reason": "Malformed NFC data"}
    member_id = parts[1]
    timestamp = parts[2]
    received_sig = parts[3]
    secret = os.environ.get("NFC_SECRET_KEY", "5812-global-nfc-secret-2026")
    expected_payload = f"{member_id}|{timestamp}"
    expected_sig = hmac.new(secret.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(received_sig, expected_sig):
        return {"valid": False, "reason": "Signature mismatch — tag may be forged"}
    # Look up the member
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "id": 1, "name": 1, "role": 1, "photo_url": 1})
    if not member:
        user = await db.users.find_one({"id": member_id}, {"_id": 0, "id": 1, "name": 1, "role": 1, "photo_url": 1})
        member = user
    return {"valid": True, "member_id": member_id, "member": member, "written_date": timestamp}
