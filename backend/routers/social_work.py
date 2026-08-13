"""Social Work & Welfare module.

Tracks sponsored children, residents of restricted spaces, and members receiving
welfare support. Wires school-tuition / resource / medical payments into the
financial + accounting ledgers automatically (mirrors the donations/expenses
pattern). Exposes a campus-aware staff API and a separate password-gated school
portal so external teachers can upload report cards & notes.

Auth model
  • Staff-facing endpoints: require_staff and above; sensitive writes
    (issuing portal passwords, discharging a case) require Manager+.
  • School portal endpoints: public auth via a per-school portal-token URL +
    one-time password; returns a short-lived JWT-style portal token used for
    subsequent reads/writes from the external teacher.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from deps import (
    db, get_current_user, require_staff, require_manager, require_director,
    _audit, logger, get_campus_filter, is_system_admin, hash_password, verify_password,
    require_social_work_view,
)
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import uuid
import secrets
import hashlib

router = APIRouter(prefix="/api/social-work", tags=["social-work"], dependencies=[Depends(require_social_work_view)])
portal_router = APIRouter(prefix="/api/school-portal", tags=["school-portal"])

CASE_CATEGORIES = {"sponsored", "restricted_location", "welfare_support", "multiple"}
CASE_STATUSES = {"active", "on_hold", "discharged"}
NOTE_KINDS = {"visit", "counseling", "safeguarding", "milestone", "school", "medical", "other"}
PAYMENT_KINDS = {"tuition", "resource", "medical", "child_support"}
RISK_LEVELS = {"low", "medium", "high", "critical"}


# ============================================================
# COUNTRY COMPLIANCE FIELDS
# ============================================================
# Each country gets its own additional record-collection requirements,
# grouped for the UI (identity / official / family / school / health).
# `type` ∈ text | textarea | select | yesno | date | number.
# Field IDs are stable — DO NOT rename without a migration.
COUNTRY_COMPLIANCE_FIELDS = {
    # Uganda Ministry of Gender, Labour & Social Development (MGLSD) OVC record set
    "UG": {
        "name": "Uganda — MGLSD OVC record",
        "fields": [
            # Identity & registration
            {"id": "birth_cert_no", "label": "Birth certificate number", "type": "text", "group": "identity"},
            {"id": "birth_registered", "label": "Birth registered with NIRA?", "type": "yesno", "group": "identity"},
            {"id": "national_id_no", "label": "National ID (NIN)", "type": "text", "group": "identity"},
            {"id": "tribe", "label": "Tribe / Ethnicity", "type": "text", "group": "identity"},
            {"id": "religion", "label": "Religion", "type": "select", "group": "identity",
             "options": ["Christian — Catholic", "Christian — Protestant", "Christian — Pentecostal", "Muslim", "Traditional", "None", "Other"]},
            # Administrative location (LC structure)
            {"id": "village", "label": "Village / LC1", "type": "text", "group": "official"},
            {"id": "parish", "label": "Parish / LC2", "type": "text", "group": "official"},
            {"id": "sub_county", "label": "Sub-county / LC3", "type": "text", "group": "official"},
            {"id": "district", "label": "District / LC5", "type": "text", "group": "official"},
            {"id": "lc1_letter_on_file", "label": "LC1 introduction letter on file?", "type": "yesno", "group": "official"},
            {"id": "dpo_case_number", "label": "DPO (District Probation Officer) case number", "type": "text", "group": "official"},
            {"id": "dpo_status", "label": "DPO referral status", "type": "select", "group": "official",
             "options": ["Not referred", "Referred — pending", "Registered", "Case closed"]},
            # Vulnerability
            {"id": "vulnerability_status", "label": "Vulnerability status", "type": "select", "group": "family",
             "options": ["Single orphan (mother)", "Single orphan (father)", "Double orphan", "Abandoned",
                         "Child-headed household", "Child with disability", "Living with HIV", "Living with chronic illness",
                         "Refugee", "Street-connected", "Other vulnerable"]},
            {"id": "vulnerability_score", "label": "Vulnerability score (0–100)", "type": "number", "group": "family"},
            {"id": "living_arrangement", "label": "Living arrangement", "type": "select", "group": "family",
             "options": ["With both biological parents", "With single parent", "With grandparent(s)",
                         "With other relatives", "Foster family", "Institutional / shelter", "Independent"]},
            # School practicalities (very Uganda-specific)
            {"id": "school_distance_km", "label": "Distance to school (km)", "type": "number", "group": "school"},
            {"id": "school_transport", "label": "Means of getting to school", "type": "select", "group": "school",
             "options": ["Walk", "Bicycle", "Boda-boda", "Parent transport", "School bus", "Public transport"]},
            {"id": "school_meal_received", "label": "Receives school meal?", "type": "yesno", "group": "school"},
            {"id": "has_uniform", "label": "Has full school uniform?", "type": "yesno", "group": "school"},
            {"id": "has_scholastic_materials", "label": "Has scholastic materials (books, pens)?", "type": "yesno", "group": "school"},
            # Health
            {"id": "immunisation_complete", "label": "Immunisation up-to-date?", "type": "yesno", "group": "health"},
            {"id": "has_mosquito_net", "label": "Has a mosquito net at home?", "type": "yesno", "group": "health"},
            {"id": "last_health_screening", "label": "Last health screening date", "type": "date", "group": "health"},
            {"id": "nhif_registered", "label": "Health insurance registered?", "type": "yesno", "group": "health"},
            {"id": "nutrition_status", "label": "Nutrition status", "type": "select", "group": "health",
             "options": ["Good", "Moderate concern", "Severe — MUAC red", "Under treatment"]},
            # Free-form
            {"id": "additional_notes", "label": "Additional compliance notes", "type": "textarea", "group": "family"},
        ],
    },
    # Kenya — adapted from Kenyan Children's Department / Department of Children Services
    "KE": {
        "name": "Kenya — Children's Department record",
        "fields": [
            {"id": "birth_notification_no", "label": "Birth notification number", "type": "text", "group": "identity"},
            {"id": "national_id_no", "label": "Huduma / National ID (if applicable)", "type": "text", "group": "identity"},
            {"id": "tribe", "label": "Tribe / Ethnicity", "type": "text", "group": "identity"},
            {"id": "religion", "label": "Religion", "type": "text", "group": "identity"},
            {"id": "ward", "label": "Ward", "type": "text", "group": "official"},
            {"id": "sub_county", "label": "Sub-county", "type": "text", "group": "official"},
            {"id": "county", "label": "County", "type": "text", "group": "official"},
            {"id": "co_referral_number", "label": "Children's Officer case number", "type": "text", "group": "official"},
            {"id": "vulnerability_status", "label": "Vulnerability status", "type": "select", "group": "family",
             "options": ["OVC", "Disabled", "Living with HIV", "Refugee", "Street-connected", "Abused", "Other"]},
            {"id": "living_arrangement", "label": "Living arrangement", "type": "select", "group": "family",
             "options": ["With parents", "With relatives", "Foster", "Institutional", "Independent"]},
            {"id": "nhif_member", "label": "NHIF member?", "type": "yesno", "group": "health"},
            {"id": "immunisation_complete", "label": "Immunisation up-to-date?", "type": "yesno", "group": "health"},
            {"id": "additional_notes", "label": "Additional compliance notes", "type": "textarea", "group": "family"},
        ],
    },
    # Haiti — IBESR (Institut du Bien-Être Social et de Recherches)
    "HT": {
        "name": "Haïti — IBESR record",
        "fields": [
            {"id": "acte_naissance_no", "label": "Acte de naissance (numéro)", "type": "text", "group": "identity"},
            {"id": "section_communale", "label": "Section communale", "type": "text", "group": "official"},
            {"id": "commune", "label": "Commune", "type": "text", "group": "official"},
            {"id": "departement", "label": "Département", "type": "text", "group": "official"},
            {"id": "ibesr_dossier_no", "label": "IBESR dossier number", "type": "text", "group": "official"},
            {"id": "vulnerability_status", "label": "Statut de vulnérabilité", "type": "select", "group": "family",
             "options": ["Orphelin de mère", "Orphelin de père", "Orphelin total", "Enfant restavèk",
                         "Enfant des rues", "En situation de handicap", "Autre"]},
            {"id": "living_arrangement", "label": "Arrangement de vie", "type": "select", "group": "family",
             "options": ["Parents biologiques", "Famille élargie", "Famille d'accueil", "Institution", "Indépendant"]},
            {"id": "school_meal_received", "label": "Reçoit un repas à l'école?", "type": "yesno", "group": "school"},
            {"id": "immunisation_complete", "label": "Vaccinations à jour?", "type": "yesno", "group": "health"},
            {"id": "additional_notes", "label": "Notes additionnelles", "type": "textarea", "group": "family"},
        ],
    },
    # Thailand — basic compliance for sponsored children
    "TH": {
        "name": "Thailand — basic welfare record",
        "fields": [
            {"id": "thai_id_no", "label": "Thai national ID (13-digit)", "type": "text", "group": "identity"},
            {"id": "ethnicity", "label": "Ethnicity / Hill tribe", "type": "text", "group": "identity"},
            {"id": "religion", "label": "Religion", "type": "text", "group": "identity"},
            {"id": "tambon", "label": "Tambon (sub-district)", "type": "text", "group": "official"},
            {"id": "amphoe", "label": "Amphoe (district)", "type": "text", "group": "official"},
            {"id": "province", "label": "Province", "type": "text", "group": "official"},
            {"id": "vulnerability_status", "label": "Vulnerability status", "type": "select", "group": "family",
             "options": ["Orphan", "Stateless", "Migrant family", "Disabled", "Trafficking risk", "Other"]},
            {"id": "living_arrangement", "label": "Living arrangement", "type": "select", "group": "family",
             "options": ["With parents", "With relatives", "Foster", "Boarding school", "Children's home"]},
            {"id": "uc_card_no", "label": "Universal Coverage health card no.", "type": "text", "group": "health"},
            {"id": "additional_notes", "label": "Additional notes", "type": "textarea", "group": "family"},
        ],
    },
    # USA — minimal (HIPAA-cautious — no SSN stored here)
    "US": {
        "name": "United States — basic welfare record",
        "fields": [
            {"id": "state", "label": "State", "type": "text", "group": "official"},
            {"id": "county", "label": "County", "type": "text", "group": "official"},
            {"id": "school_district", "label": "School district", "type": "text", "group": "school"},
            {"id": "iep_504_plan", "label": "IEP / 504 plan in place?", "type": "yesno", "group": "school"},
            {"id": "free_reduced_lunch", "label": "Free/reduced lunch program", "type": "yesno", "group": "school"},
            {"id": "vulnerability_status", "label": "Vulnerability status", "type": "select", "group": "family",
             "options": ["Foster care", "Unhoused", "Refugee/asylum", "Disability", "Single-parent", "Other"]},
            {"id": "additional_notes", "label": "Additional compliance notes", "type": "textarea", "group": "family"},
        ],
    },
    # Generic fallback for any country not yet templated
    "GENERIC": {
        "name": "Generic welfare record",
        "fields": [
            {"id": "national_id_no", "label": "National / Government ID", "type": "text", "group": "identity"},
            {"id": "ethnicity", "label": "Ethnicity", "type": "text", "group": "identity"},
            {"id": "religion", "label": "Religion", "type": "text", "group": "identity"},
            {"id": "village", "label": "Village / Neighbourhood", "type": "text", "group": "official"},
            {"id": "district", "label": "District / Region", "type": "text", "group": "official"},
            {"id": "vulnerability_status", "label": "Vulnerability status", "type": "select", "group": "family",
             "options": ["Orphan", "Single-parent household", "Disabled", "Refugee", "Other vulnerable"]},
            {"id": "living_arrangement", "label": "Living arrangement", "type": "select", "group": "family",
             "options": ["With parents", "With relatives", "Foster", "Institutional"]},
            {"id": "additional_notes", "label": "Additional notes", "type": "textarea", "group": "family"},
        ],
    },
}


def _country_to_code(country: str) -> str:
    if not country:
        return "GENERIC"
    s = country.strip().lower()
    if s in {"ug", "uga", "uganda"}: return "UG"
    if s in {"ke", "ken", "kenya"}: return "KE"
    if s in {"ht", "hti", "haiti", "haïti"}: return "HT"
    if s in {"th", "tha", "thailand"}: return "TH"
    if s in {"us", "usa", "united states", "united states of america"}: return "US"
    # Already a code?
    if country.upper() in COUNTRY_COMPLIANCE_FIELDS:
        return country.upper()
    return "GENERIC"


async def _resolve_country_for_case(case: dict) -> str:
    """Return ISO-ish country code from the case's location."""
    loc_id = case.get("location_id")
    if not loc_id:
        return "GENERIC"
    loc = await db.locations.find_one({"id": loc_id}, {"_id": 0, "country": 1, "parent_id": 1})
    if loc and loc.get("country"):
        return _country_to_code(loc["country"])
    # Walk parent chain (sub-locations may not have country set)
    parent_id = (loc or {}).get("parent_id")
    while parent_id:
        parent = await db.locations.find_one({"id": parent_id}, {"_id": 0, "country": 1, "parent_id": 1})
        if not parent:
            break
        if parent.get("country"):
            return _country_to_code(parent["country"])
        parent_id = parent.get("parent_id")
    return "GENERIC"


