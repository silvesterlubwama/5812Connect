"""Member document storage (local fs) and document request workflow"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import FileResponse
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
import uuid
import os

from deps import db, get_current_user, require_manager, _audit

router = APIRouter(prefix="/api", tags=["documents"])

UPLOAD_DIR = Path("/app/backend/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "pdf", "doc", "docx"}

ID_TYPES = [
    "national_id", "state_id", "drivers_license", "passport",
    "birth_certificate", "refugee_id", "alien_id", "voter_card",
    "student_id", "employee_id", "other",
]


def _validate_file(file: UploadFile):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension")
    return ext


def _save_file(member_id: str, data: bytes, ext: str) -> str:
    """Save to local filesystem, return relative path"""
    member_dir = UPLOAD_DIR / member_id
    member_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = member_dir / filename
    file_path.write_bytes(data)
    return str(file_path.relative_to(UPLOAD_DIR.parent))  # relative to /app/backend


# =================== DOCUMENTS CRUD ===================

@router.get("/documents/id-types")
async def list_id_types(current_user: dict = Depends(get_current_user)):
    return ID_TYPES


@router.get("/documents/available-types/{member_id}")
async def available_doc_types(member_id: str, current_user: dict = Depends(get_current_user)):
    """Return document types that haven't been uploaded yet or are expired"""
    existing = await db.member_documents.find({"member_id": member_id}, {"_id": 0, "doc_type": 1, "expires_at": 1}).to_list(50)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    uploaded_valid = set()
    for doc in existing:
        exp = doc.get("expires_at", "")
        if not exp or exp > today:
            uploaded_valid.add(doc.get("doc_type"))
    available = [t for t in ID_TYPES if t["value"] not in uploaded_valid]
    return {"available": available, "uploaded_valid": list(uploaded_valid)}


