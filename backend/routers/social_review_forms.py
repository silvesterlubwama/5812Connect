"""Social Work Review Forms — School Progress + Welfare Home Visit.

Endpoints:
  • CRUD on filled review forms (auto-syncs structured fields into the child profile)
  • Printable blank PDF templates (WeasyPrint, loaded from /app/backend/templates/social_reviews/)
  • Upload-scan with optional Gemini-3-flash OCR auto-fill

Templates live in /app/backend/templates/social_reviews/{kind}.html so the HTML
is editable without touching Python and the router stays focused.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response
from deps import db, get_current_user, _audit, require_staff, logger
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path
import uuid
import os
import tempfile
import json

router = APIRouter(prefix="/api/social-work/reviews", tags=["social_work_reviews"])

VALID_KINDS = {"school_progress", "welfare_visit", "medical_exam"}
TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "social_reviews"


# ============================================================
# CRUD on filled review forms
# ============================================================

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


# ============================================================
# Auto-sync filled review into child profile
# ============================================================

async def _apply_review_to_child(child_id: str, kind: str, data: dict, user: dict, review_id: str):
    """Pull structured indicators out of the form payload and merge them into
    the child's profile so the existing report-pdf endpoint surfaces them
    without any extra logic on its side. Idempotent — runs on every save/update."""
    fields = data.get("fields") or {}
    set_ops = {}

    if kind == "school_progress":
        if fields.get("class_grade"):
            set_ops["education.grade"] = fields["class_grade"]
        if fields.get("school"):
            set_ops["education.school_name"] = fields["school"]
        if fields.get("term"):
            set_ops["education.current_term"] = fields["term"]
        set_ops["education.latest_review"] = {
            "review_id": review_id,
            "review_date": data.get("review_date") or "",
            "academic_performance": fields.get("academic_performance") or {},
            "attendance_discipline": fields.get("attendance_discipline") or {},
            "social_emotional": fields.get("social_emotional") or {},
            "strengths": fields.get("strengths") or "",
            "areas_requiring_support": fields.get("areas_requiring_support") or "",
            "overall": data.get("overall_assessment") or "",
        }

    elif kind == "welfare_visit":
        if fields.get("caregiver_name"):
            set_ops["family.primary_caregiver"] = fields["caregiver_name"]
        if fields.get("caregiver_relationship"):
            set_ops["family.caregiver_relationship"] = fields["caregiver_relationship"]
        if fields.get("village_parish"):
            set_ops["family.village_parish"] = fields["village_parish"]
        if fields.get("district"):
            set_ops["family.district"] = fields["district"]
        if fields.get("household") is not None:
            set_ops["family.household_assessment"] = fields["household"]
        # Guardians / siblings / income notes — surface these on the profile so the
        # Family tab reflects what's on the latest visit report.
        if fields.get("guardians"):
            set_ops["family.guardians"] = fields["guardians"] if isinstance(fields["guardians"], list) else [g.strip() for g in str(fields["guardians"]).split(",") if g.strip()]
        if fields.get("siblings") is not None:
            try:
                set_ops["family.siblings"] = int(fields["siblings"])
            except (TypeError, ValueError):
                pass
        if fields.get("household_income"):
            set_ops["family.household_income"] = fields["household_income"]
        if fields.get("family_notes"):
            set_ops["family.notes"] = fields["family_notes"]
        set_ops["welfare.latest_review"] = {
            "review_id": review_id,
            "review_date": data.get("review_date") or "",
            "indicators": fields.get("welfare_indicators") or {},
            "education_checks": fields.get("education_checks") or {},
            "health_nutrition": fields.get("health_nutrition") or {},
            "protection_concerns": fields.get("protection_concerns") or {},
            "protection_details": fields.get("protection_details") or "",
            "child_voice": fields.get("child_voice") or {},
            "strengths": fields.get("strengths") or "",
            "challenges": fields.get("challenges") or "",
            "overall": data.get("overall_assessment") or "",
            "next_visit_date": data.get("next_visit_date") or "",
        }
        prot = fields.get("protection_concerns") or {}
        flag_keys = ["neglect", "physical_abuse", "emotional_abuse", "child_labour",
                     "school_dropout_risk", "early_marriage_risk", "other_protection"]
        any_flag = any(bool(prot.get(k)) for k in flag_keys)
        set_ops["protection.has_active_concern"] = any_flag
        set_ops["protection.flags"] = {k: bool(prot.get(k)) for k in flag_keys}
        set_ops["protection.last_assessed_at"] = data.get("review_date") or datetime.now(timezone.utc).date().isoformat()

    elif kind == "medical_exam":
        # Sync medical-history flags + chronic conditions onto child.medical so the existing
        # report generator and badges-with-conditions surface them. Stamps a `medical.latest_exam`
        # snapshot for full verbatim retrieval.
        history = fields.get("medical_history") or {}
        condition_list = [k for k in (
            "asthma", "epilepsy", "diabetes", "sickle_cell", "heart_disease",
            "tuberculosis", "hiv_aids", "chronic_illness",
        ) if (history.get(k) or {}).get("present")]
        other_cond = (history.get("other") or {}).get("specify", "").strip()
        if other_cond:
            condition_list.append(other_cond)
        set_ops["medical.conditions"] = condition_list
        if fields.get("known_allergies"):
            set_ops["medical.allergies"] = fields["known_allergies"]
        if fields.get("current_medication"):
            set_ops["medical.current_medication"] = fields["current_medication"]
        if fields.get("nutritional_status"):
            set_ops["medical.nutritional_status"] = fields["nutritional_status"]
        if fields.get("general_condition"):
            set_ops["medical.general_condition"] = fields["general_condition"]
        if fields.get("immunization_status"):
            set_ops["medical.immunization_status"] = fields["immunization_status"]
        # Disability sub-flags — multi-select bools
        disability = fields.get("disability") or {}
        has_disability = bool(disability.get("has_disability"))
        set_ops["medical.has_disability"] = has_disability
        set_ops["medical.disability_flags"] = {
            k: bool(disability.get(k)) for k in (
                "physical", "visual", "hearing", "intellectual",
                "autism", "speech_language", "multiple",
            )
        }
        if disability.get("other"):
            set_ops["medical.disability_other"] = disability["other"]
        if fields.get("assistive_devices"):
            set_ops["medical.assistive_devices"] = fields["assistive_devices"]
        # Mental health screening
        if fields.get("mental_observations"):
            set_ops["medical.mental_observations"] = fields["mental_observations"]
        # Medical Diagnosis / Impression + Recommendations
        if fields.get("diagnosis"):
            set_ops["medical.diagnosis"] = fields["diagnosis"]
        recs = fields.get("recommendations") or {}
        set_ops["medical.recommendations"] = {
            k: bool(recs.get(k)) for k in (
                "fit", "fit_with_monitoring", "needs_treatment",
                "needs_referral", "needs_nutrition", "needs_disability_support",
            )
        }
        set_ops["medical.recommended_actions"] = (fields.get("recommended_actions") or "")[:1000]
        # Referral
        ref = fields.get("referral") or {}
        if ref:
            set_ops["medical.referral"] = {
                "facility": (ref.get("facility") or "")[:120],
                "reason": (ref.get("reason") or "")[:300],
                "follow_up_date": (ref.get("follow_up_date") or "")[:10],
            }
        # Practitioner certification
        pc = fields.get("practitioner") or {}
        if pc:
            set_ops["medical.practitioner"] = {
                "name": (pc.get("name") or "")[:120],
                "qualification": (pc.get("qualification") or "")[:80],
                "facility": (pc.get("facility") or "")[:120],
                "telephone": (pc.get("telephone") or "")[:32],
                "exam_date": (pc.get("exam_date") or "")[:10],
            }
        set_ops["medical.latest_exam"] = {
            "review_id": review_id,
            "exam_date": data.get("review_date") or "",
            "fields_snapshot": fields,
            "overall": data.get("overall_assessment") or "",
        }

    set_ops["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_ops["last_review_id"] = review_id
    set_ops["last_review_at"] = datetime.now(timezone.utc).isoformat()

    # ── Risk scoring ─────────────────────────────────────────────
    # Recomputed on every review so the profile always reflects the freshest
    # signals. Factors are stored verbatim in `risk.factors` so staff can see
    # exactly WHY a child was flagged rather than trusting an opaque label.
    computed_risk = None
    try:
        computed_risk = await _compute_child_risk(child_id, kind, fields, set_ops)
        if computed_risk:
            set_ops["risk.level"] = computed_risk["level"]
            set_ops["risk.factors"] = computed_risk["factors"]
            set_ops["risk.score"] = computed_risk["score"]
            set_ops["risk.updated_at"] = datetime.now(timezone.utc).isoformat()
            set_ops["risk.updated_by"] = f"ocr:{review_id}"
    except Exception as e:
        logger.warning(f"risk scoring failed for {child_id}: {e}")

    # ── Auto-goals from action plan ──────────────────────────────
    # Every action-plan row Gemini pulled becomes an in-progress goal on the
    # child so directors can see follow-through directly on the case card.
    try:
        ap = data.get("action_plan") or []
        if ap:
            existing_child = await db.children.find_one({"id": child_id}, {"_id": 0, "goals": 1}) or {}
            existing_goals = existing_child.get("goals") or []
            new_goals = []
            seen = {(g.get("goal") or "").strip().lower() for g in existing_goals if isinstance(g, dict)}
            for row in ap:
                if not isinstance(row, dict):
                    continue
                text = (row.get("action") or row.get("concern") or "").strip()
                if not text or text.lower() in seen:
                    continue
                new_goals.append({
                    "goal": text,
                    "target_date": (row.get("timeline") or "")[:10] or None,
                    "progress_pct": 0,
                    "responsible": row.get("responsible") or "",
                    "source_review_id": review_id,
                })
            if new_goals:
                set_ops["goals"] = existing_goals + new_goals
    except Exception as e:
        logger.warning(f"auto-goal creation failed for {child_id}: {e}")

    if set_ops:
        await db.children.update_one({"id": child_id}, {"$set": set_ops})

    # Propagate the computed risk onto the child's active social case so the
    # case list badge stays in sync without staff editing the case manually.
    # Never DOWNGRADES a manually-set risk level — only escalates.
    if computed_risk:
        try:
            RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            case = await db.social_cases.find_one(
                {"subject_kind": "child", "subject_id": child_id, "status": "active"},
                {"_id": 0, "id": 1, "risk_level": 1},
            )
            if case:
                current = (case.get("risk_level") or "low").lower()
                if RANK.get(computed_risk["level"], 0) > RANK.get(current, 0):
                    await db.social_cases.update_one(
                        {"id": case["id"]},
                        {"$set": {
                            "risk_level": computed_risk["level"],
                            "risk_factors": computed_risk["factors"],
                            "risk_updated_at": datetime.now(timezone.utc).isoformat(),
                            "risk_source": f"ocr:{review_id}",
                        }},
                    )
        except Exception as e:
            logger.warning(f"case risk propagation failed for {child_id}: {e}")


async def _compute_child_risk(child_id: str, latest_kind: str, latest_fields: dict, latest_set_ops: dict) -> dict:
    """Blended risk snapshot from the most recent set of reviews.

    Rules (deliberately transparent — no ML):
      • Any active protection flag  → CRITICAL
      • Chronic condition + Fair/Poor nutrition/general condition → HIGH
      • DOB mismatch OR housing Fair/Poor + nutrition Fair/Poor → MEDIUM
      • Any single Fair indicator → LOW
      • Otherwise → LOW
    """
    factors: list[str] = []
    level = "low"
    score = 0

    # Pull the child's current sub-docs so we can look at the OTHER review
    # types too (e.g. a welfare visit shouldn't lose sight of a chronic
    # medical condition captured last month).
    child = await db.children.find_one(
        {"id": child_id},
        {"_id": 0, "medical": 1, "welfare": 1, "protection": 1, "family": 1},
    ) or {}

    # Protection flags — check the freshest first, then the stored profile.
    if latest_kind == "welfare_visit":
        prot_flags = latest_set_ops.get("protection.flags") or {}
        prot_details = latest_fields.get("protection_details") or ""
    else:
        prot_flags = (child.get("protection") or {}).get("flags") or {}
        prot_details = ""
    if any(prot_flags.values()):
        level = "critical"
        score = 100
        for k, v in prot_flags.items():
            if v:
                factors.append(f"Protection: {k.replace('_', ' ')}")
        if prot_details:
            factors.append(f"Details: {prot_details[:120]}")

    # Chronic medical conditions
    if latest_kind == "medical_exam":
        conditions = latest_set_ops.get("medical.conditions") or []
        nutrition = (latest_fields.get("nutritional_status") or "").lower()
        general = (latest_fields.get("general_condition") or "").lower()
        has_disability = latest_set_ops.get("medical.has_disability")
    else:
        conditions = (child.get("medical") or {}).get("conditions") or []
        nutrition = ((child.get("medical") or {}).get("nutritional_status") or "").lower()
        general = ((child.get("medical") or {}).get("general_condition") or "").lower()
        has_disability = (child.get("medical") or {}).get("has_disability")

    if conditions:
        factors.append(f"Chronic condition(s): {', '.join(str(c) for c in conditions[:3])}")
        if level != "critical":
            level = "high" if (nutrition in {"fair", "poor"} or general in {"fair", "poor"}) else "medium"
            score = max(score, 70 if level == "high" else 50)
    if has_disability and level == "low":
        level = "medium"
        score = max(score, 45)
        factors.append("Disability noted")

    # Welfare / household indicators
    indicators = {}
    if latest_kind == "welfare_visit":
        indicators = latest_fields.get("welfare_indicators") or {}
        household = latest_fields.get("household") or {}
    else:
        w = (child.get("welfare") or {}).get("latest_review") or {}
        indicators = w.get("indicators") or {}
        household = w.get("household") or {}

    fair_count = sum(
        1 for v in indicators.values()
        if isinstance(v, dict) and str(v.get("rating", "")).lower() in {"fair", "poor"}
    )
    if fair_count >= 3 and level in {"low", "medium"}:
        level = "medium" if level == "low" else level
        score = max(score, 50)
        factors.append(f"{fair_count} welfare indicator(s) rated Fair/Poor")
    elif fair_count >= 1 and level == "low":
        score = max(score, 20)
        factors.append(f"{fair_count} welfare indicator rated Fair")

    # DOB mismatch surfaces here so staff see it in the risk breakdown, not
    # just as a toast.
    dob_mismatch = (latest_set_ops.get("data_flags") or {}).get("dob_mismatch")
    if dob_mismatch and level == "low":
        level = "medium"
        score = max(score, 40)
        factors.append("DOB on scan doesn't match record")

    if not factors:
        factors.append("No elevated risk signals detected")

    return {"level": level, "factors": factors, "score": score}


async def _append_timeline_note(child_id: str, kind: str, doc: dict, user: dict, review_id: str):
    """Append a rich, structured note to the active case's timeline so directors
    reading `/social-work/cases/{id}/notes` see the full picture without
    opening the review form. Non-fatal — any failure is logged and swallowed."""
    try:
        case = await db.social_cases.find_one(
            {"subject_kind": "child", "subject_id": child_id, "status": "active"},
            {"_id": 0, "id": 1},
        )
        if not case:
            return
        fields = doc.get("fields") or {}
        overall = doc.get("overall_assessment") or "n/a"
        header = {
            "school_progress": "🏫 School progress review",
            "welfare_visit": "🏠 Home / welfare visit",
            "medical_exam": "🩺 Medical examination",
        }.get(kind, "Review form filed")
        lines = [f"{header} — {doc.get('review_date') or ''}", f"Overall: {overall}"]

        if kind == "welfare_visit":
            cv = fields.get("child_voice") or {}
            if cv.get("going_well"): lines.append(f"Going well: {cv['going_well']}")
            if cv.get("challenges"): lines.append(f"Challenges: {cv['challenges']}")
            if cv.get("support_wanted"): lines.append(f"Support wanted: {cv['support_wanted']}")
            prot = fields.get("protection_concerns") or {}
            active_prot = [k.replace('_', ' ') for k, v in prot.items() if v]
            if active_prot:
                lines.append(f"⚠️ Protection concerns: {', '.join(active_prot)}")
            if fields.get("protection_details"):
                lines.append(f"Details: {fields['protection_details']}")
            if fields.get("strengths"):
                lines.append(f"Strengths: {fields['strengths']}")
            if fields.get("challenges"):
                lines.append(f"Challenges observed: {fields['challenges']}")
        elif kind == "school_progress":
            if fields.get("strengths"): lines.append(f"Strengths: {fields['strengths']}")
            if fields.get("areas_requiring_support"):
                lines.append(f"Areas needing support: {fields['areas_requiring_support']}")
        elif kind == "medical_exam":
            if fields.get("diagnosis"): lines.append(f"Diagnosis: {fields['diagnosis']}")
            if fields.get("recommended_actions"):
                lines.append(f"Recommendations: {fields['recommended_actions']}")
            ref = fields.get("referral") or {}
            if ref.get("facility") or ref.get("reason"):
                lines.append(f"Referral: {ref.get('facility','')} — {ref.get('reason','')}")

        ap = doc.get("action_plan") or []
        if ap:
            lines.append("Action plan:")
            for i, row in enumerate(ap[:6], 1):
                if not isinstance(row, dict): continue
                a = row.get("action") or row.get("concern") or ""
                r = row.get("responsible") or ""
                t = row.get("timeline") or ""
                lines.append(f"  {i}. {a}" + (f" — {r}" if r else "") + (f" (by {t})" if t else ""))

        await db.case_notes.insert_one({
            "id": f"note_{uuid.uuid4().hex[:8]}",
            "case_id": case["id"],
            "kind": "visit",
            "text": "\n".join(lines),
            "review_id": review_id,
            "source": "ocr_auto",
            "is_confidential": False,
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"review timeline note failed: {e}")


# ============================================================
# Blank printable templates (PDF) — HTML lives in /app/backend/templates/social_reviews/
# ============================================================

def _load_template(kind: str) -> str:
    """Read a template file. Cached only within a single process — re-reads on
    every request so admins can edit the HTML in-place without restarting."""
    path = TEMPLATES_DIR / f"{kind}.html"
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Template {kind}.html missing on server")
    return path.read_text(encoding="utf-8")


@router.get("/templates/{kind}.pdf")
async def download_blank_template(kind: str, current_user: dict = Depends(require_staff)):
    """Generate a printable blank template PDF. Branding pulled from system_settings."""
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail="kind must be school_progress or welfare_visit")
    org_name = "58:12 Global"
    try:
        settings = await db.system_settings.find_one({"id": "settings"}, {"_id": 0, "branding": 1, "org": 1})
        if settings:
            b = settings.get("branding") or {}
            o = settings.get("org") or {}
            org_name = b.get("app_name") or o.get("name") or org_name
    except Exception:
        pass
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    html = _load_template(kind).replace("{{ORG_NAME}}", org_name).replace("{{TODAY}}", today)
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        filename = "school-progress-review-blank.pdf" if kind == "school_progress" else "welfare-visit-blank.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.warning(f"PDF generation failed, returning HTML: {e}")
        return Response(content=html.encode(), media_type="text/html")


# ============================================================
# Upload a scanned filled paper form — with optional Gemini OCR auto-fill
# ============================================================

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
    """Upload a scanned-and-filled paper form.

    v2 flow: saves the scan + creates a draft review IMMEDIATELY (< 1 s), then
    kicks off Gemini OCR as a background task. The HTTP response comes back
    fast so we never hit the ingress proxy timeout — even for handwriting-
    heavy pages that take 30-40 s to OCR.

    Frontend behaviour:
      • Response arrives with `ocr.pending: true` — show "OCR running…" toast
      • Poll `GET /:review_id` every 5 s (or refresh the list) — OCR meta
        flips to `ran: true` + `confidence: high|medium|low` when done
      • If `ocr.error` set, user can transcribe manually via the row's dialog
    """
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
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "pdf"
    unique = f"{child_id}-{kind}-{uuid.uuid4().hex[:8]}.{ext}"
    file_url = None
    try:
        from storage import put_object
        result = put_object(f"social-review-scans/{unique}", data, file.content_type)
        file_url = result.get("url", f"/api/storage/social-review-scans/{unique}")
    except Exception as e:
        logger.warning(f"Cloud storage put failed, saving locally: {e}")
        os.makedirs("/app/backend/uploads/social-review-scans", exist_ok=True)
        with open(f"/app/backend/uploads/social-review-scans/{unique}", "wb") as fh:
            fh.write(data)
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
    try:
        await db.child_extras.insert_one({
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
        })
    except Exception as e:
        logger.warning(f"child_extras mirror failed: {e}")

    await _audit(current_user["id"], "create", "social_review_scan", review_id,
                 {"kind": kind, "child_id": child_id, "ocr_will_run": will_ocr})
    return rev


# ============================================================
# Visit photos — attached to a specific review form
# ============================================================

@router.post("/{review_id}/photos")
async def upload_review_photo(
    review_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    current_user: dict = Depends(require_staff),
):
    """Attach a photo taken during this visit to the review.

    Photos appear as a gallery on the review row in the social-work UI and
    are also mirrored into `db.child_extras` (kind='gallery') so they show
    up in the existing child-extras gallery and on sponsor updates when
    `is_public_for_sponsor` is enabled.
    """
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
        from storage import put_object
        result = put_object(f"review-photos/{unique}", data, file.content_type)
        file_url = result.get("url", f"/api/storage/review-photos/{unique}")
    except Exception as e:
        logger.warning(f"Cloud storage put failed, saving locally: {e}")
        os.makedirs("/app/backend/uploads/review-photos", exist_ok=True)
        with open(f"/app/backend/uploads/review-photos/{unique}", "wb") as fh:
            fh.write(data)
        file_url = f"/api/uploads/review-photos/{unique}"

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


# ============================================================
# Bonus — Review compliance widget (children due for a welfare visit)
# ============================================================

@router.get("/compliance/due")
async def reviews_due(
    days: int = 90,
    location_id: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Children whose last welfare visit is older than `days` days (or who have
    never had one). Used by the social-work dashboard to nudge field staff
    toward overdue cases.

    Returns: { total_active, due, never_visited, list: [{child_id, name,
    last_review_at, days_since}, …] }. List is capped at 200 for UI rendering.
    """
    from deps import is_system_admin, has_module_access, get_campus_filter
    # Restrict to active social-work cases on children
    case_query = {"subject_kind": "child", "status": "active"}
    if not is_system_admin(current_user) and not has_module_access(current_user, "social_work"):
        scope = await get_campus_filter(current_user)
        if scope:
            case_query.update(scope)
    if location_id and location_id != "all":
        case_query["location_id"] = location_id
    cases = await db.social_cases.find(case_query, {"_id": 0, "subject_id": 1, "subject_name": 1, "location_id": 1}).to_list(2000)
    if not cases:
        return {"total_active": 0, "due": 0, "never_visited": 0, "list": []}
    child_ids = [c["subject_id"] for c in cases if c.get("subject_id")]

    # Latest welfare review per child (single aggregation)
    pipeline = [
        {"$match": {"child_id": {"$in": child_ids}, "kind": "welfare_visit"}},
        {"$sort": {"review_date": -1}},
        {"$group": {"_id": "$child_id", "last_review_at": {"$first": "$review_date"}}},
    ]
    last_map = {}
    async for row in db.social_review_forms.aggregate(pipeline):
        last_map[row["_id"]] = row["last_review_at"]

    today = datetime.now(timezone.utc).date()
    due_list = []
    never_count = 0
    for c in cases:
        cid = c.get("subject_id")
        last = last_map.get(cid)
        if not last:
            never_count += 1
            due_list.append({"child_id": cid, "name": c.get("subject_name", ""),
                             "last_review_at": None, "days_since": None,
                             "location_id": c.get("location_id")})
            continue
        try:
            last_date = datetime.fromisoformat(last[:10]).date()
            delta = (today - last_date).days
            if delta > days:
                due_list.append({"child_id": cid, "name": c.get("subject_name", ""),
                                 "last_review_at": last, "days_since": delta,
                                 "location_id": c.get("location_id")})
        except Exception:
            continue
    due_list.sort(key=lambda x: (x["days_since"] is None, -(x["days_since"] or 0)))
    return {
        "total_active": len(cases),
        "due": len(due_list),
        "never_visited": never_count,
        "threshold_days": days,
        "list": due_list[:200],
    }