def _can_manage_social_work(user: dict) -> bool:
    """Manager+ OR explicit social_work role/department."""
    role = user.get("role", "")
    dept = (user.get("department") or "").lower()
    if is_system_admin(user) or role in {"admin", "Executive Director", "Adviser", "Director", "Manager"}:
        return True
    if role.lower() in {"social_work", "social worker", "welfare"}:
        return True
    if "social" in dept or "welfare" in dept:
        return True
    return False


async def _can_issue_portal_password(user: dict) -> bool:
    """Only social-work staff/manager/director can hand out school-portal passwords."""
    return _can_manage_social_work(user)


# ============================================================
# CASES
# ============================================================

@router.get("/cases")
async def list_cases(
    category: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    school_id: Optional[str] = None,
    search: Optional[str] = None,
    ocr_confidence: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """Search cases. Scoped to user's campus.

    `ocr_confidence` filters cases by the LATEST review's OCR confidence:
      • 'low'   → cases whose latest review was auto-extracted with low confidence
                  (these need a social worker to review & correct)
      • 'any'   → no filter
    """
    query = {}
    if category and category in CASE_CATEGORIES:
        query["category"] = category
    if status and status in CASE_STATUSES:
        query["status"] = status
    if risk_level and risk_level in RISK_LEVELS:
        query["risk_level"] = risk_level
    if school_id:
        query["education.school_id"] = school_id
    if search:
        s = search.strip()
        query["$or"] = [
            {"subject_name": {"$regex": s, "$options": "i"}},
            {"summary": {"$regex": s, "$options": "i"}},
        ]
    scope = await get_campus_filter(current_user)
    if scope:
        query.update(scope)
    cases = await db.social_cases.find(query, {"_id": 0}).sort("opened_at", -1).to_list(500)

    # Enrich with child protection flags so the list view can render a red dot
    # for any child with an active protection concern (set by welfare-visit reviews).
    # Also pull the latest-review OCR confidence so the UI can surface
    # "needs review" cases and so we can apply the ocr_confidence filter.
    child_ids = [c["subject_id"] for c in cases if c.get("subject_kind") == "child" and c.get("subject_id")]
    if child_ids:
        # Protection flags (batched)
        prot_map = {}
        async for ch in db.children.find(
            {"id": {"$in": child_ids}, "protection.has_active_concern": True},
            {"_id": 0, "id": 1, "protection": 1},
        ):
            prot_map[ch["id"]] = ch.get("protection") or {}
        # Latest-review OCR meta — one aggregation per child × kind so the
        # caller can see if the most recent review for either kind was
        # auto-extracted at low confidence.
        ocr_map = {}
        pipeline = [
            {"$match": {"child_id": {"$in": child_ids}, "ocr.ran": True}},
            {"$sort": {"review_date": -1}},
            {"$group": {
                "_id": {"child_id": "$child_id", "kind": "$kind"},
                "latest_confidence": {"$first": "$ocr.confidence"},
                "latest_review_id": {"$first": "$id"},
                "latest_review_date": {"$first": "$review_date"},
            }},
        ]
        async for row in db.social_review_forms.aggregate(pipeline):
            cid = row["_id"]["child_id"]
            ocr_map.setdefault(cid, {})[row["_id"]["kind"]] = {
                "confidence": row["latest_confidence"],
                "review_id": row["latest_review_id"],
                "review_date": row["latest_review_date"],
            }
        for c in cases:
            sid = c.get("subject_id")
            if sid in prot_map:
                c["protection"] = prot_map[sid]
            if sid in ocr_map:
                c["latest_ocr"] = ocr_map[sid]
                # Convenience boolean — true if ANY of the review kinds is low-confidence
                c["has_low_confidence_ocr"] = any(v.get("confidence") == "low" for v in ocr_map[sid].values())

    if ocr_confidence == "low":
        cases = [c for c in cases if c.get("has_low_confidence_ocr")]
    elif ocr_confidence in {"high", "medium"}:
        cases = [c for c in cases if any(
            v.get("confidence") == ocr_confidence for v in (c.get("latest_ocr") or {}).values()
        )]

    return cases


@router.post("/cases")
async def create_case(data: dict, current_user: dict = Depends(require_staff)):
    """Create a social-work case linked to a child OR member.
    Body: { subject_id, subject_kind ('child'|'member'), category, summary?, education?,
            medical?, family?, goals?, risk_level?, sponsor_member_id?, location_id? }"""
    subject_id = (data.get("subject_id") or "").strip()
    subject_kind = (data.get("subject_kind") or "child").strip().lower()
    category = (data.get("category") or "welfare_support").strip()
    if subject_kind not in {"child", "member"}:
        raise HTTPException(status_code=400, detail="subject_kind must be 'child' or 'member'")
    if category not in CASE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CASE_CATEGORIES)}")
    if not subject_id:
        raise HTTPException(status_code=400, detail="subject_id required")
    # Resolve subject snapshot
    if subject_kind == "child":
        subject = await db.children.find_one({"id": subject_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "photo_url": 1, "date_of_birth": 1})
    else:
        subject = await db.members.find_one({"id": subject_id}, {"_id": 0, "id": 1, "name": 1, "location_id": 1, "photo_url": 1, "date_of_birth": 1})
    if not subject:
        raise HTTPException(status_code=404, detail=f"{subject_kind} {subject_id} not found")
    # De-dup: don't open two active cases for the same subject
    existing = await db.social_cases.find_one({"subject_id": subject_id, "subject_kind": subject_kind, "status": "active"})
    if existing:
        raise HTTPException(status_code=400, detail="An active case already exists for this subject — re-open or edit it instead")
    case_id = f"sc_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": case_id,
        "subject_id": subject_id,
        "subject_kind": subject_kind,
        "subject_name": subject.get("name", ""),
        "subject_photo_url": subject.get("photo_url"),
        "subject_dob": subject.get("date_of_birth"),
        "category": category,
        "status": "active",
        "summary": (data.get("summary") or "")[:1000],
        "education": data.get("education") or {
            # { grade, school_id, school_name, enrollment_date, extracurricular: [str] }
        },
        "medical": data.get("medical") or {
            # { conditions: [], allergies: [], receives_medical_support: bool, primary_doctor, notes }
        },
        "family": data.get("family") or {
            # { guardians: [str], siblings: int, household_income, notes }
        },
        "goals": data.get("goals") or [],  # [{ goal, target_date, progress_pct, notes }]
        "risk_level": (data.get("risk_level") if data.get("risk_level") in RISK_LEVELS else "low"),
        "sponsor_member_id": data.get("sponsor_member_id"),
        "sponsor_manual": None,    # set below if data includes it (with full validation + guest upsert)
        "sponsor_guest_id": None,
        "location_id": data.get("location_id") or subject.get("location_id") or current_user.get("active_campus_id"),
        "opened_at": now,
        "opened_by": current_user["id"],
        "opened_by_name": current_user.get("name", ""),
        "updated_at": now,
    }
    # Same validation+guest-upsert path used by PUT so create + edit behave identically.
    sm_in = data.get("sponsor_manual")
    if sm_in is not None:
        if not isinstance(sm_in, dict):
            raise HTTPException(status_code=400, detail="sponsor_manual must be an object or null")
        name = (sm_in.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="sponsor_manual.name is required when sponsor_manual is set")
        doc["sponsor_manual"] = {
            "name": name[:120],
            "email": (sm_in.get("email") or "").strip().lower()[:120],
            "phone": (sm_in.get("phone") or "").strip()[:32],
            "notes": (sm_in.get("notes") or "").strip()[:500],
        }
        gid = await _upsert_external_sponsor_guest(doc["sponsor_manual"], current_user)
        if gid:
            doc["sponsor_guest_id"] = gid
    await db.social_cases.insert_one(doc)
    doc.pop("_id", None)
    await _audit(current_user["id"], "create", "social_case", case_id, {"subject": subject.get("name"), "category": category})
    return doc


