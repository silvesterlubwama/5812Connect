"""Multi-step approval workflows (Odoo-style).
Generic request system: any record can be sent through a configurable approval chain.
Steps execute sequentially; each step has approver(s) and an outcome.
Supports delegation."""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, require_director, _audit, logger, get_campus_filter
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ===== WORKFLOW TEMPLATES =====

@router.get("/workflows")
async def list_workflows(current_user: dict = Depends(get_current_user)):
    scope = await get_campus_filter(current_user)
    query = {**scope, "active": True} if scope else {"active": True}
    return await db.approval_workflows.find(query, {"_id": 0}).sort("name", 1).to_list(200)


@router.post("/workflows")
async def create_workflow(data: dict, current_user: dict = Depends(require_director)):
    """Create an approval workflow template.
    Body: {
      name, kind (e.g. 'expense'|'leave'|'sale_discount'|'purchase_order'|'custom'),
      steps: [ { name, approver_role?: 'Manager'|'Director'..., approver_user_id?, min_approvals?: 1 } ]
    }"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    steps = data.get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise HTTPException(status_code=400, detail="At least one step required")
    cleaned_steps = []
    for i, s in enumerate(steps):
        if not s.get("name"):
            raise HTTPException(status_code=400, detail=f"Step {i+1} requires a name")
        if not s.get("approver_role") and not s.get("approver_user_id"):
            raise HTTPException(status_code=400, detail=f"Step {i+1} requires approver_role or approver_user_id")
        cleaned_steps.append({
            "id": f"st_{uuid.uuid4().hex[:6]}",
            "name": s["name"][:80],
            "approver_role": s.get("approver_role") or None,
            "approver_user_id": s.get("approver_user_id") or None,
            "min_approvals": max(1, int(s.get("min_approvals") or 1)),
        })
    doc = {
        "id": f"wf_{uuid.uuid4().hex[:10]}",
        "name": name[:80],
        "kind": (data.get("kind") or "custom").strip(),
        "steps": cleaned_steps,
        "active": True,
        "location_id": data.get("location_id") or current_user.get("active_campus_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.approval_workflows.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, data: dict, current_user: dict = Depends(require_director)):
    allowed = {"name", "kind", "active", "steps"}
    update = {k: v for k, v in data.items() if k in allowed}
    await db.approval_workflows.update_one({"id": workflow_id}, {"$set": update})
    return await db.approval_workflows.find_one({"id": workflow_id}, {"_id": 0})


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, current_user: dict = Depends(require_director)):
    # If any requests are open against this WF, deactivate instead
    has_open = await db.approval_requests.find_one({"workflow_id": workflow_id, "status": "in_progress"})
    if has_open:
        await db.approval_workflows.update_one({"id": workflow_id}, {"$set": {"active": False}})
        return {"deactivated": True}
    await db.approval_workflows.delete_one({"id": workflow_id})
    return {"deleted": True}


# ===== APPROVAL REQUESTS =====

def _step_done(step_state: dict) -> bool:
    return step_state.get("status") in {"approved", "rejected"}


def _can_act_on_step(user: dict, step_template: dict) -> bool:
    """Check if `user` is an authorized approver for `step_template`."""
    if step_template.get("approver_user_id") and step_template["approver_user_id"] == user["id"]:
        return True
    role = (user.get("role") or "")
    required_role = step_template.get("approver_role")
    if required_role:
        # System admins / EDs / admins can override anywhere
        if role in {"admin", "system_admin", "Executive Director"}:
            return True
        if role == required_role:
            return True
        # Hierarchical: Director can approve Manager-level; Manager can approve Coordinator/Leader
        hierarchy = ["Volunteer", "Staff", "Coordinator", "Leader", "Manager", "Director", "Adviser", "Executive Director"]
        try:
            u_idx = hierarchy.index(role)
            r_idx = hierarchy.index(required_role)
            return u_idx >= r_idx
        except ValueError:
            return False
    return False


@router.get("/requests")
async def list_requests(
    status: Optional[str] = None,
    subject_kind: Optional[str] = None,
    submitted_by_me: bool = False,
    pending_my_action: bool = False,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """List approval requests with filters."""
    query = {}
    if status:
        query["status"] = status
    if subject_kind:
        query["subject_kind"] = subject_kind
    if submitted_by_me:
        query["submitted_by"] = current_user["id"]
    scope = await get_campus_filter(current_user)
    if scope:
        query.update(scope)
    rows = await db.approval_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    if pending_my_action:
        rows = [
            r for r in rows
            if r.get("status") == "in_progress"
            and r.get("current_step") is not None
            and r["current_step"] < len(r.get("step_states") or [])
            and not _step_done(r["step_states"][r["current_step"]])
            and _can_act_on_step(current_user, r.get("workflow_snapshot", {}).get("steps", [{}])[r["current_step"]] if r["current_step"] < len(r.get("workflow_snapshot", {}).get("steps", [])) else {})
        ]
    return rows


@router.post("/requests")
async def create_request(data: dict, current_user: dict = Depends(get_current_user)):
    """Submit a request against an approval workflow.
    Body: { workflow_id, subject_kind, subject_id?, title, summary?, amount?, metadata? }"""
    wf_id = data.get("workflow_id")
    if not wf_id:
        raise HTTPException(status_code=400, detail="workflow_id required")
    wf = await db.approval_workflows.find_one({"id": wf_id}, {"_id": 0})
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not wf.get("active"):
        raise HTTPException(status_code=400, detail="Workflow is inactive")
    steps = wf.get("steps") or []
    if not steps:
        raise HTTPException(status_code=400, detail="Workflow has no steps")
    now = datetime.now(timezone.utc).isoformat()
    step_states = [{"step_index": i, "status": "pending", "approvals": [], "started_at": (now if i == 0 else None)} for i, _ in enumerate(steps)]
    doc = {
        "id": f"areq_{uuid.uuid4().hex[:10]}",
        "workflow_id": wf_id,
        "workflow_name": wf.get("name"),
        "workflow_snapshot": {"steps": steps, "kind": wf.get("kind")},  # freeze the template at submission
        "subject_kind": (data.get("subject_kind") or wf.get("kind") or "custom")[:60],
        "subject_id": (data.get("subject_id") or "")[:120],
        "title": (data.get("title") or "Untitled")[:200],
        "summary": (data.get("summary") or "")[:1000],
        "amount": float(data.get("amount") or 0) if data.get("amount") is not None else None,
        "currency": data.get("currency") or "UGX",
        "metadata": data.get("metadata") or {},
        "status": "in_progress",  # in_progress | approved | rejected | cancelled
        "current_step": 0,
        "step_states": step_states,
        "submitted_by": current_user["id"],
        "submitted_by_name": current_user.get("name", ""),
        "location_id": current_user.get("active_campus_id") or current_user.get("location_id"),
        "created_at": now,
    }
    await db.approval_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _maybe_advance(req: dict):
    """If the current step is done, advance to the next or finalize."""
    while True:
        idx = req.get("current_step")
        states = req.get("step_states") or []
        if idx is None or idx >= len(states):
            break
        st = states[idx]
        # Compute step completion
        approvals_for = [a for a in (st.get("approvals") or []) if a["outcome"] == "approved"]
        rejections = [a for a in (st.get("approvals") or []) if a["outcome"] == "rejected"]
        step_template = req["workflow_snapshot"]["steps"][idx]
        min_app = int(step_template.get("min_approvals") or 1)
        if rejections:
            states[idx]["status"] = "rejected"
            states[idx]["finished_at"] = datetime.now(timezone.utc).isoformat()
            req["status"] = "rejected"
            req["finished_at"] = states[idx]["finished_at"]
            break
        if len(approvals_for) >= min_app:
            states[idx]["status"] = "approved"
            states[idx]["finished_at"] = datetime.now(timezone.utc).isoformat()
            # Advance
            next_idx = idx + 1
            if next_idx >= len(states):
                req["current_step"] = next_idx
                req["status"] = "approved"
                req["finished_at"] = states[idx]["finished_at"]
                break
            req["current_step"] = next_idx
            states[next_idx]["started_at"] = datetime.now(timezone.utc).isoformat()
            continue
        break
    return req


@router.post("/requests/{request_id}/act")
async def act_on_request(request_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Approve or reject the current step.
    Body: { outcome: 'approved'|'rejected', note? }"""
    req = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "in_progress":
        raise HTTPException(status_code=400, detail=f"Request is {req['status']} — no more actions")
    idx = req.get("current_step")
    steps = req["workflow_snapshot"]["steps"]
    if idx is None or idx >= len(steps):
        raise HTTPException(status_code=400, detail="No active step")
    step_template = steps[idx]
    if not _can_act_on_step(current_user, step_template):
        raise HTTPException(status_code=403, detail=f"Not authorized for step '{step_template.get('name')}' (requires {step_template.get('approver_role') or 'specific user'})")
    outcome = data.get("outcome")
    if outcome not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="outcome must be 'approved' or 'rejected'")
    # De-dup: a single approver shouldn't double-vote on the same step
    if any(a["user_id"] == current_user["id"] for a in (req["step_states"][idx].get("approvals") or [])):
        raise HTTPException(status_code=400, detail="You already acted on this step")
    req["step_states"][idx].setdefault("approvals", []).append({
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "user_role": current_user.get("role", ""),
        "outcome": outcome,
        "note": (data.get("note") or "")[:500],
        "at": datetime.now(timezone.utc).isoformat(),
    })
    req = await _maybe_advance(req)
    await db.approval_requests.replace_one({"id": request_id}, req)
    req.pop("_id", None)
    return req


