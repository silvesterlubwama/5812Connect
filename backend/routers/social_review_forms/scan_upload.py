"""Upload a scanned filled paper form.

v2 flow: saves the scan + creates a draft review IMMEDIATELY (< 1 s), then
kicks off Gemini OCR as a background task. The HTTP response comes back fast
so we never hit the ingress proxy timeout — even for handwriting-heavy pages
that take 30-40 s to OCR.

Frontend behaviour:
  • Response arrives with `ocr.pending: true` — show "OCR running…" toast
  • Poll `GET /:review_id` every 5 s (or refresh the list) — OCR meta flips
    to `ran: true` + `confidence: high|medium|low` when done
  • If `ocr.error` set, user can transcribe manually via the row's dialog
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from deps import db, _audit, require_staff, logger

from ._common import VALID_KINDS
from .ocr import _ocr_background

router = APIRouter(prefix="/api/social-work/reviews", tags=["social_work_reviews"])


@router.post("/children/{child_id}/upload-scan")
async def upload_filled_scan(
    child_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kind: str = Form("welfare_visit"),
    review_date: Optional[str] = Form(None),
    run_ocr: bool = Form(True),
    current_user: dict = Depends(require_staff),
):
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of: {', '.join(sorted(VALID_KINDS))}")
    if not file.content_type or not (file.content_type == "application/pdf" or file.content_type.startswith("image/")):
        raise HTTPException(status_code=400, detail="Scan must be a PDF or image")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Scan must be under 15 MB")

    child = await db.children.find_one({"id": child_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "family_id": 1})
    if not child:
        # Social-work cases can also be opened against members (staff/adult
        # subjects). Fall back to the members collection so their scan uploads
        # don't 404 with "Child not found".
        member = await db.members.find_one({"id": child_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1})
        if member:
            child = {"id": member["id"], "name": member.get("name", ""), "location_id": member.get("location_id"), "family_id": None}
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # 1) Persist the raw scan (fast — no LLM in this path)
    #
    # We ALWAYS save to local disk first (a few ms) so the HTTP response
    # returns quickly and Cloudflare never sees a 524 timeout. The cloud
    # upload is then attempted with a tight 15 s wall-clock via a thread
    # (blocking `requests` calls otherwise pin the asyncio event loop and
    # can hang the entire worker for the full 120 s timeout).
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "pdf"
    unique = f"{child_id}-{kind}-{uuid.uuid4().hex[:8]}.{ext}"
    # iter 264 — disk-only, via the shared upload helper. We deliberately
    # skip the cloud round-trip here because scan_upload runs a blocking
    # OCR pipeline right after, and the disk hop needs to be fast enough
    # that Cloudflare never sees a 524.
    from upload_helper import _disk_fallback
    _disk_fallback("social-review-scans", unique, data)
    local_path = f"/app/backend/uploads/social-review-scans/{unique}"
    file_url = f"/api/uploads/social-review-scans/{unique}"

    # 2) Insert the draft review NOW so the frontend has something to poll
    # PDFs are now OCR-able too — pdf2image converts the first page to PNG
    # before we hand off to Gemini.
    will_ocr = bool(run_ocr and (
        file.content_type.startswith("image/") or file.content_type == "application/pdf"
    ))
    rdate = (review_date or datetime.now(timezone.utc).date().isoformat())[:10]
    review_id = f"rev_{uuid.uuid4().hex[:10]}"
    rev = {
        "id": review_id,
        "child_id": child_id,
        "child_name": child.get("name", ""),
        "family_id": child.get("family_id"),
        "location_id": child.get("location_id"),
        "kind": kind,
        "review_date": rdate,
        "fields": {}, "action_plan": [], "overall_assessment": "", "next_visit_date": "",
        "attached_scan_url": file_url,
        "ocr": {
            "ran": False,
            "pending": will_ocr,   # Frontend keys off this to show "OCR running…" state
            "confidence": "",
            "error": None if will_ocr else "OCR skipped (run_ocr=false)",
            "raw_text": "",
            "completed_at": None,
        },
        "status": "ocr_pending" if will_ocr else "draft_scan_only",
        "social_worker_id": current_user["id"],
        "social_worker_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.social_review_forms.insert_one(rev)
    rev.pop("_id", None)

    async def _try_cloud_upload():
        """Best-effort upload to object storage. If cloud responds within 15 s
        we swap the review's `attached_scan_url` to the cloud URL; otherwise
        the local URL keeps working."""
        try:
            from storage import put_object
            result = await asyncio.wait_for(
                asyncio.to_thread(put_object, f"social-review-scans/{unique}", data, file.content_type),
                timeout=15.0,
            )
            cloud_url = result.get("url", f"/api/storage/social-review-scans/{unique}")
            await db.social_review_forms.update_one({"id": review_id}, {"$set": {"attached_scan_url": cloud_url}})
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Cloud storage upload skipped/failed (using local): {e}")

    # Cloud upload runs in the background so the HTTP response returns fast.
    background_tasks.add_task(_try_cloud_upload)

    # 3) Kick off OCR in the background (fire-and-forget). Snapshot the user
    # so we don't hold a DB cursor open across the request boundary.
    if will_ocr:
        user_snap = {
            "id": current_user["id"],
            "name": current_user.get("name", ""),
            "role": current_user.get("role", ""),
        }
        background_tasks.add_task(
            _ocr_background, review_id, child_id, kind, data, file.content_type, user_snap,
        )

    # 4) Mirror into child_extras gallery for visual discovery (fast)
    # We insert TWO rows: kind='report' feeds the social-work reviews list and
    # kind='file_doc' surfaces the scan inside the child's Documents tab so
    # authorised staff have a single, searchable "official documents" view.
    doc_type_key = {
        "welfare_visit": "home_visit_report",
        "school_progress": "school_report",
        "medical_exam": "medical_report",
    }.get(kind, "other")
    doc_type_label = {
        "welfare_visit": "Home Visit Report",
        "school_progress": "School Progress Report",
        "medical_exam": "Medical Report",
    }.get(kind, "Social work document")
    try:
        await db.child_extras.insert_many([
            {
                "id": f"cex_{uuid.uuid4().hex[:10]}",
                "child_id": child_id,
                "child_name": child.get("name"),
                "kind": "report",
                "caption": f"{'OCR running…' if will_ocr else 'Filled (transcribe)'} {kind.replace('_', ' ')} ({rdate})",
                "file_url": file_url,
                "file_name": file.filename,
                "is_public_for_sponsor": False,
                "location_id": child.get("location_id"),
                "review_id": review_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": current_user["id"],
                "created_by_name": current_user.get("name", ""),
            },
            {
                "id": f"cex_{uuid.uuid4().hex[:10]}",
                "child_id": child_id,
                "child_name": child.get("name"),
                "kind": "file_doc",
                "doc_type": doc_type_key,
                "doc_label": doc_type_label,
                "caption": f"{doc_type_label} — {rdate}",
                "issued_date": rdate,
                "file_url": file_url,
                "file_name": file.filename,
                "file_size": len(data),
                "is_public_for_sponsor": False,
                "location_id": child.get("location_id"),
                "review_id": review_id,
                "auto_mirrored_from_review": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": current_user["id"],
                "created_by_name": current_user.get("name", ""),
            },
        ])
    except Exception as e:
        logger.warning(f"child_extras mirror failed: {e}")

    await _audit(current_user["id"], "create", "social_review_scan", review_id,
                 {"kind": kind, "child_id": child_id, "ocr_will_run": will_ocr})
    return rev
