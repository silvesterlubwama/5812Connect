"""Gemini-3-Flash OCR pipeline for filled review scans.

Two entrypoints:
  • `_ocr_review_form(...)` — pure OCR call (raises on hard failures)
  • `_ocr_background(...)`  — background task that OCRs, patches the review
    row, cross-checks DOB, WebSocket-notifies the uploader, and re-syncs the
    child profile. Never raises; every failure is logged onto `review.ocr.error`.

The system prompts are big JSON-schema instructions kept co-located with the
OCR call so their shape is verifiable at a glance without extra hops.
"""
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException

from deps import db, logger

from .child_sync import _apply_review_to_child
from .timeline import _append_timeline_note


async def _ocr_review_form(file_bytes: bytes, mime: str, kind: str, user_id: str) -> dict:
    """Send a filled-form image to Gemini 3 Flash and extract structured `fields`
    matching the schema for `kind`. Returns {fields, action_plan, overall_assessment,
    review_date, ocr_confidence, raw_text}. Raises HTTPException on hard failures
    so the caller can decide to fall back to draft-scan-only."""
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty scan")

    # MIME normalization — Gemini wants jpeg/png/webp. PDFs get converted to
    # a PNG via pdf2image (poppler). Multi-page PDFs are stitched vertically
    # into a single tall image so Gemini sees every page in one pass.
    detected = mime.lower()
    if detected == "application/pdf" or file_bytes[:4] == b"%PDF":
        try:
            from pdf2image import convert_from_bytes
            from PIL import Image
            import io as _io
            pages = convert_from_bytes(file_bytes, dpi=200, fmt="png")
            if not pages:
                raise HTTPException(status_code=415, detail="PDF has no pages")
            if len(pages) == 1:
                composite = pages[0]
            else:
                # Stitch pages vertically. Max height guard: Gemini has a
                # ~20 MP practical ceiling; if we'd blow past ~15000 px total
                # height we downscale each page proportionally.
                width = max(p.width for p in pages)
                total_h = sum(p.height for p in pages)
                scale = min(1.0, 15000 / total_h)
                if scale < 1.0:
                    pages = [p.resize((int(p.width * scale), int(p.height * scale))) for p in pages]
                    width = max(p.width for p in pages)
                    total_h = sum(p.height for p in pages)
                composite = Image.new("RGB", (width, total_h), "white")
                y = 0
                for p in pages:
                    composite.paste(p, (0, y))
                    y += p.height
            buf = _io.BytesIO()
            composite.save(buf, format="PNG", optimize=True)
            file_bytes = buf.getvalue()
            detected = "image/png"
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"PDF→PNG conversion failed: {e}")
            raise HTTPException(status_code=415, detail=f"Could not convert PDF for OCR ({e})")
    elif detected not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        if file_bytes[:3] == b"\xff\xd8\xff":
            detected = "image/jpeg"
        elif file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            detected = "image/png"
        elif file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
            detected = "image/webp"
        else:
            raise HTTPException(status_code=415, detail="OCR supports JPEG/PNG/WEBP images and PDF")
    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="OCR not configured (no LLM key)")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OCR unavailable: {e}")

    fd, tmp_path = tempfile.mkstemp(suffix="." + detected.split("/")[-1])
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(file_bytes)
        system_prompt = _OCR_SYSTEM_PROMPTS[kind]
        chat = LlmChat(
            api_key=api_key,
            session_id=f"sw_review_ocr_{user_id}_{uuid.uuid4().hex[:6]}",
            system_message=system_prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text=(
                f"This is a filled paper {kind.replace('_', ' ')} form. Extract every ticked checkbox, "
                "rating circle, and handwritten note into the strict JSON schema specified in the system "
                "message. If a field is empty or unclear, return empty string / null / false as appropriate. "
                "Do NOT invent data. Set ocr_confidence to 'low' for any badly-photographed sections."
            ),
            file_contents=[FileContentWithMimeType(file_path=tmp_path, mime_type=detected)],
        )
        raw = await chat.send_message(msg)
        s = (raw or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:].strip()
        first, last = s.find("{"), s.rfind("}")
        if first >= 0 and last > first:
            s = s[first:last + 1]
        try:
            parsed = json.loads(s)
        except Exception as e:
            logger.warning(f"OCR JSON parse failed: {e} — raw: {(raw or '')[:200]}")
            return {"fields": {}, "action_plan": [], "overall_assessment": "",
                    "review_date": "", "ocr_confidence": "low",
                    "raw_text": (raw or "")[:500], "parse_error": True}
        # Sanitise structure — defensive defaults
        return {
            "fields": parsed.get("fields") or {},
            "action_plan": parsed.get("action_plan") or [],
            "overall_assessment": str(parsed.get("overall_assessment") or "").strip()[:120],
            "review_date": str(parsed.get("review_date") or "").strip()[:10],
            "next_visit_date": str(parsed.get("next_visit_date") or "").strip()[:10],
            "ocr_confidence": str(parsed.get("ocr_confidence") or "medium").lower(),
            "raw_text": str(parsed.get("raw_text") or "")[:2000],
        }
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