# ============================================================
# Profile completeness — % of file-checklist + reviews present per child
# ============================================================

# Same canonical doc_types as `routers/members/children.py`. Duplicated here so this
# module stays import-light (avoids a circular routers.members.children import).
_FILE_DOC_TYPE_KEYS = [
    "ovcmis_form_008", "sponsorship_assessment", "lc1_introduction_letter",
    "school_report", "guardian_national_id", "family_consent_letter",
    "medical_assessment", "exit_form", "sponsor_letter_in", "sponsor_letter_out",
]


@router.get("/compliance/completeness")
async def child_file_completeness(
    location_id: Optional[str] = None,
    threshold_pct: int = 70,
    group_by: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Per-child profile-completeness scorecard.

    For each child with an active social-work case, computes:
      • has_photo        — child.photo_url set
      • has_welfare      — at least one welfare_visit review
      • has_school       — at least one school_progress review
      • has_medical      — at least one medical_exam review OR a medical_assessment file_doc
      • per-doctype flags for the 10 checklist items
      • completeness_pct — 0–100 (weighted equally across 14 indicators)

    Returns the aggregate counts + a list of children sorted by ascending
    completeness so the audit-focused user sees the most-incomplete files first.

    Pass `group_by=location_id` to ALSO get a `by_campus` rollup: { location_id,
    location_name, total_active, above_threshold, below_threshold, avg_pct }.
    Used by the per-campus leaderboard widget to surface which campus is
    keeping the cleanest records.
    """
    from deps import is_system_admin, has_module_access, get_campus_filter
    case_query = {"subject_kind": "child", "status": "active"}
    if not is_system_admin(current_user) and not has_module_access(current_user, "social_work"):
        scope = await get_campus_filter(current_user)
        if scope:
            case_query.update(scope)
    if location_id and location_id != "all":
        case_query["location_id"] = location_id
    cases = await db.social_cases.find(case_query, {"_id": 0, "subject_id": 1, "subject_name": 1, "location_id": 1}).to_list(2000)
    if not cases:
        return {"total_active": 0, "above_threshold": 0, "below_threshold": 0, "threshold_pct": threshold_pct, "list": []}
    child_ids = [c["subject_id"] for c in cases if c.get("subject_id")]

    # Bulk-load: child photos + reviews + file_docs in one round-trip per source.
    photo_map = {}
    async for ch in db.children.find({"id": {"$in": child_ids}}, {"_id": 0, "id": 1, "photo_url": 1}):
        photo_map[ch["id"]] = bool(ch.get("photo_url"))

    review_kinds_map = {}  # child_id → set of kinds
    async for r in db.social_review_forms.find(
        {"child_id": {"$in": child_ids}}, {"_id": 0, "child_id": 1, "kind": 1}
    ):
        review_kinds_map.setdefault(r["child_id"], set()).add(r.get("kind"))

    doc_types_map = {}  # child_id → set of doc_types present
    async for d in db.child_extras.find(
        {"child_id": {"$in": child_ids}, "kind": "file_doc"},
        {"_id": 0, "child_id": 1, "doc_type": 1},
    ):
        doc_types_map.setdefault(d["child_id"], set()).add(d.get("doc_type"))

    out_list = []
    above = 0
    # 14 indicators: 4 high-level (photo, welfare, school, medical) + 10 file-doc types
    TOTAL_INDICATORS = 4 + len(_FILE_DOC_TYPE_KEYS)
    for c in cases:
        cid = c.get("subject_id")
        kinds = review_kinds_map.get(cid, set())
        docs = doc_types_map.get(cid, set())
        # has_medical is met EITHER by a medical_exam review OR by an uploaded medical_assessment scan
        has_medical = "medical_exam" in kinds or "medical_assessment" in docs
        indicators = {
            "has_photo": photo_map.get(cid, False),
            "has_welfare": "welfare_visit" in kinds,
            "has_school": "school_progress" in kinds,
            "has_medical": has_medical,
            **{f"doc_{k}": (k in docs) for k in _FILE_DOC_TYPE_KEYS},
        }
        present = sum(1 for v in indicators.values() if v)
        pct = round((present / TOTAL_INDICATORS) * 100)
        if pct >= threshold_pct:
            above += 1
        out_list.append({
            "child_id": cid,
            "name": c.get("subject_name", ""),
            "location_id": c.get("location_id"),
            "completeness_pct": pct,
            "present": present,
            "total_indicators": TOTAL_INDICATORS,
            "indicators": indicators,
        })
    out_list.sort(key=lambda x: (x["completeness_pct"], (x["name"] or "").lower()))

    # Optional per-campus rollup — drives the leaderboard widget. Computed in
    # process from out_list so we don't re-query; location names resolved in a
    # single round-trip.
    by_campus = None
    if group_by == "location_id":
        groups = {}
        for row in out_list:
            loc = row.get("location_id") or "_unassigned"
            g = groups.setdefault(loc, {"location_id": loc, "total_active": 0, "above_threshold": 0, "below_threshold": 0, "sum_pct": 0})
            g["total_active"] += 1
            g["sum_pct"] += row["completeness_pct"]
            if row["completeness_pct"] >= threshold_pct:
                g["above_threshold"] += 1
            else:
                g["below_threshold"] += 1
        real_ids = [g for g in groups.keys() if g != "_unassigned"]
        name_map = {}
        if real_ids:
            async for loc in db.locations.find({"id": {"$in": real_ids}}, {"_id": 0, "id": 1, "name": 1}):
                name_map[loc["id"]] = loc.get("name") or loc["id"]
        by_campus = []
        for g in groups.values():
            g["location_name"] = name_map.get(g["location_id"], "Unassigned" if g["location_id"] == "_unassigned" else g["location_id"])
            g["avg_pct"] = round(g["sum_pct"] / g["total_active"]) if g["total_active"] else 0
            del g["sum_pct"]
            by_campus.append(g)
        # Top campus first — sort by avg, then by raw above-threshold count to
        # break ties in favour of larger campuses doing well.
        by_campus.sort(key=lambda g: (-g["avg_pct"], -g["above_threshold"]))

    response = {
        "total_active": len(cases),
        "above_threshold": above,
        "below_threshold": len(cases) - above,
        "threshold_pct": threshold_pct,
        "list": out_list[:500],
    }
    if by_campus is not None:
        response["by_campus"] = by_campus
    return response


# Late import to avoid circular dep with deps.py inside the module top-level.
from datetime import timedelta  # noqa: E402
