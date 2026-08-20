"""Compliance widgets for the social-work dashboard.

Two rollups:
  • `/compliance/due`           — children whose last welfare visit is older
                                  than `days` days (or never happened)
  • `/compliance/completeness`  — per-child profile-completeness score across
                                  photo + reviews + file-doc checklist
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from deps import db, require_staff

from ._common import FILE_DOC_TYPE_KEYS

router = APIRouter(prefix="/api/social-work/reviews", tags=["social_work_reviews"])


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
    TOTAL_INDICATORS = 4 + len(FILE_DOC_TYPE_KEYS)
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
            **{f"doc_{k}": (k in docs) for k in FILE_DOC_TYPE_KEYS},
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