_OCR_SYSTEM_PROMPTS = {
    "school_progress": (
        "You are an OCR + structured-extraction assistant for a 58:12 Global child welfare org's "
        "School Progress Review forms (filled by hand at school visits). "
        "Output STRICT JSON — no prose, no markdown:\n"
        "{\n"
        '  "review_date": "YYYY-MM-DD" or empty,\n'
        '  "fields": {\n'
        '    "child_name": str, "dob": "YYYY-MM-DD"|"", "age": str,\n'
        '    "school": str, "class_grade": str, "term": str,\n'
        '    "academic_performance": {\n'
        '      "overall": {"rating": "Excellent"|"Good"|"Fair"|"Poor"|null, "comments": str},\n'
        '      "reading_writing": {"rating": ..., "comments": str},\n'
        '      "mathematics": {"rating": ..., "comments": str},\n'
        '      "participation": {"rating": ..., "comments": str}\n'
        '    },\n'
        '    "attendance_discipline": {\n'
        '      "regular_attendance": {"rating": "Yes"|"No"|null, "comments": str},\n'
        '      "punctual": {"rating": ..., "comments": str},\n'
        '      "discipline": {"rating": ..., "comments": str},\n'
        '      "homework": {"rating": ..., "comments": str}\n'
        '    },\n'
        '    "social_emotional": {\n'
        '      "peers": {"rating": "Good"|"Fair"|"Poor"|null, "comments": str},\n'
        '      "respect": {"rating": ..., "comments": str},\n'
        '      "confidence": {"rating": ..., "comments": str},\n'
        '      "cocurricular": {"rating": ..., "comments": str}\n'
        '    },\n'
        '    "strengths": str, "areas_requiring_support": str\n'
        '  },\n'
        '  "action_plan": [{"no": int, "concern": str, "action": str, "responsible": str, "timeline": str}],\n'
        '  "overall_assessment": "Excellent Progress"|"Good Progress"|"Satisfactory Progress"|"Needs Additional Support"|"Requires Immediate Follow-up"|"",\n'
        '  "ocr_confidence": "high"|"medium"|"low",\n'
        '  "raw_text": "everything legible from the page"\n'
        "}\n"
        "Read ticked boxes (☒, ✓, X, or filled circles). If multiple boxes are ticked in the same row, "
        "pick the one most-clearly marked. Empty rows → rating:null. Be conservative."
    ),
    "welfare_visit": (
        "You are an OCR + structured-extraction assistant for a 58:12 Global child welfare org's "
        "Child Welfare Review and Home Visit forms. Output STRICT JSON — no prose, no markdown:\n"
        "{\n"
        '  "review_date": "YYYY-MM-DD" or empty,\n'
        '  "next_visit_date": "YYYY-MM-DD" or empty,\n'
        '  "fields": {\n'
        '    "child_name": str, "dob": "YYYY-MM-DD"|"", "age": str, "sex": "male"|"female"|"",\n'
        '    "caregiver_name": str, "caregiver_relationship": str,\n'
        '    "village_parish": str, "district": str,\n'
        '    "welfare_indicators": { "physical_health": {"rating":"Good"|"Fair"|"Poor"|null,"comments":str},\n'
        '       "nutrition": {...}, "hygiene": {...}, "emotional": {...}, "safety": {...},\n'
        '       "school_attendance": {...}, "academic_progress": {...}, "family_support": {...}, "living_conditions": {...} },\n'
        '    "education_checks": { "enrolled": bool, "attends_regularly": bool, "has_materials": bool, "fees_met": bool, "progressing": bool },\n'
        '    "health_nutrition": { "healthy": bool, "accessed_medical": bool, "adequate_meals": bool, "has_disability": bool },\n'
        '    "protection_concerns": { "neglect": bool, "physical_abuse": bool, "emotional_abuse": bool, "child_labour": bool, "school_dropout_risk": bool, "early_marriage_risk": bool, "other_protection": bool },\n'
        '    "protection_details": str,\n'
        '    "household": { "caregiver_child": {"rating":...,"comments":str}, "household_stability": {...}, "housing": {...}, "water_sanitation": {...}, "family_capacity": {...} },\n'
        '    "child_voice": { "going_well": str, "challenges": str, "support_wanted": str },\n'
        '    "strengths": str, "challenges": str\n'
        '  },\n'
        '  "action_plan": [{"no": int, "concern": str, "action": str, "responsible": str, "timeline": str}],\n'
        '  "overall_assessment": "Thriving and progressing well"|"Requires routine monitoring"|"Requires additional support services"|"Requires urgent intervention"|"",\n'
        '  "ocr_confidence": "high"|"medium"|"low",\n'
        '  "raw_text": "everything legible"\n'
        "}\n"
        "All checkboxes default to false unless clearly ticked. Be especially careful with protection_concerns — "
        "false positives there cause incorrect protection alerts on the child's record."
    ),
    "medical_exam": (
        "You are an OCR + structured-extraction assistant for a 58:12 Global Child Enrollment "
        "Medical Examination Form. Output STRICT JSON — no prose, no markdown:\n"
        "{\n"
        '  "review_date": "YYYY-MM-DD or empty (use Date of Examination)",\n'
        '  "fields": {\n'
        '    "child_name": str, "dob": "YYYY-MM-DD"|"", "age": str, "sex": "male"|"female"|"",\n'
        '    "village": str, "parish": str, "sub_county": str, "district": str,\n'
        '    "guardian_name": str, "contact": str,\n'
        '    "medical_history": { "asthma": {"present": bool, "notes": str}, "epilepsy": {...},\n'
        '       "diabetes": {...}, "sickle_cell": {...}, "heart_disease": {...},\n'
        '       "tuberculosis": {...}, "hiv_aids": {...}, "chronic_illness": {...},\n'
        '       "other": {"present": bool, "specify": str, "notes": str} },\n'
        '    "current_medication": str, "known_allergies": str, "previous_admissions": str,\n'
        '    "general_condition": "Excellent"|"Good"|"Fair"|"Poor"|"",\n'
        '    "medical_remarks": str,\n'
        '    "nutritional_status": "Well Nourished"|"Mild Malnutrition"|"Moderate Malnutrition"|"Severe Malnutrition"|"",\n'
        '    "clinical_remarks": str,\n'
        '    "disability": { "has_disability": bool, "physical": bool, "visual": bool, "hearing": bool,\n'
        '       "intellectual": bool, "autism": bool, "speech_language": bool, "multiple": bool, "other": str },\n'
        '    "disability_description": str, "assistive_devices": str,\n'
        '    "mental_observations": str,  // one of: "No concerns observed","Emotional distress","Behavioural concerns","Developmental concerns","Trauma-related concerns","Other"\n'
        '    "mental_remarks": str,\n'
        '    "immunization_status": "Fully Immunized"|"Partially Immunized"|"Status Unknown"|"",\n'
        '    "immunization_card_verified": bool,\n'
        '    "diagnosis": str,\n'
        '    "recommendations": { "fit": bool, "fit_with_monitoring": bool, "needs_treatment": bool,\n'
        '       "needs_referral": bool, "needs_nutrition": bool, "needs_disability_support": bool },\n'
        '    "recommended_actions": str,\n'
        '    "referral": { "facility": str, "reason": str, "follow_up_date": "YYYY-MM-DD"|"" },\n'
        '    "practitioner": { "name": str, "qualification": str, "facility": str, "telephone": str, "exam_date": "YYYY-MM-DD"|"" }\n'
        '  },\n'
        '  "overall_assessment": "Medically fit"|"Fit with monitoring"|"Needs treatment"|"Needs referral"|"Needs nutritional support"|"Needs disability support"|"",\n'
        '  "ocr_confidence": "high"|"medium"|"low",\n'
        '  "raw_text": "everything legible"\n'
        "}\n"
        "Be extra careful with the past-medical-history table: read each row's Yes/No checkbox literally. "
        "False positives (e.g. recording 'epilepsy: present=true' when the No box was ticked) cause serious "
        "downstream harm — set present=false unless the Yes box is clearly marked."
    ),
}