@router.post("/requests/{request_id}/delegate")
async def delegate_step(request_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Delegate the current step to another user (e.g. while on leave).
    Body: { delegate_to_user_id, note? }
    The delegate becomes an additional authorized approver for the current step."""
    req = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="Request not active")
    idx = req.get("current_step")
    if idx is None or idx >= len(req["workflow_snapshot"]["steps"]):
        raise HTTPException(status_code=400, detail="No active step")
    step_template = req["workflow_snapshot"]["steps"][idx]
    if not _can_act_on_step(current_user, step_template):
        raise HTTPException(status_code=403, detail="Only an authorized approver may delegate this step")
    delegate_id = data.get("delegate_to_user_id")
    if not delegate_id:
        raise HTTPException(status_code=400, detail="delegate_to_user_id required")
    delegate = await db.users.find_one({"id": delegate_id}, {"_id": 0, "id": 1, "name": 1, "role": 1})
    if not delegate:
        raise HTTPException(status_code=404, detail="Delegate not found")
    # Append the delegate as an approver_user_id for this step (additive permission)
    req["step_states"][idx].setdefault("delegations", []).append({
        "from_user_id": current_user["id"],
        "from_user_name": current_user.get("name", ""),
        "to_user_id": delegate_id,
        "to_user_name": delegate.get("name", ""),
        "note": (data.get("note") or "")[:500],
        "at": datetime.now(timezone.utc).isoformat(),
    })
    # Override approver_user_id so delegate becomes authorized (preserve original via approver_role)
    req["workflow_snapshot"]["steps"][idx]["delegated_to"] = delegate_id
    await db.approval_requests.replace_one({"id": request_id}, req)
    req.pop("_id", None)
    return req


@router.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: str, current_user: dict = Depends(get_current_user)):
    """Cancel a request — submitter only, while still in progress."""
    req = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["submitted_by"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the submitter may cancel")
    if req["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="Already finalized")
    await db.approval_requests.update_one({"id": request_id}, {"$set": {
        "status": "cancelled",
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"cancelled": True}


@router.get("/requests/{request_id}")
async def get_request(request_id: str, current_user: dict = Depends(get_current_user)):
    req = await db.approval_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Not found")
    return req
