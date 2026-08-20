"""Sync a filled review form back into the child profile + compute a risk snapshot.

Called by the create/update endpoints AND by the OCR background job so a review
saved manually and one auto-filled from a scan converge on the same child
document. Idempotent — safe to re-run on every save.
"""
from datetime import datetime, timezone

from deps import db, logger


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
        # Flatten common numeric/text signals onto education.* so the child's
        # Education tab reflects the latest review without re-opening it.
        ad = fields.get("attendance_discipline") or {}
        if ad.get("attendance_pct") is not None:
            try:
                set_ops["education.attendance_pct"] = float(ad["attendance_pct"])
            except (TypeError, ValueError):
                pass
        if ad.get("discipline"):
            set_ops["education.discipline"] = ad["discipline"]
        if ad.get("uniform_status"):
            set_ops["education.uniform_status"] = ad["uniform_status"]
        ap = fields.get("academic_performance") or {}
        if ap.get("overall"):
            set_ops["education.academic_performance"] = ap["overall"]
        if ap.get("position_in_class"):
            set_ops["education.class_position"] = ap["position_in_class"]
        if fields.get("teacher_name"):
            set_ops["education.class_teacher"] = fields["teacher_name"]
        if fields.get("teacher_phone"):
            set_ops["education.teacher_phone"] = fields["teacher_phone"]
        # Compliance: a fresh school-progress review counts toward "termly
        # school visit done" — stamp the date so the compliance dashboard
        # doesn't need staff to double-log it.
        set_ops["compliance.last_school_review_at"] = data.get("review_date") or datetime.now(timezone.utc).date().isoformat()
        set_ops["compliance.school_review_done_this_term"] = True
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
        # Compliance: a welfare/home visit is the flagship compliance box.
        set_ops["compliance.last_home_visit_at"] = data.get("review_date") or datetime.now(timezone.utc).date().isoformat()
        set_ops["compliance.home_visit_done_this_quarter"] = True

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
        # Compliance: annual medical exam stamped for the compliance dashboard.
        set_ops["compliance.last_medical_exam_at"] = data.get("review_date") or datetime.now(timezone.utc).date().isoformat()
        set_ops["compliance.medical_exam_done_this_year"] = True

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
