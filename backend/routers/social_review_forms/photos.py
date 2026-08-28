"""Visit-photo attachment endpoints (per review).

Photos appear as a gallery on the review row in the social-work UI and are
also mirrored into `db.child_extras` (kind='gallery') so they show up in the
existing child-extras gallery and on sponsor updates when
`is_public_for_sponsor` is enabled.
"""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from deps import db, _audit, require_staff, logger

router = APIRouter(prefix="/api/social-work/reviews", tags=["social_work_reviews"])


@router.post("/{review_id}/photos")
async def upload_review_photo(
    review_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    current_user: dict = Depends(require_staff),
):
    rev = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0, "id": 1, "child_id": 1, "child_name": 1, "location_id": 1, "kind": 1})
    if not rev:
        raise HTTPException(status_code=404, detail="Review form not found")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Photo must be an image")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo must be under 10 MB")

    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    unique = f"{review_id}-{uuid.uuid4().hex[:8]}.{ext}"
    file_url = None
    try:
        from upload_helper import save_upload
        file_url = await save_upload("review-photos", unique, data, file.content_type)
    except Exception as e:
        logger.warning(f"Review photo upload failed: {e}")
        raise HTTPException(status_code=502, detail="Could not save photo")

    photo_id = f"vph_{uuid.uuid4().hex[:10]}"
    photo = {
        "id": photo_id,
        "url": file_url,
        "caption": (caption or "")[:300],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
    }
    await db.social_review_forms.update_one({"id": review_id}, {"$push": {"photos": photo}})

    # Mirror into child_extras so the photo also appears in the existing gallery
    try:
        await db.child_extras.insert_one({
            "id": f"cex_{uuid.uuid4().hex[:10]}",
            "child_id": rev["child_id"],
            "child_name": rev.get("child_name"),
            "kind": "gallery",
            "caption": (caption or f"Visit photo — {rev.get('kind', 'review').replace('_', ' ')}")[:300],
            "file_url": file_url,
            "file_name": file.filename,
            "is_public_for_sponsor": False,
            "location_id": rev.get("location_id"),
            "review_id": review_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
            "created_by_name": current_user.get("name", ""),
        })
    except Exception as e:
        logger.warning(f"child_extras mirror failed: {e}")
    await _audit(current_user["id"], "create", "review_photo", review_id, {"photo_id": photo_id})
    return photo


@router.delete("/{review_id}/photos/{photo_id}")
async def delete_review_photo(review_id: str, photo_id: str, current_user: dict = Depends(require_staff)):
    rev = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0, "photos": 1})
    if not rev:
        raise HTTPException(status_code=404, detail="Review form not found")
    photo = next((p for p in (rev.get("photos") or []) if p.get("id") == photo_id), None)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found on this review")
    await db.social_review_forms.update_one({"id": review_id}, {"$pull": {"photos": {"id": photo_id}}})
    # Soft-delete the child_extras mirror too (find by URL match)
    try:
        if photo.get("url"):
            await db.child_extras.delete_many({"file_url": photo["url"], "review_id": review_id})
    except Exception:
        pass
    return {"deleted": True}