@router.get("/cases/{case_id}")
async def get_case(case_id: str, current_user: dict = Depends(require_staff)):
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # Attach computed aggregates
    case["payments_total"] = await _case_payments_summary(case_id)
    case["notes_count"] = await db.social_case_notes.count_documents({"case_id": case_id})
    # Attach the country-compliance schema the UI should render
    case["compliance_country_code"] = await _resolve_country_for_case(case)
    return case


# ============================================================
# COUNTRY COMPLIANCE SCHEMA + PROFILE REPORT PDF
# ============================================================

@router.get("/compliance/{country}")
async def get_compliance_schema(country: str, current_user: dict = Depends(require_staff)):
    """Return the field schema for a country code or human name (e.g. 'Uganda').
    The UI uses this to dynamically render the Compliance tab."""
    code = _country_to_code(country)
    schema = COUNTRY_COMPLIANCE_FIELDS.get(code) or COUNTRY_COMPLIANCE_FIELDS["GENERIC"]
    return {"country_code": code, **schema}


@router.get("/compliance")
async def list_compliance_countries(current_user: dict = Depends(require_staff)):
    """List all available country compliance templates (for picker UIs / admin)."""
    return [
        {"country_code": code, "name": schema["name"], "field_count": len(schema["fields"])}
        for code, schema in COUNTRY_COMPLIANCE_FIELDS.items()
    ]


