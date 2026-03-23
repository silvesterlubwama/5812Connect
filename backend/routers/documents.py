"""Member document storage and ID scans"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from typing import Optional
from datetime import datetime, timezone
import uuid

from deps import db, get_current_user
from storage import put_object, get_object, APP_NAME

router = APIRouter(prefix="/api", tags=["documents"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def _validate_file(file: UploadFile):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG/PNG files are supported")
    ext = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension")
    return ext


@router.post("/members/{member_id}/documents")
async def upload_member_document(
    member_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("id_scan"),
    label: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    member = await db.members.find_one({"id": member_id}, {"_id": 0, "role": 1, "group": 1, "name": 1})
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if doc_type == "id_scan":
        role = (member.get("role") or "").lower()
        if role == "child" or member.get("group") == "Children":
            raise HTTPException(status_code=400, detail="Children do not require ID scans")

    ext = _validate_file(file)
    data = await file.read()
    storage_path = f"{APP_NAME}/uploads/{member_id}/{uuid.uuid4()}.{ext}"
    result = put_object(storage_path, data, file.content_type or "application/octet-stream")

    doc = {
        "id": f"doc_{str(uuid.uuid4())[:8]}",
        "member_id": member_id,
        "member_name": member.get("name"),
        "doc_type": doc_type,
        "label": label or doc_type.replace("_", " ").title(),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.files.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/members/{member_id}/documents")
async def list_member_documents(member_id: str, current_user: dict = Depends(get_current_user)):
    docs = await db.files.find({"member_id": member_id, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.get("/members/{member_id}/documents/id-scan")
async def latest_id_scan(member_id: str, current_user: dict = Depends(get_current_user)):
    doc = await db.files.find_one(
        {"member_id": member_id, "doc_type": "id_scan", "is_deleted": False},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not doc:
        raise HTTPException(status_code=404, detail="ID scan not found")
    return doc


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    record = await db.files.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type))


@router.put("/documents/{doc_id}/archive")
async def archive_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    await db.files.update_one({"id": doc_id}, {"$set": {"is_deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Document archived"}
