"""Case-note timeline append helper.

Every review save/OCR-complete pushes a rich, human-readable note into the
child's active case timeline so directors reading `/social-work/cases/{id}/notes`
see the full picture without opening the review form. Non-fatal — any failure
is logged and swallowed so a broken note never blocks the review itself.
"""
import uuid
from datetime import datetime, timezone

from deps import db, logger


async def _append_timeline_note(child_id: str, kind: str, doc: dict, user: dict, review_id: str):
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
            # Iteration 226 audit: render the "Child voice" heading and
            # every key the OCR pulls (not just the fixed 3) so bespoke
            # fields don't disappear from the timeline note.
            cv_pairs = [(k, v) for k, v in cv.items() if v and isinstance(v, (str, int, float))]
            if cv_pairs:
                lines.append("Child's voice:")
                pretty = {
                    "going_well": "Going well",
                    "challenges": "Challenges",
                    "support_wanted": "Support wanted",
                }
                for k, v in cv_pairs:
                    label = pretty.get(k, k.replace('_', ' ').capitalize())
                    lines.append(f"  {label}: {v}")
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
            if fields.get("strengths"):
                lines.append(f"Strengths: {fields['strengths']}")
            if fields.get("areas_requiring_support"):
                lines.append(f"Areas needing support: {fields['areas_requiring_support']}")
        elif kind == "medical_exam":
            if fields.get("diagnosis"):
                lines.append(f"Diagnosis: {fields['diagnosis']}")
            if fields.get("recommended_actions"):
                lines.append(f"Recommendations: {fields['recommended_actions']}")
            ref = fields.get("referral") or {}
            if ref.get("facility") or ref.get("reason"):
                lines.append(f"Referral: {ref.get('facility','')} — {ref.get('reason','')}")

        ap = doc.get("action_plan") or []
        if ap:
            lines.append("Action plan:")
            for i, row in enumerate(ap[:6], 1):
                if not isinstance(row, dict):
                    continue
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