async def _ocr_background(review_id: str, child_id: str, kind: str,
                          data: bytes, mime: str, user_snapshot: dict) -> None:
    """Runs after the client's HTTP response has already returned. Executes
    the Gemini OCR call (may take 20-40 s) and patches the review row with
    structured fields + auto-syncs into the child profile. Never raises —
    all failures are logged and stored on `review.ocr.error`.

    This decouples the slow LLM call from the ingress-proxy timeout, which
    used to bite users as generic "Upload failed" toasts."""
    try:
        payload = await _ocr_review_form(data, mime, kind, user_snapshot["id"])
    except HTTPException as e:
        payload = None
        err = e.detail
    except Exception as e:
        payload = None
        err = str(e)[:200]
        logger.error(f"OCR background failure for review {review_id}: {e}")
    else:
        err = None

    ocr_meta = {
        "ran": bool(payload),
        "pending": False,
        "confidence": (payload or {}).get("ocr_confidence", ""),
        "error": err,
        "raw_text": (payload or {}).get("raw_text", "")[:500] if payload else "",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    update: Dict[str, Any] = {"ocr": ocr_meta}
    if payload:
        rdate = payload.get("review_date") or datetime.now(timezone.utc).date().isoformat()
        update.update({
            "fields": payload.get("fields") or {},
            "action_plan": payload.get("action_plan") or [],
            "overall_assessment": payload.get("overall_assessment") or "",
            "next_visit_date": payload.get("next_visit_date") or "",
            "review_date": rdate[:10],
            "status": "submitted",
        })

        # ── DOB integrity check ────────────────────────────────
        # If Gemini read a DOB off the form, compare it against what's on the
        # child record. Mismatches probably mean the wrong child's form was
        # uploaded or somebody typo'd a date — surface it so staff can review.
        try:
            extracted_dob = (payload.get("fields") or {}).get("dob") or ""
            if extracted_dob and len(extracted_dob) >= 8:
                child = await db.children.find_one(
                    {"id": child_id},
                    {"_id": 0, "dob": 1, "date_of_birth": 1, "name": 1},
                ) or {}
                on_file = (child.get("dob") or child.get("date_of_birth") or "")[:10]
                if on_file and on_file != extracted_dob[:10]:
                    update["data_flags"] = {
                        "dob_mismatch": {
                            "on_file": on_file,
                            "on_form": extracted_dob[:10],
                            "child_name": child.get("name") or "",
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        }
                    }
                    logger.warning(
                        f"[social-work] DOB mismatch on review {review_id}: "
                        f"on-file={on_file} vs on-form={extracted_dob[:10]}"
                    )
        except Exception as e:
            logger.warning(f"DOB cross-check failed for review {review_id}: {e}")

    await db.social_review_forms.update_one({"id": review_id}, {"$set": update})

    # ── Push notify the uploader that OCR finished ─────────────
    # Replaces the frontend's 5-second polling loop. The panel already listens
    # on the global WebSocket — we just tag the event so it knows which review
    # to refresh.
    try:
        from routers.websocket import manager as _ws_manager
        await _ws_manager.send_to_user(user_snapshot["id"], {
            "type": "social_review_ocr_completed",
            "review_id": review_id,
            "child_id": child_id,
            "kind": kind,
            "ran": bool(payload),
            "confidence": ocr_meta["confidence"],
            "error": err,
            "dob_mismatch": bool(update.get("data_flags", {}).get("dob_mismatch")),
        })
    except Exception as e:
        logger.warning(f"WS push after OCR failed (non-fatal): {e}")

    # Auto-sync structured fields into the child profile — same as the original
    # synchronous path. Failures here don't block the OCR write itself.
    if payload:
        try:
            await _apply_review_to_child(child_id, kind, {
                "review_date": update["review_date"],
                "overall_assessment": update["overall_assessment"],
                "next_visit_date": update["next_visit_date"],
                "fields": update["fields"],
            }, user_snapshot, review_id)
            fresh = await db.social_review_forms.find_one({"id": review_id}, {"_id": 0})
            if fresh:
                await _append_timeline_note(child_id, kind, fresh, user_snapshot, review_id)
        except Exception as e:
            logger.warning(f"OCR auto-sync after background job failed: {e}")