@router.post("/members/{member_id}/documents")
async def upload_member_document(
    member_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    label: Optional[str] = Form(None),
    request_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Upload a document for a member or user. Accepts both member_id and user_id.
    Staff/admin can upload for any member. Members can only upload their own documents."""
    # Try members collection first
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "role": 1, "group": 1, "name": 1, "email": 1})
    if not member:
        # Fallback: check if this is a user_id and find their linked member record
        user = await db.users.find_one({"id": member_id}, {"_id": 0, "id": 1, "name": 1, "email": 1})
        if user:
            member = await db.members.find_one(
                {"$or": [{"user_id": member_id}, {"email": user.get("email", "__none__")}]},
                {"_id": 0, "id": 1, "role": 1, "group": 1, "name": 1, "email": 1}
            )
            if member:
                member_id = member["id"]
            else:
                # No member profile exists, use user data directly
                member = {"name": user.get("name"), "email": user.get("email"), "role": "user"}
        else:
            raise HTTPException(status_code=404, detail="Member not found")

    # Access check: member can only upload their own docs
    role = (current_user.get("role") or "").lower()
    is_staff = role in {"admin", "system_admin", "executive director", "director", "manager", "coordinator", "staff", "hr"}
    if not is_staff:
        # Check if this user is the member
        user_record = await db.members.find_one(
            {"email": current_user.get("email")}, {"_id": 0, "id": 1}
        )
        if not user_record or user_record.get("id") != member_id:
            raise HTTPException(status_code=403, detail="You can only upload your own documents")

    ext = _validate_file(file)
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    local_path = _save_file(member_id, data, ext)

    doc = {
        "id": f"doc_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "member_name": member.get("name"),
        "doc_type": doc_type,
        "label": label or doc_type.replace("_", " ").title(),
        "local_path": local_path,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.files.insert_one(doc)
    doc.pop("_id", None)

    # Fulfill a pending request if request_id provided
    if request_id:
        await db.document_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "fulfilled", "fulfilled_at": datetime.now(timezone.utc).isoformat(), "doc_id": doc["id"]}}
        )

    await _audit(current_user["id"], "create", "document", doc["id"], {"member_id": member_id, "doc_type": doc_type})
    return doc


@router.get("/members/{member_id}/documents")
async def list_member_documents(member_id: str, current_user: dict = Depends(get_current_user)):
    # Also check if member_id is actually a user_id and resolve the real member_id
    resolved_id = member_id
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "id": 1})
    if not member:
        user = await db.users.find_one({"id": member_id}, {"_id": 0, "email": 1})
        if user:
            linked = await db.members.find_one(
                {"$or": [{"user_id": member_id}, {"email": user.get("email", "__none__")}]},
                {"_id": 0, "id": 1}
            )
            if linked:
                resolved_id = linked["id"]
    docs = await db.files.find({"member_id": {"$in": [member_id, resolved_id]}, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.get("/documents/{doc_id}/file")
async def serve_document_file(doc_id: str, current_user: dict = Depends(get_current_user)):
    """Serve file from local storage"""
    record = await db.files.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = Path("/app/backend") / record["local_path"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=str(file_path),
        media_type=record.get("content_type", "application/octet-stream"),
        filename=record.get("original_filename", doc_id),
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    record = await db.files.find_one({"id": doc_id}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    # Delete from disk
    if record.get("local_path"):
        file_path = Path("/app/backend") / record["local_path"]
        if file_path.exists():
            file_path.unlink()
    await db.files.update_one({"id": doc_id}, {"$set": {"is_deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Document deleted"}


# =================== DOCUMENT REQUESTS ===================

@router.post("/document-requests")
async def create_document_request(data: dict, current_user: dict = Depends(get_current_user)):
    """Admin/manager/HR requests a document from a member"""
    role = (current_user.get("role") or "").lower()
    allowed_roles = {"admin", "system_admin", "executive director", "director", "manager", "coordinator", "hr", "staff"}
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions to request documents")

    member_id = data.get("member_id")
    if not member_id:
        raise HTTPException(status_code=400, detail="member_id is required")

    member = await db.members.find_one({"id": member_id}, {"_id": 0, "name": 1, "id": 1})
    if not member:
        # Fallback: resolve user_id to member
        user = await db.users.find_one({"id": member_id}, {"_id": 0, "name": 1, "email": 1})
        if user:
            linked = await db.members.find_one(
                {"$or": [{"user_id": member_id}, {"email": user.get("email", "__none__")}]},
                {"_id": 0, "name": 1, "id": 1}
            )
            if linked:
                member = linked
                member_id = linked["id"]
            else:
                member = {"name": user.get("name")}
        else:
            raise HTTPException(status_code=404, detail="Member not found")

    doc_type = data.get("doc_type", "other")
    if doc_type not in ID_TYPES:
        doc_type = "other"

    req = {
        "id": f"req_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "member_name": member.get("name"),
        "doc_type": doc_type,
        "doc_type_label": doc_type.replace("_", " ").title(),
        "message": data.get("message", ""),
        "status": "pending",
        "requested_by": current_user["id"],
        "requested_by_name": current_user.get("name"),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "doc_id": None,
        "fulfilled_at": None,
    }
    await db.document_requests.insert_one(req)
    req.pop("_id", None)
    await _audit(current_user["id"], "create", "document_request", req["id"], {"member_id": member_id, "doc_type": doc_type})
    return req


@router.get("/document-requests")
async def list_document_requests(
    member_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """List document requests. Staff sees all; members see only their own."""
    role = (current_user.get("role") or "").lower()
    is_staff = role in {"admin", "system_admin", "executive director", "director", "manager", "coordinator", "hr", "staff"}

    query = {}
    if is_staff:
        if member_id:
            query["member_id"] = member_id
    else:
        # Find member record for this user
        user_member = await db.members.find_one({"email": current_user.get("email")}, {"_id": 0, "id": 1})
        if user_member:
            query["member_id"] = user_member["id"]
        else:
            return []

    if status and status != "all":
        query["status"] = status

    reqs = await db.document_requests.find(query, {"_id": 0}).sort("requested_at", -1).to_list(200)
    return reqs


@router.delete("/document-requests/{request_id}")
async def cancel_document_request(request_id: str, current_user: dict = Depends(get_current_user)):
    role = (current_user.get("role") or "").lower()
    is_staff = role in {"admin", "system_admin", "executive director", "director", "manager", "coordinator", "hr", "staff"}
    if not is_staff:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await db.document_requests.update_one(
        {"id": request_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Request cancelled"}