@router.get("/cases/{case_id}/report")
async def generate_case_report(case_id: str, current_user: dict = Depends(require_staff)):
    """Generate a branded, presentation-ready Beneficiary Profile Report PDF.
    Includes identity, education, medical, family, compliance (country-specific),
    goals, payments YTD, and recent case notes. Suitable for school / official handoff."""
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    notes = await db.social_case_notes.find(
        {"case_id": case_id, "is_confidential": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    payments = await db.social_child_payments.find({"case_id": case_id}, {"_id": 0}).sort("date", -1).to_list(500)
    school = None
    if (case.get("education") or {}).get("school_id"):
        school = await db.social_schools.find_one(
            {"id": case["education"]["school_id"]}, {"_id": 0, "name": 1, "address": 1, "head_teacher": 1, "phone": 1}
        )
    country_code = await _resolve_country_for_case(case)
    compliance_schema = COUNTRY_COMPLIANCE_FIELDS.get(country_code, COUNTRY_COMPLIANCE_FIELDS["GENERIC"])
    compliance_values = case.get("compliance") or {}

    # Resolve sponsor for the report's Sponsor section. The case can carry EITHER:
    #   • sponsor_member_id  → lookup in db.users to get name/email/phone
    #   • sponsor_manual     → use the embedded {name, email, phone, notes} directly
    # Manual wins when both are set (UI keeps them mutually exclusive but be defensive).
    sponsor_info = None
    sm = case.get("sponsor_manual") or {}
    if sm and sm.get("name"):
        sponsor_info = {
            "name": sm.get("name", ""),
            "email": sm.get("email", ""),
            "phone": sm.get("phone", ""),
            "notes": sm.get("notes", ""),
            "source": "External donor",
        }
    elif case.get("sponsor_member_id"):
        u = await db.users.find_one(
            {"id": case["sponsor_member_id"]},
            {"_id": 0, "name": 1, "email": 1, "phone": 1},
        )
        if u:
            sponsor_info = {
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "phone": u.get("phone", ""),
                "notes": "",
                "source": "In-system user",
            }

    html = _render_case_report_html(case, school, notes, payments, compliance_schema, compliance_values, sponsor_info)

    from weasyprint import HTML
    from starlette.responses import StreamingResponse
    import io
    try:
        pdf = HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"Case report PDF failed: {e}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_name = (case.get("subject_name") or "beneficiary").replace(" ", "_")[:40]
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="profile-{safe_name}-{case_id}.pdf"'},
    )


def _esc(value) -> str:
    """Minimal HTML escape for values flowing into the PDF template."""
    if value is None:
        return ""
    s = str(value)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&#39;"))


def _render_case_report_html(case, school, notes, payments, compliance_schema, compliance_values, sponsor_info=None) -> str:
    """Build a branded HTML report — clean, presentation-ready for school/official handoff."""
    edu = case.get("education") or {}
    med = case.get("medical") or {}
    fam = case.get("family") or {}
    goals = case.get("goals") or []

    # Compliance grouped by 'group' key for readable layout
    groups = {"identity": "Identity & Registration", "official": "Administrative & Official",
              "family": "Family & Vulnerability", "school": "School", "health": "Health"}
    fields_by_group = {g: [] for g in groups}
    for f in compliance_schema.get("fields", []):
        g = f.get("group", "family")
        fields_by_group.setdefault(g, []).append(f)

    def _val(v):
        if v is None or v == "":
            return "<em class='muted'>—</em>"
        if isinstance(v, bool):
            return "Yes" if v else "No"
        if isinstance(v, list):
            return ", ".join(_esc(x) for x in v) if v else "<em class='muted'>—</em>"
        return _esc(v)

    compliance_html = ""
    for g_key, g_label in groups.items():
        fields = fields_by_group.get(g_key, [])
        rows = []
        for f in fields:
            raw = compliance_values.get(f["id"])
            if f.get("type") == "yesno":
                raw = bool(raw) if raw is not None else None
            rows.append(f"<tr><td class='label'>{_esc(f['label'])}</td><td>{_val(raw)}</td></tr>")
        if rows:
            compliance_html += f"<h3>{_esc(g_label)}</h3><table class='kv'>{''.join(rows)}</table>"

    payments_total_in = sum(float(p.get("amount") or 0) for p in payments if p.get("direction") == "in")
    payments_total_out = sum(float(p.get("amount") or 0) for p in payments if p.get("direction") == "out")
    payment_rows = "".join(
        f"<tr><td>{_esc(p.get('date',''))}</td><td class='cap'>{_esc(p.get('kind',''))}</td>"
        f"<td>{_esc(p.get('paid_to',''))}</td>"
        f"<td style='text-align:right'>{_esc(p.get('currency','UGX'))} {float(p.get('amount') or 0):,.2f}</td></tr>"
        for p in payments[:30]
    ) or "<tr><td colspan='4' class='muted center'>No payments on record.</td></tr>"

    note_rows = "".join(
        f"<div class='note'><div class='note-h'><span class='cap'>{_esc(n.get('kind',''))}</span> "
        f"<span class='muted'>· {_esc((n.get('created_at') or '')[:10])} · {_esc(n.get('created_by_name',''))}</span></div>"
        f"<p>{_esc(n.get('body',''))}</p></div>"
        for n in notes[:10]
    ) or "<p class='muted'>No notes on record (excluding confidential).</p>"

    goals_html = ""
    if goals:
        goals_html = "<ul class='goals'>" + "".join(
            f"<li><strong>{_esc(g.get('goal',''))}</strong>"
            + (f" — target {_esc(g.get('target_date',''))}" if g.get('target_date') else '')
            + (f" <span class='muted'>({int(g.get('progress_pct',0))}% complete)</span>" if g.get('progress_pct') is not None else '')
            + "</li>"
            for g in goals
        ) + "</ul>"
    else:
        goals_html = "<p class='muted'>No goals on record.</p>"

    school_block = ""
    if school:
        school_block = (
            f"<p><strong>{_esc(school.get('name',''))}</strong>"
            + (f" — {_esc(school.get('address',''))}" if school.get('address') else '')
            + "</p>"
            + (f"<p class='muted'>Head Teacher: {_esc(school.get('head_teacher',''))}{' · '+_esc(school.get('phone','')) if school.get('phone') else ''}</p>" if school.get('head_teacher') or school.get('phone') else '')
        )

    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
<style>
  body {{ font-family: Arial, sans-serif; color: #1a1a2e; font-size: 11px; padding: 18mm; }}
  h1 {{ font-size: 22px; margin: 0; color: #1a1a2e; }}
  h2 {{ font-size: 14px; margin: 18px 0 6px 0; padding-bottom: 4px; border-bottom: 2px solid #48a9c5; color:#1a1a2e; }}
  h3 {{ font-size: 11px; margin: 10px 0 4px 0; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; }}
  .head {{ display: flex; justify-content: space-between; border-bottom: 2px solid #1a1a2e; padding-bottom: 10px; align-items: flex-start; }}
  .logo {{ height: 36px; }}
  .meta {{ color: #64748b; font-size: 10px; }}
  .muted {{ color: #94a3b8; }}
  .center {{ text-align: center; padding: 14px; }}
  .cap {{ text-transform: capitalize; }}
  .subject {{ display: flex; gap: 14px; align-items: center; margin-top: 14px; }}
  .photo {{ height: 64px; width: 64px; border-radius: 50%; object-fit: cover; border: 2px solid #e2e8f0; }}
  .photo-placeholder {{ height: 64px; width: 64px; border-radius: 50%; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 700; color: #94a3b8; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 9px; margin-right: 4px; border: 1px solid; }}
  .pill-cat {{ background: #f3e8ff; color: #6b21a8; border-color: #e9d5ff; }}
  .pill-risk-low {{ background: #d1fae5; color: #065f46; border-color: #6ee7b7; }}
  .pill-risk-medium {{ background: #fef3c7; color: #92400e; border-color: #fcd34d; }}
  .pill-risk-high {{ background: #fee2e2; color: #991b1b; border-color: #fca5a5; }}
  table.kv {{ width: 100%; border-collapse: collapse; margin-bottom: 6px; font-size: 10px; }}
  table.kv td {{ padding: 3px 5px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
  table.kv td.label {{ width: 40%; color: #64748b; }}
  table.payments {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
  table.payments th {{ background: #1a1a2e; color: white; padding: 5px; text-align: left; font-size: 9px; text-transform: uppercase; }}
  table.payments td {{ padding: 4px 5px; border-bottom: 1px solid #e2e8f0; }}
  .totals {{ margin-top: 6px; text-align: right; font-size: 11px; }}
  .note {{ border-left: 3px solid #48a9c5; padding: 4px 8px; margin: 4px 0; background: #f8fafc; }}
  .note-h {{ font-size: 9px; margin-bottom: 2px; }}
  .note p {{ margin: 0; font-size: 10px; white-space: pre-wrap; }}
  ul.goals {{ padding-left: 16px; margin: 4px 0; }}
  ul.goals li {{ margin-bottom: 3px; font-size: 10px; }}
  .footer {{ margin-top: 22mm; text-align: center; font-size: 9px; color: #64748b; }}
  .sig {{ display: flex; justify-content: space-between; margin-top: 14mm; font-size: 10px; color: #64748b; }}
  .sig div {{ width: 45%; border-top: 1px solid #1a1a2e; padding-top: 3px; text-align: center; }}
</style></head><body>
  <div class='head'>
    <div>
      <img src='https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1' class='logo' />
      <p class='meta' style='margin: 6px 0 0 0'>58:12 Global — Social Work &amp; Welfare</p>
      <p class='meta' style='margin: 0'>Confidential Beneficiary Profile Report</p>
    </div>
    <div style='text-align: right'>
      <h1>Profile Report</h1>
      <p class='meta'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
      <p class='meta'>Case ID: {_esc(case.get('id',''))}</p>
    </div>
  </div>

  <div class='subject'>
    {f"<img src='{_esc(case.get('subject_photo_url'))}' class='photo' />" if case.get('subject_photo_url') else f"<div class='photo-placeholder'>{_esc((case.get('subject_name') or '?')[:1])}</div>"}
    <div>
      <h1 style='font-size:18px'>{_esc(case.get('subject_name',''))}</h1>
      <p style='margin: 3px 0; font-size: 10px;'>
        {("DOB " + _esc(case.get('subject_dob','')[:10])) if case.get('subject_dob') else ''}
        {(" · " + _esc(case.get('subject_kind',''))) if case.get('subject_kind') else ''}
      </p>
      <p style='margin: 4px 0 0 0'>
        <span class='pill pill-cat'>{_esc(case.get('category','').replace('_', ' ').title())}</span>
        <span class='pill pill-risk-{_esc(case.get('risk_level','low'))}'>{_esc(case.get('risk_level','low').title())} risk</span>
        <span class='pill' style='background:#f1f5f9;color:#475569;border-color:#cbd5e1'>{_esc(case.get('status','').title())}</span>
      </p>
    </div>
  </div>

  {f"<p class='meta' style='margin-top:8px'>{_esc(case.get('summary',''))}</p>" if case.get('summary') else ''}

  <h2>Education</h2>
  <table class='kv'>
    <tr><td class='label'>Grade / Level</td><td>{_val(edu.get('grade'))}</td></tr>
    <tr><td class='label'>School</td><td>{_val(edu.get('school_name'))}</td></tr>
    <tr><td class='label'>Enrollment date</td><td>{_val((edu.get('enrollment_date') or '')[:10])}</td></tr>
    <tr><td class='label'>Extracurricular</td><td>{_val(edu.get('extracurricular'))}</td></tr>
  </table>
  {school_block}

  <h2>Medical</h2>
  <table class='kv'>
    <tr><td class='label'>Conditions</td><td>{_val(med.get('conditions'))}</td></tr>
    <tr><td class='label'>Allergies</td><td>{_val(med.get('allergies'))}</td></tr>
    <tr><td class='label'>Receives medical support</td><td>{_val(med.get('receives_medical_support'))}</td></tr>
    <tr><td class='label'>Primary doctor / clinic</td><td>{_val(med.get('primary_doctor'))}</td></tr>
    {f"<tr><td class='label'>Notes</td><td>{_esc(med.get('notes'))}</td></tr>" if med.get('notes') else ''}
  </table>

  <h2>Family Situation</h2>
  <table class='kv'>
    <tr><td class='label'>Guardians</td><td>{_val(fam.get('guardians'))}</td></tr>
    <tr><td class='label'>Siblings</td><td>{_val(fam.get('siblings'))}</td></tr>
    <tr><td class='label'>Household income</td><td>{_val(fam.get('household_income'))}</td></tr>
    {f"<tr><td class='label'>Notes</td><td>{_esc(fam.get('notes'))}</td></tr>" if fam.get('notes') else ''}
  </table>

  {(
    "<h2>Sponsor</h2>"
    "<table class='kv'>"
    f"<tr><td class='label'>Name</td><td>{_esc(sponsor_info['name'])}</td></tr>"
    f"<tr><td class='label'>Source</td><td>{_esc(sponsor_info['source'])}</td></tr>"
    + (f"<tr><td class='label'>Email</td><td>{_esc(sponsor_info['email'])}</td></tr>" if sponsor_info.get('email') else '')
    + (f"<tr><td class='label'>Phone</td><td>{_esc(sponsor_info['phone'])}</td></tr>" if sponsor_info.get('phone') else '')
    + (f"<tr><td class='label'>Notes</td><td>{_esc(sponsor_info['notes'])}</td></tr>" if sponsor_info.get('notes') else '')
    + "</table>"
  ) if sponsor_info else ''}

  <h2>{_esc(compliance_schema.get('name', 'Compliance'))}</h2>
  {compliance_html or "<p class='muted'>No compliance fields recorded.</p>"}

  <h2>Goals &amp; Care Plan</h2>
  {goals_html}

  <h2>Payments on Record</h2>
  <table class='payments'>
    <thead><tr><th>Date</th><th>Kind</th><th>Paid to / Source</th><th style='text-align:right'>Amount</th></tr></thead>
    <tbody>{payment_rows}</tbody>
  </table>
  <p class='totals'>
    <strong>Out:</strong> {payments_total_out:,.2f}
    &nbsp;·&nbsp;
    <strong>In (sponsor support):</strong> {payments_total_in:,.2f}
  </p>

  <h2>Recent Case Notes</h2>
  {note_rows}

  <div class='sig'>
    <div>Social Worker — name &amp; signature</div>
    <div>Supervisor — name &amp; signature</div>
  </div>

  <div class='footer'>
    Confidential — to be shared only with authorised school officials, government welfare officers, or approved sponsors.<br/>
    Document generated by 58:12 Connect · {_esc(case.get('id',''))}
  </div>
</body></html>"""


@router.put("/cases/{case_id}")
async def update_case(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"category", "status", "summary", "education", "medical", "family", "goals",
               "risk_level", "sponsor_member_id", "sponsor_manual", "sponsor_guest_id", "compliance"}
    if "status" in data and data["status"] not in CASE_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(CASE_STATUSES)}")
    if data.get("status") == "discharged" and not _can_manage_social_work(current_user):
        raise HTTPException(status_code=403, detail="Only social-work manager+ can discharge a case")
    if "risk_level" in data and data["risk_level"] not in RISK_LEVELS:
        raise HTTPException(status_code=400, detail=f"risk_level must be one of {sorted(RISK_LEVELS)}")
    # Validate sponsor_manual shape — must be either null/missing OR an object with a non-empty name.
    # Anything else gets rejected here rather than landing as garbage that the report PDF then trips on.
    if "sponsor_manual" in data and data["sponsor_manual"] is not None:
        sm = data["sponsor_manual"]
        if not isinstance(sm, dict):
            raise HTTPException(status_code=400, detail="sponsor_manual must be an object or null")
        name = (sm.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="sponsor_manual.name is required when sponsor_manual is set")
        # Normalise: strip whitespace + cap field lengths so junk paste doesn't blow up the report PDF
        data["sponsor_manual"] = {
            "name": name[:120],
            "email": (sm.get("email") or "").strip().lower()[:120],
            "phone": (sm.get("phone") or "").strip()[:32],
            "notes": (sm.get("notes") or "").strip()[:500],
        }
        # Mirror the manual sponsor into db.guests as kind='external_sponsor' so future cases
        # can link the SAME donor by id (no re-typing). Sets case.sponsor_guest_id alongside
        # case.sponsor_manual so the existing guest-payment pipeline lights up automatically.
        guest_id = await _upsert_external_sponsor_guest(data["sponsor_manual"], current_user)
        if guest_id:
            data["sponsor_guest_id"] = guest_id
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    if data.get("status") == "discharged":
        update["discharged_at"] = update["updated_at"]
        update["discharged_by"] = current_user["id"]
        update["discharged_by_name"] = current_user.get("name", "")
    await db.social_cases.update_one({"id": case_id}, {"$set": update})
    await _audit(current_user["id"], "update", "social_case", case_id, {"fields": list(update.keys())})
    return await db.social_cases.find_one({"id": case_id}, {"_id": 0})


@router.get("/sponsors/external")
async def list_external_sponsors(
    search: Optional[str] = None,
    current_user: dict = Depends(require_staff),
):
    """List external sponsor guests so the case detail dialog can autocomplete
    instead of forcing the social worker to re-type the same donor's contact
    info every time they open a new case for that sponsor's child.

    External sponsors are stored as `db.guests` rows with `kind='external_sponsor'`.
    They're created automatically when a manual sponsor is filled on any case
    (see `_upsert_external_sponsor_guest`), but admins can also pre-seed them
    via the standard guests endpoints if they prefer to manage a roster.
    """
    query = {"kind": "external_sponsor"}
    if search and search.strip():
        s = search.strip()
        query["$or"] = [
            {"name": {"$regex": s, "$options": "i"}},
            {"email": {"$regex": s, "$options": "i"}},
            {"phone": {"$regex": s, "$options": "i"}},
        ]
    rows = await db.guests.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1, "notes": 1, "created_at": 1},
    ).sort("name", 1).to_list(500)
    # Annotate each with how many active cases they currently sponsor
    if rows:
        ids = [r["id"] for r in rows]
        pipeline = [
            {"$match": {"sponsor_guest_id": {"$in": ids}, "status": "active"}},
            {"$group": {"_id": "$sponsor_guest_id", "n": {"$sum": 1}}},
        ]
        counts = {}
        async for row in db.social_cases.aggregate(pipeline):
            counts[row["_id"]] = row["n"]
        for r in rows:
            r["active_cases"] = counts.get(r["id"], 0)
    return rows


@router.delete("/sponsors/external/{guest_id}")
async def delete_external_sponsor(guest_id: str, current_user: dict = Depends(require_director)):
    """Director-only: remove an external sponsor guest record.

    Refuses to delete if any ACTIVE case still references this sponsor — surfaces
    the count so the operator knows what to re-link first. Inactive references
    (discharged cases) get nulled out so the case retains its sponsor_manual
    snapshot but the dangling FK is cleaned up.
    """
    g = await db.guests.find_one({"id": guest_id, "kind": "external_sponsor"}, {"_id": 0, "name": 1})
    if not g:
        raise HTTPException(status_code=404, detail="External sponsor not found")
    active = await db.social_cases.count_documents({"sponsor_guest_id": guest_id, "status": "active"})
    if active > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete — {active} active case(s) still reference this sponsor. Re-link or discharge them first.",
        )
    # Null the dangling FK on inactive cases so we don't leave broken references
    await db.social_cases.update_many(
        {"sponsor_guest_id": guest_id}, {"$set": {"sponsor_guest_id": None}}
    )
    await db.guests.delete_one({"id": guest_id})
    await _audit(current_user["id"], "delete", "external_sponsor", guest_id, {"name": g.get("name")})
    return {"deleted": True}


async def _upsert_external_sponsor_guest(sponsor_manual: dict, current_user: dict) -> Optional[str]:
    """Idempotently create-or-find a guest record for an external sponsor.

    Dedup strategy:
      • Primary key — email (case-insensitive) when present.
      • Secondary — phone (exact) when present.
      • Tertiary — name (case-insensitive) alone.

    Returns the guest id (existing or newly-created), or None if upsert failed.
    Non-fatal — sponsor_manual still saves on the case if this errors.
    """
    name = (sponsor_manual.get("name") or "").strip()
    if not name:
        return None
    email = (sponsor_manual.get("email") or "").strip().lower()
    phone = (sponsor_manual.get("phone") or "").strip()
    notes = (sponsor_manual.get("notes") or "").strip()
    try:
        # Look for an existing external_sponsor by email→phone→name (whichever matches first)
        existing = None
        if email:
            existing = await db.guests.find_one(
                {"kind": "external_sponsor", "email": email}, {"_id": 0, "id": 1}
            )
        if not existing and phone:
            existing = await db.guests.find_one(
                {"kind": "external_sponsor", "phone": phone}, {"_id": 0, "id": 1}
            )
        if not existing:
            # re.escape to defend against names with regex metacharacters
            # ('O'Brien (Jr.)', etc.) — would otherwise mis-match or throw.
            import re as _re
            existing = await db.guests.find_one(
                {"kind": "external_sponsor", "name": {"$regex": f"^{_re.escape(name)}$", "$options": "i"}},
                {"_id": 0, "id": 1},
            )

        now = datetime.now(timezone.utc).isoformat()
        if existing:
            # Backfill any fields the caller now has that we didn't previously
            await db.guests.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "name": name,
                    "email": email or None,
                    "phone": phone or None,
                    "notes": notes or None,
                    "updated_at": now,
                    "kind": "external_sponsor",
                    "is_sponsor": True,
                }},
            )
            return existing["id"]
        # Create fresh
        guest_id = f"gst_{uuid.uuid4().hex[:8]}"
        await db.guests.insert_one({
            "id": guest_id,
            "kind": "external_sponsor",
            "is_sponsor": True,
            "name": name,
            "email": email or None,
            "phone": phone or None,
            "notes": notes or None,
            "created_at": now,
            "created_by": current_user["id"],
            "created_by_name": current_user.get("name", ""),
            "source": "social_work_sponsor_manual",
        })
        return guest_id
    except Exception as e:
        logger.warning(f"external sponsor guest upsert failed: {e}")
        return None


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str, current_user: dict = Depends(require_director)):
    """Hard delete — director only. Use status='discharged' to soft-close instead."""
    await db.social_cases.delete_one({"id": case_id})
    await db.social_case_notes.delete_many({"case_id": case_id})
    await db.social_child_payments.delete_many({"case_id": case_id})
    await _audit(current_user["id"], "delete", "social_case", case_id)
    return {"deleted": True}


# ============================================================
# CASE NOTES (chronological narrative)
# ============================================================

@router.get("/cases/{case_id}/notes")
async def list_notes(case_id: str, current_user: dict = Depends(require_staff)):
    return await db.social_case_notes.find({"case_id": case_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/cases/{case_id}/notes")
async def add_note(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    kind = (data.get("kind") or "other").strip().lower()
    if kind not in NOTE_KINDS:
        kind = "other"
    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0, "id": 1, "subject_name": 1, "location_id": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    note = {
        "id": f"scn_{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "kind": kind,
        "body": body[:5000],
        "attachments": data.get("attachments") or [],
        "tags": data.get("tags") or [],
        "is_confidential": bool(data.get("is_confidential", False)),
        "location_id": case.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.social_case_notes.insert_one(note)
    note.pop("_id", None)
    # Bump case updated_at
    await db.social_cases.update_one({"id": case_id}, {"$set": {"updated_at": note["created_at"]}})
    return note


@router.delete("/cases/{case_id}/notes/{note_id}")
async def delete_note(case_id: str, note_id: str, current_user: dict = Depends(require_staff)):
    note = await db.social_case_notes.find_one({"id": note_id, "case_id": case_id}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note["created_by"] != current_user["id"] and not _can_manage_social_work(current_user):
        raise HTTPException(status_code=403, detail="Only the author or a social-work manager can delete this note")
    await db.social_case_notes.delete_one({"id": note_id})
    return {"deleted": True}


# ============================================================
# SCHOOLS
# ============================================================

@router.get("/schools")
async def list_schools(current_user: dict = Depends(require_staff)):
    """List schools visible to the calling user.

    Visibility rules (broader than the default campus filter — social workers
    routinely need to reference partner schools that aren't tagged to their
    own campus):
      • System admins / Directors+ see every school.
      • Anyone with social_work module access sees every school org-wide
        (the schools are partner organisations, not internal campuses).
      • Everyone else sees: their own campus + schools with no campus
        attached (legacy / un-tagged rows that would otherwise be invisible).
    """
    from deps import is_system_admin, has_module_access
    if is_system_admin(current_user) or has_module_access(current_user, "social_work"):
        query = {}
    else:
        scope = await get_campus_filter(current_user)
        # Always include rows that have no location_id stamped (legacy data
        # would otherwise vanish for non-admin viewers — this was the bug).
        if scope:
            query = {"$or": [
                scope,
                {"location_id": {"$in": [None, ""]}},
                {"location_id": {"$exists": False}},
            ]}
        else:
            query = {}
    schools = await db.social_schools.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    # Attach a student count per school
    for s in schools:
        s["student_count"] = await db.social_cases.count_documents({
            "education.school_id": s["id"], "status": "active"
        })
    return schools


@router.post("/schools")
async def create_school(data: dict, current_user: dict = Depends(require_staff)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    # De-dup by name+location
    loc = data.get("location_id") or current_user.get("active_campus_id")
    existing = await db.social_schools.find_one({"name": name, "location_id": loc})
    if existing:
        raise HTTPException(status_code=400, detail=f"School '{name}' already exists for this campus")
    school_id = f"sch_{uuid.uuid4().hex[:10]}"
    portal_token = secrets.token_urlsafe(16)  # used in the public URL — opaque
    doc = {
        "id": school_id,
        "name": name[:200],
        "address": (data.get("address") or "")[:300],
        "country": (data.get("country") or "")[:60],
        "phone": (data.get("phone") or "")[:40],
        "email": (data.get("email") or "")[:120],
        "head_teacher": (data.get("head_teacher") or "")[:120],
        "notes": (data.get("notes") or "")[:1000],
        "portal_token": portal_token,
        "location_id": loc,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.social_schools.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/schools/{school_id}")
async def update_school(school_id: str, data: dict, current_user: dict = Depends(require_staff)):
    allowed = {"name", "address", "country", "phone", "email", "head_teacher", "notes"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.social_schools.update_one({"id": school_id}, {"$set": update})
    return await db.social_schools.find_one({"id": school_id}, {"_id": 0})


@router.delete("/schools/{school_id}")
async def delete_school(school_id: str, current_user: dict = Depends(require_director)):
    in_use = await db.social_cases.count_documents({"education.school_id": school_id, "status": "active"})
    if in_use > 0:
        raise HTTPException(status_code=400, detail=f"School is referenced by {in_use} active case(s) — reassign first")
    await db.social_schools.delete_one({"id": school_id})
    await db.social_school_portal_passwords.delete_many({"school_id": school_id})
    return {"deleted": True}


# ---------- SCHOOL PORTAL PASSWORDS ----------

@router.post("/schools/{school_id}/portal-passwords")
async def issue_school_portal_password(school_id: str, data: dict = None, current_user: dict = Depends(require_staff)):
    """Issue a one-time portal password (7-day expiry by default).
    Returned plaintext can be shown to the social worker ONCE — store hash only.
    Body: { ttl_days?, note? }"""
    if not await _can_issue_portal_password(current_user):
        raise HTTPException(status_code=403, detail="Only social-work staff/manager/director can issue portal passwords")
    school = await db.social_schools.find_one({"id": school_id}, {"_id": 0, "id": 1, "name": 1, "portal_token": 1})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    data = data or {}
    ttl_days = max(1, min(int(data.get("ttl_days") or 7), 30))
    plaintext = secrets.token_urlsafe(9)  # ~12-char alphanumeric token, easy to share
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=ttl_days)).isoformat()
    pw_id = f"spw_{uuid.uuid4().hex[:10]}"
    await db.social_school_portal_passwords.insert_one({
        "id": pw_id,
        "school_id": school_id,
        "password_hash": hash_password(plaintext),
        "expires_at": expires_at,
        "issued_at": now.isoformat(),
        "issued_by": current_user["id"],
        "issued_by_name": current_user.get("name", ""),
        "note": (data.get("note") or "")[:200],
        "revoked": False,
        "last_used_at": None,
        "last_used_ip": None,
    })
    await _audit(current_user["id"], "issue", "school_portal_password", pw_id, {"school": school["name"]})
    return {
        "id": pw_id,
        "school_id": school_id,
        "school_name": school["name"],
        "portal_url_path": f"/school-portal/{school['portal_token']}",
        "portal_token": school["portal_token"],
        "password_plaintext": plaintext,  # ONLY returned here — never stored
        "expires_at": expires_at,
        "ttl_days": ttl_days,
        "note": "Share this URL + password with the school. Both are required to log in. Password expires on the date shown.",
    }


@router.get("/schools/{school_id}/portal-passwords")
async def list_school_portal_passwords(school_id: str, current_user: dict = Depends(require_staff)):
    """List active+expired passwords for a school — does NOT return plaintext."""
    rows = await db.social_school_portal_passwords.find(
        {"school_id": school_id},
        {"_id": 0, "password_hash": 0},
    ).sort("issued_at", -1).to_list(50)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        r["is_active"] = (not r.get("revoked")) and (r.get("expires_at", "") > now)
    return rows


@router.delete("/schools/{school_id}/portal-passwords/{pw_id}")
async def revoke_school_portal_password(school_id: str, pw_id: str, current_user: dict = Depends(require_staff)):
    if not await _can_issue_portal_password(current_user):
        raise HTTPException(status_code=403, detail="Only social-work staff/manager/director can revoke portal passwords")
    await db.social_school_portal_passwords.update_one(
        {"id": pw_id, "school_id": school_id},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(),
                  "revoked_by": current_user["id"]}},
    )
    return {"revoked": True}


# ============================================================
# CHILD PAYMENTS — wired to financials + accounting
# ============================================================

async def _case_payments_summary(case_id: str) -> dict:
    """Total payments per kind for a case."""
    out = {"tuition": 0.0, "resource": 0.0, "medical": 0.0, "child_support_received": 0.0}
    async for p in db.social_child_payments.find({"case_id": case_id}, {"_id": 0}):
        amt = float(p.get("amount") or 0)
        kind = p.get("kind")
        if kind == "child_support":
            out["child_support_received"] += amt
        elif kind in out:
            out[kind] += amt
    # Round to 2dp
    return {k: round(v, 2) for k, v in out.items()}


@router.get("/cases/{case_id}/payments")
async def list_case_payments(case_id: str, current_user: dict = Depends(require_staff)):
    return await db.social_child_payments.find({"case_id": case_id}, {"_id": 0}).sort("date", -1).to_list(500)


@router.post("/cases/{case_id}/payments")
async def add_case_payment(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Record a payment FOR or FROM a child case.
    Body: { kind ('tuition'|'resource'|'medical'|'child_support'), amount, currency?, date?,
            paid_to (school/clinic/etc), notes?, source ('sponsor'|'org_fund'|'partner'|'other') }
    Side effects:
      • Mirror to financial.donations (child_support) or financial.expenses (tuition/resource/medical)
      • Auto-post a balanced journal entry to accounting (via the same helper sales/donations use)."""
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    kind = (data.get("kind") or "").strip().lower()
    if kind not in PAYMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(PAYMENT_KINDS)}")
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount must be numeric")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    pay_id = f"scp_{uuid.uuid4().hex[:10]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    payment = {
        "id": pay_id,
        "case_id": case_id,
        "subject_id": case.get("subject_id"),
        "subject_name": case.get("subject_name"),
        "kind": kind,
        "direction": "in" if kind == "child_support" else "out",
        "amount": amount,
        "currency": (data.get("currency") or "UGX").upper()[:5],
        "date": (data.get("date") or now_iso)[:10],
        "paid_to": (data.get("paid_to") or "")[:200],
        "source": (data.get("source") or "org_fund")[:60],
        "notes": (data.get("notes") or "")[:500],
        "location_id": case.get("location_id"),
        "created_at": now_iso,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    # Mirror into the existing financial collections so the Finance page shows it too.
    try:
        if kind == "child_support":
            mirror = {
                "id": f"don_{uuid.uuid4().hex[:8]}",
                "donor_name": data.get("source_name") or "Child Sponsor",
                "amount": amount,
                "currency": payment["currency"],
                "type": "sponsorship",
                "date": payment["date"],
                "notes": f"Sponsorship for {case.get('subject_name')} [{case_id}]: {payment.get('notes','')}".strip(),
                "location_id": payment["location_id"],
                "created_at": now_iso,
                "created_by": current_user["id"],
                "entered_by": current_user.get("name", ""),
                "social_case_id": case_id,
                "social_payment_id": pay_id,
            }
            await db.donations.insert_one(mirror)
            payment["mirror_id"] = mirror["id"]
            payment["mirror_collection"] = "donations"
        else:
            category_map = {"tuition": "education", "resource": "supplies", "medical": "medical"}
            mirror = {
                "id": f"exp_{uuid.uuid4().hex[:8]}",
                "title": f"{kind.title()} for {case.get('subject_name')}",
                "amount": amount,
                "currency": payment["currency"],
                "category": category_map.get(kind, "general"),
                "date": payment["date"],
                "notes": (payment.get("notes") or "") + f" [case: {case_id}]",
                "location_id": payment["location_id"],
                "status": "approved",  # social-work-recorded payments are post-fact, not pending
                "approved_by": current_user["id"],
                "approved_by_name": current_user.get("name", ""),
                "approved_at": now_iso,
                "created_at": now_iso,
                "created_by": current_user["id"],
                "entered_by": current_user.get("name", ""),
                "social_case_id": case_id,
                "social_payment_id": pay_id,
            }
            await db.expenses.insert_one(mirror)
            payment["mirror_id"] = mirror["id"]
            payment["mirror_collection"] = "expenses"
        # Re-use the financial→accounting auto-post helper if the location has a CoA.
        try:
            from routers.financial import _post_to_accounting
            await _post_to_accounting(
                "donation" if kind == "child_support" else "expense_approved",
                mirror,
                current_user,
            )
        except Exception as e:
            logger.warning(f"Social-work payment ledger auto-post skipped: {e}")
    except Exception as e:
        logger.error(f"Social-work payment mirror failed: {e}")
    await db.social_child_payments.insert_one(payment)
    payment.pop("_id", None)
    await _audit(current_user["id"], "create", "social_payment", pay_id, {"case": case_id, "kind": kind, "amount": amount})
    # Universal activity trail — show payments on the child's profile
    try:
        from routers.activity import log_activity
        await log_activity(
            "child", case.get("subject_id"), "social_payment",
            title=f"{kind.replace('_', ' ').title()}: {payment['currency']} {amount:,.2f}",
            body=(payment.get("notes") or ""),
            actor_id=current_user["id"], actor_name=current_user.get("name", ""),
            amount=amount, currency=payment["currency"],
            ref_id=pay_id, ref_kind="social_payment",
            location_id=case.get("location_id"),
            visibility="public_to_subject" if kind == "child_support" else "internal",
        )
    except Exception as e:
        logger.warning(f"Activity log (social payment) skipped: {e}")
    return payment


@router.delete("/cases/{case_id}/payments/{payment_id}")
async def delete_case_payment(case_id: str, payment_id: str, current_user: dict = Depends(require_manager)):
    """Delete a payment + its mirrored finance entry. Manager+ only (audit-critical)."""
    p = await db.social_child_payments.find_one({"id": payment_id, "case_id": case_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.get("mirror_collection") == "donations" and p.get("mirror_id"):
        await db.donations.delete_one({"id": p["mirror_id"]})
    elif p.get("mirror_collection") == "expenses" and p.get("mirror_id"):
        await db.expenses.delete_one({"id": p["mirror_id"]})
    # Note: we don't auto-reverse the journal entry — leave it for the books.
    # A finance admin can post a reversal manually via /accounting/entries/{id}/reverse.
    await db.social_child_payments.delete_one({"id": payment_id})
    await _audit(current_user["id"], "delete", "social_payment", payment_id, {"reason": "user-initiated"})
    return {"deleted": True, "ledger_reversal_required": True}


@router.get("/payments/summary")
async def payments_summary(period: Optional[str] = None, current_user: dict = Depends(require_staff)):
    """Org-wide payments overview (YYYY-MM, defaults to current month)."""
    period = period or datetime.now(timezone.utc).strftime("%Y-%m")
    start = f"{period}-01"
    y, m = map(int, period.split("-"))
    nm_y, nm_m = (y, m + 1) if m < 12 else (y + 1, 1)
    end = f"{nm_y:04d}-{nm_m:02d}-01"
    query = {"date": {"$gte": start, "$lt": end}}
    scope = await get_campus_filter(current_user)
    if scope:
        query.update(scope)
    rows = await db.social_child_payments.find(query, {"_id": 0}).to_list(2000)
    by_kind: dict = {}
    by_subject: dict = {}
    for r in rows:
        kind = r.get("kind", "")
        by_kind[kind] = by_kind.get(kind, 0) + float(r.get("amount") or 0)
        subj = r.get("subject_id") or ""
        if subj:
            d = by_subject.setdefault(subj, {"subject_name": r.get("subject_name"), "total": 0, "count": 0})
            d["total"] += float(r.get("amount") or 0)
            d["count"] += 1
    return {
        "period": period,
        "by_kind": by_kind,
        "by_subject": list(by_subject.values()),
        "total_out": sum(v for k, v in by_kind.items() if k != "child_support"),
        "total_in": by_kind.get("child_support", 0),
        "count": len(rows),
    }


# ============================================================
# PUBLIC SCHOOL PORTAL — separate auth (token + password)
# ============================================================

PORTAL_SESSION_TTL_HOURS = 6


def _hash_session_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@portal_router.post("/login")
async def school_portal_login(data: dict):
    """Public login for an external school user.
    Body: { portal_token, password }
    Returns: { session_token, school_id, school_name, expires_at } — store the session_token
    client-side and pass via Authorization: Bearer header for subsequent calls."""
    portal_token = (data.get("portal_token") or "").strip()
    password = (data.get("password") or "").strip()
    if not portal_token or not password:
        raise HTTPException(status_code=400, detail="portal_token and password required")
    school = await db.social_schools.find_one({"portal_token": portal_token}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="Unknown school portal — check the URL")
    now_iso = datetime.now(timezone.utc).isoformat()
    # Find a non-revoked, non-expired password whose hash matches
    matches = await db.social_school_portal_passwords.find({
        "school_id": school["id"],
        "revoked": False,
        "expires_at": {"$gt": now_iso},
    }, {"_id": 0}).to_list(20)
    pw_row = next((r for r in matches if verify_password(password, r["password_hash"])), None)
    if not pw_row:
        raise HTTPException(status_code=401, detail="Invalid or expired password")
    # Create a short-lived session token
    raw_session = secrets.token_urlsafe(32)
    session_id = f"sps_{uuid.uuid4().hex[:10]}"
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=PORTAL_SESSION_TTL_HOURS)).isoformat()
    await db.social_school_portal_sessions.insert_one({
        "id": session_id,
        "token_hash": _hash_session_token(raw_session),
        "school_id": school["id"],
        "password_id": pw_row["id"],
        "created_at": now_iso,
        "expires_at": expires_at,
    })
    # Update last-used on the password
    await db.social_school_portal_passwords.update_one(
        {"id": pw_row["id"]},
        {"$set": {"last_used_at": now_iso}},
    )
    return {
        "session_token": raw_session,
        "school_id": school["id"],
        "school_name": school["name"],
        "expires_at": expires_at,
        "ttl_hours": PORTAL_SESSION_TTL_HOURS,
    }


async def _verify_portal_session(authorization: Optional[str]) -> dict:
    """Resolve a school-portal session from the Authorization header.
    Returns the session row + school. Raises 401 on any failure."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing portal session token")
    token = authorization.split(" ", 1)[1].strip()
    th = _hash_session_token(token)
    sess = await db.social_school_portal_sessions.find_one({"token_hash": th}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid portal session token")
    now_iso = datetime.now(timezone.utc).isoformat()
    if sess.get("expires_at", "") <= now_iso:
        raise HTTPException(status_code=401, detail="Portal session expired — log in again")
    school = await db.social_schools.find_one({"id": sess["school_id"]}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=401, detail="School no longer exists")
    return {"session": sess, "school": school}


@portal_router.get("/me")
async def school_portal_me(authorization: Optional[str] = Header(None)):
    """Return the school + its active students for the logged-in school user."""
    ctx = await _verify_portal_session(authorization)
    school = ctx["school"]
    # Active cases at this school
    cases = await db.social_cases.find(
        {"education.school_id": school["id"], "status": "active"},
        {"_id": 0, "id": 1, "subject_id": 1, "subject_name": 1, "subject_photo_url": 1,
         "subject_dob": 1, "category": 1, "education": 1, "risk_level": 1},
    ).sort("subject_name", 1).to_list(500)
    return {
        "school": {
            "id": school["id"],
            "name": school["name"],
            "head_teacher": school.get("head_teacher", ""),
        },
        "students": cases,
        "session_expires_at": ctx["session"]["expires_at"],
    }


@portal_router.get("/students/{case_id}")
async def school_portal_student(case_id: str, authorization: Optional[str] = Header(None)):
    """Detail view (limited) of one student for the school user — includes prior notes."""
    ctx = await _verify_portal_session(authorization)
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case or case.get("education", {}).get("school_id") != ctx["school"]["id"]:
        raise HTTPException(status_code=404, detail="Student not at your school")
    # Strip confidential / private fields before sending out
    safe_case = {
        "id": case["id"],
        "subject_id": case.get("subject_id"),
        "subject_name": case.get("subject_name"),
        "subject_photo_url": case.get("subject_photo_url"),
        "subject_dob": case.get("subject_dob"),
        "category": case.get("category"),
        "education": case.get("education"),
        # Limited medical (just allergies + receives_support) — no diagnoses
        "medical_summary": {
            "allergies": (case.get("medical") or {}).get("allergies") or [],
            "receives_medical_support": (case.get("medical") or {}).get("receives_medical_support") or False,
        },
    }
    # Notes from the school (kind in {school, milestone}) OR uploaded via this portal
    notes = await db.social_case_notes.find(
        {"case_id": case_id, "kind": {"$in": ["school", "milestone"]}, "is_confidential": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"student": safe_case, "notes": notes}


@portal_router.post("/students/{case_id}/notes")
async def school_portal_add_note(case_id: str, data: dict, authorization: Optional[str] = Header(None)):
    """External school staff can upload a report card / note / incident.
    Body: { kind ('school'|'medical'|'other'), body, attachments?: [{name, url}] }"""
    ctx = await _verify_portal_session(authorization)
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0, "id": 1, "education": 1, "location_id": 1, "subject_name": 1})
    if not case or case.get("education", {}).get("school_id") != ctx["school"]["id"]:
        raise HTTPException(status_code=404, detail="Student not at your school")
    kind = (data.get("kind") or "school").strip().lower()
    if kind not in {"school", "medical", "other"}:
        kind = "school"
    body = (data.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    now_iso = datetime.now(timezone.utc).isoformat()
    note = {
        "id": f"scn_{uuid.uuid4().hex[:10]}",
        "case_id": case_id,
        "kind": kind,
        "body": body[:5000],
        "attachments": data.get("attachments") or [],
        "tags": ["school-portal-upload"],
        "is_confidential": False,
        "location_id": case.get("location_id"),
        "source": "school_portal",
        "school_id": ctx["school"]["id"],
        "school_name": ctx["school"]["name"],
        "created_at": now_iso,
        "created_by": f"school_portal:{ctx['school']['id']}",
        "created_by_name": ctx["school"]["name"] + " (external)",
    }
    await db.social_case_notes.insert_one(note)
    note.pop("_id", None)
    await db.social_cases.update_one({"id": case_id}, {"$set": {"updated_at": now_iso}})
    return note


@portal_router.post("/logout")
async def school_portal_logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"logged_out": True}
    token = authorization.split(" ", 1)[1].strip()
    await db.social_school_portal_sessions.delete_one({"token_hash": _hash_session_token(token)})
    return {"logged_out": True}
