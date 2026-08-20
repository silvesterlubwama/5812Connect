"""CRUD endpoints for filled social-work review forms.

Every save/update also pushes structured fields back onto the child's profile
(see child_sync.py) and appends a rich note to the active case timeline
(see timeline.py) so downstream views see fresh data without extra wiring.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, _audit, require_staff

from ._common import VALID_KINDS
from .child_sync import _apply_review_to_child
from .timeline import _append_timeline_note

router = APIRouter(prefix="/api/social-work/reviews", tags=["social_work_reviews"])


@router.get("/children/{child_id}")
async def list_child_reviews(
    child_id: str,
    kind: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Timeline of review forms filed for one child. Campus-scoped for
    non-privileged staff — anyone with social_work module access or sysadmin
    sees every review for any child in their campus tree."""
    from deps import is_system_admin, has_module_access, get_campus_filter
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "location_id": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    if not is_system_admin(current_user) and not has_module_access(current_user, "social_work"):
        scope = await get_campus_filter(current_user)
        child_loc = child.get("location_id") or ""
        allowed_locs = (scope.get("location_id", {}) or {}).get("$in", []) if scope else []
        if child_loc and allowed_locs and child_loc not in allowed_locs:
            raise HTTPException(status_code=403, detail="Child is outside your campus scope")
    query = {"child_id": child_id}
    if kind:
        if kind not in VALID_KINDS:
            raise HTTPException(status_code=400, detail="kind must be school_progress or welfare_visit")
        query["kind"] = kind
    rows = await db.social_review_forms.find(query, {"_id": 0}).sort("review_date", -1).to_list(500)
    return rows


@router.get("/{review_id}")
async def get_review(review_id: str, current_user: dict = Depends(require_staff)):
    rev = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=404, detail="Review form not found")
    return rev


@router.post("/children/{child_id}")
async def create_review(child_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Submit a filled review form. On save we ALSO push the relevant structured
    fields back into the child's profile so the existing report generator
    surfaces them without extra wiring."""
    kind = (data.get("kind") or "").strip()
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail="kind must be school_progress or welfare_visit")
    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "name": 1, "family_id": 1, "location_id": 1})
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    review_date = (data.get("review_date") or datetime.now(timezone.utc).date().isoformat())[:10]
    review_id = f"rev_{uuid.uuid4().hex[:10]}"
    doc = {
        "id": review_id,
        "child_id": child_id,
        "child_name": child.get("name", ""),
        "family_id": child.get("family_id"),
        "location_id": child.get("location_id"),
        "kind": kind,
        "review_date": review_date,
        "fields": data.get("fields") or {},
        "action_plan": data.get("action_plan") or [],
        "overall_assessment": data.get("overall_assessment") or "",
        "social_worker_id": current_user["id"],
        "social_worker_name": current_user.get("name", ""),
        "term": data.get("term") or "",
        "next_visit_date": data.get("next_visit_date") or "",
        "attached_scan_url": data.get("attached_scan_url") or "",
        "status": "submitted",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.social_review_forms.insert_one(doc)
    doc.pop("_id", None)

    await _apply_review_to_child(child_id, kind, data, current_user, review_id)
    await _append_timeline_note(child_id, kind, doc, current_user, review_id)
    await _audit(current_user["id"], "create", "social_review", review_id, {"kind": kind, "child_id": child_id})
    return doc


@router.put("/{review_id}")
async def update_review(review_id: str, data: dict, current_user: dict = Depends(require_staff)):
    rev = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=404, detail="Review form not found")
    allowed = {"fields", "action_plan", "overall_assessment", "term", "next_visit_date", "review_date", "attached_scan_url", "status"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    await db.social_review_forms.update_one({"id": review_id}, {"$set": update})
    fresh = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0})
    await _apply_review_to_child(rev["child_id"], rev["kind"], {**rev, **update}, current_user, review_id)
    return fresh


@router.delete("/{review_id}")
async def delete_review(review_id: str, current_user: dict = Depends(require_staff)):
    rev = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0})
    if not rev:
        raise HTTPException(status_code=404, detail="Review form not found")
    rev["_deleted_from"] = "social_review_forms"
    rev["deleted_at"] = datetime.now(timezone.utc).isoformat()
    rev["deleted_by"] = current_user["id"]
    await db.deleted_items.insert_one(rev)
    await db.social_review_forms.delete_one({"id": review_id})
    return {"deleted": True}
