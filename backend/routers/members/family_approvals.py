"""Family change requests — the approval flow for edits made by members.

Adding a child or guardian from the portal already lands in a pending state.
Edits used to save straight through, so a parent could quietly rename a child
or change a guardian's phone number with nobody reviewing it. Every portal
edit now becomes a change request: the current value and the proposed value are
stored side by side, admins approve or reject, and only an approval writes the
data.
"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["members"])

REVIEWER_ROLES = {"admin", "system_admin", "Executive Director", "Adviser", "Director",
                  "Regional Director", "Manager", "Coordinator", "HR"}

FIELD_LABELS = {
    "name": "Name", "phone": "Phone", "email": "Email", "relationship": "Relationship",
    "is_parent": "Counts as a parent", "can_pickup": "Allowed to collect children",
    "date_of_birth": "Date of birth", "gender": "Gender", "class_group": "Class / group",
    "medical_notes": "Medical notes", "allergies": "Allergies", "family_name": "Family name",
    "address": "Address", "notes": "Notes", "primary_contact_phone": "Contact phone",
}


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return (str(a or "")).strip() == (str(b or "")).strip()


async def create_change_request(family_id: str, kind: str, target_id: str, target_name: str,
                                before: dict, after: dict, actor: dict) -> dict:
    """Record a proposed edit. Returns the stored request, or a no-op marker."""
    changes = {k: {"from": before.get(k), "to": v}
               for k, v in after.items() if not _same(before.get(k), v)}
    if not changes:
        return {"status": "unchanged", "changes": {}}
    doc = {
        "id": f"fcr_{uuid.uuid4().hex[:10]}",
        "family_id": family_id,
        "kind": kind,                     # guardian | child | family
        "target_id": target_id,
        "target_name": target_name,
        "changes": changes,
        "status": "pending",
        "submitted_by": actor.get("id"),
        "submitted_by_name": actor.get("name", ""),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.family_change_requests.insert_one(dict(doc))
    doc.pop("_id", None)
    from routers.members.families import _log_family_event, _notify_admins_of_family_change
    await _log_family_event(family_id, "change_requested", actor, {
        "kind": kind, "target_id": target_id, "fields": list(changes.keys()),
    })
    await _notify_admins_of_family_change(
        "Family change pending review",
        f"{actor.get('name', 'A member')} proposed changes to {target_name or kind} — needs approval",
        f"/people?tab=family-approvals&request={doc['id']}",
    )
    return doc


@router.get("/families/change-requests")
async def list_change_requests(status: str = "pending", current_user: dict = Depends(get_current_user)):
    """Admin queue of proposed family edits."""
    if (current_user.get("role") or "") not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    query = {} if status == "all" else {"status": status}
    rows = await db.family_change_requests.find(query, {"_id": 0}).sort("submitted_at", -1).to_list(300)
    fam_names = {}
    for r in rows:
        fid = r.get("family_id")
        if fid and fid not in fam_names:
            fam = await db.families.find_one({"id": fid}, {"_id": 0, "family_name": 1})
            fam_names[fid] = (fam or {}).get("family_name", "")
        r["family_name"] = fam_names.get(fid, "")
        r["field_labels"] = {k: FIELD_LABELS.get(k, k.replace("_", " ").title()) for k in r.get("changes", {})}
    return rows


@router.get("/portal/family/change-requests")
async def my_change_requests(current_user: dict = Depends(get_current_user)):
    """What the member has submitted and is still waiting on."""
    from routers.members.families import _resolve_my_family_id
    family_id = await _resolve_my_family_id(current_user)
    if not family_id:
        return []
    rows = await db.family_change_requests.find(
        {"family_id": family_id, "status": "pending"}, {"_id": 0}).sort("submitted_at", -1).to_list(100)
    for r in rows:
        r["field_labels"] = {k: FIELD_LABELS.get(k, k.replace("_", " ").title()) for k in r.get("changes", {})}
    return rows


async def _apply_change(req: dict) -> None:
    values = {k: v["to"] for k, v in req.get("changes", {}).items()}
    if not values:
        return
    if req["kind"] == "guardian":
        res = await db.families.update_one(
            {"id": req["family_id"], "guardians.id": req["target_id"]},
            {"$set": {f"guardians.$.{k}": v for k, v in values.items()}})
    elif req["kind"] == "child":
        res = await db.children.update_one({"id": req["target_id"]}, {"$set": values})
    elif req["kind"] == "family":
        res = await db.families.update_one({"id": req["family_id"]}, {"$set": values})
    else:
        return
    if not res.matched_count:
        raise HTTPException(status_code=409,
                            detail="That record no longer exists — reject this request instead")


@router.post("/families/change-requests/{req_id}/decide")
async def decide_change_request(req_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Body: {action: 'approve'|'reject', reason?}"""
    if (current_user.get("role") or "") not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    action = (data.get("action") or "").lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be approve or reject")
    req = await db.family_change_requests.find_one({"id": req_id, "status": "pending"}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="That request has already been handled")
    if action == "approve":
        await _apply_change(req)
    await db.family_change_requests.update_one({"id": req_id}, {"$set": {
        "status": "approved" if action == "approve" else "rejected",
        "decided_by": current_user["id"],
        "decided_by_name": current_user.get("name", ""),
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "decision_reason": (data.get("reason") or "")[:300],
    }})
    from routers.members.families import _log_family_event
    await _log_family_event(req["family_id"], f"change_{action}d", current_user, {
        "request_id": req_id, "kind": req["kind"], "target_id": req.get("target_id"),
        "fields": list(req.get("changes", {}).keys()),
        "reason": (data.get("reason") or "")[:200],
    })
    try:
        from routers.notifications import create_notification
        await create_notification(
            "Family change " + ("approved" if action == "approve" else "rejected"),
            f"Your update to {req.get('target_name') or 'your household'} was "
            f"{'applied' if action == 'approve' else 'rejected'}"
            + (f" — {data.get('reason')}" if data.get("reason") else ""),
            req["submitted_by"], "info" if action == "approve" else "warning", "/portal/family")
    except Exception:
        pass
    return {"decided": action, "id": req_id}


async def pending_change_map(family_id: Optional[str]) -> dict:
    """{target_id: [pending change requests]} so the portal can badge rows."""
    if not family_id:
        return {}
    out: dict = {}
    async for r in db.family_change_requests.find(
            {"family_id": family_id, "status": "pending"}, {"_id": 0}):
        out.setdefault(r.get("target_id") or family_id, []).append({
            "id": r["id"], "kind": r["kind"],
            "fields": {k: FIELD_LABELS.get(k, k) for k in r.get("changes", {})},
            "submitted_at": r.get("submitted_at"),
        })
    return out
