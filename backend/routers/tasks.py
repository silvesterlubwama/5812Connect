"""Tasks CRUD routes — archive/restore, assignees, attachments, WebSocket broadcasts"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from deps import db, get_current_user, _audit, logger, get_campus_filter, is_system_admin, expand_descendants
from models import TaskCreate, TaskUpdate
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import uuid
import json

router = APIRouter(prefix="/api", tags=["tasks"])


async def _broadcast_board(board_id: str, action: str, payload: dict, exclude_user: str = None):
    """Broadcast a board event to all WS viewers of a board."""
    if not board_id:
        return
    try:
        from routers.websocket import manager
        await manager.broadcast_to_board(board_id, {
            "type": "board_event",
            "board_id": board_id,
            "action": action,
            **payload,
        }, exclude_user=exclude_user)
    except Exception as e:
        logger.warning(f"WS broadcast failed: {e}")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    board_id: Optional[str] = None,
    list_id: Optional[str] = None,
    include_archived: bool = False,
    current_user: dict = Depends(get_current_user)
) -> list:
    query = {}
    if not include_archived:
        query["is_archived"] = {"$ne": True}
    if status and status != "all":
        query["status"] = status
    if priority and priority != "all":
        query["priority"] = priority
    if assignee:
        query["assignee"] = assignee
    if board_id:
        query["board_id"] = board_id
    if list_id:
        query["list_id"] = list_id

    # Scope tasks to boards the user has access to (same rules as /api/boards).
    # When active_campus_id is set, narrow to JUST that campus (admin/director switched).
    # Otherwise use the union of user's assigned locations.
    user_id = current_user["id"]
    active_campus = current_user.get("active_campus_id")
    if active_campus:
        # Strict scope — admin explicitly chose a campus
        user_locs = {active_campus}
    else:
        user_locs = set(current_user.get("location_ids") or [])
        if current_user.get("location_id"):
            user_locs.add(current_user["location_id"])
    if user_locs:
        # Recursive descendant walk — type-agnostic. Viewing 58:12 Uganda
        # should surface Zimba Farm; viewing 58:12 Global (Central) should
        # surface every descendant (Uganda, Kenya, Haiti, and their sub-locs).
        descendants = await expand_descendants(list(user_locs), include_restricted_from=user_locs, allow_all_restricted=False)
        user_locs |= descendants
    user_locs_list = list(user_locs)

    # Boards on which user has a task assigned — include even if otherwise out of scope
    task_board_ids = await db.tasks.distinct("board_id", {
        "$or": [{"assignees": user_id}, {"assignee": user_id}],
        "is_archived": {"$ne": True},
    })

    or_clauses = []
    if active_campus:
        # STRICT scope — only boards in this campus; escapes are disabled
        if user_locs_list:
            or_clauses.append({"location_id": {"$in": user_locs_list}})
        else:
            return []
    else:
        or_clauses.append({"tagged_members": user_id})
        or_clauses.append({"created_by": user_id})
        if user_locs_list:
            or_clauses.append({"location_id": {"$in": user_locs_list}})
        or_clauses.append({"is_global": True, "is_restricted": {"$ne": True}, "is_private": {"$ne": True}})
    candidate_boards = await db.boards.find({"$or": or_clauses}, {"_id": 0, "id": 1, "tagged_members": 1, "created_by": 1, "is_restricted": 1, "is_private": 1}).to_list(500)
    allowed_board_ids = set()
    for b in candidate_boards:
        if b.get("is_restricted") or b.get("is_private"):
            if user_id in (b.get("tagged_members") or []) or user_id == b.get("created_by"):
                allowed_board_ids.add(b["id"])
        else:
            allowed_board_ids.add(b["id"])
    # Add boards user has tasks on (only when NOT narrowing by active campus)
    if not active_campus:
        for bid in task_board_ids:
            if bid:
                allowed_board_ids.add(bid)
    # Apply the board scope to the task query (only if user requested no specific board)
    if not board_id:
        if not allowed_board_ids:
            return []
        query["board_id"] = {"$in": list(allowed_board_ids)}

    return await db.tasks.find(query, {"_id": 0}).sort("position", 1).to_list(1000)


@router.get("/tasks/archived")
async def list_archived_tasks(
    board_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get archived cards, optionally filtered by board"""
    query = {"is_archived": True}
    if board_id:
        query["board_id"] = board_id
    return await db.tasks.find(query, {"_id": 0}).sort("archived_at", -1).to_list(500)


@router.post("/tasks")
async def create_task(data: TaskCreate, current_user: dict = Depends(get_current_user)) -> dict:
    task = {
        "id": f"task_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "is_archived": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.tasks.insert_one(task)
    task.pop("_id", None)
    await _broadcast_board(task.get("board_id"), "card_created", {
        "list_id": task.get("list_id"),
        "task": task,
    }, exclude_user=current_user["id"])
    return task


# =================== BULK TASK OPERATIONS (must be before parameterized routes) ===================

@router.put("/tasks/bulk-update")
async def bulk_update_tasks(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk update tasks. Body: {ids: [], updates: {status, priority, list_id, board_id, assignees}}"""
    ids = data.get("ids", [])
    updates = data.get("updates", {})
    if not ids or not updates:
        return {"updated": 0}
    allowed = {"status", "priority", "list_id", "board_id", "due_date", "is_archived"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    if "assignees" in updates:
        clean["assignees"] = updates["assignees"]
    clean["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_many({"id": {"$in": ids}}, {"$set": clean})
    return {"updated": result.modified_count}


@router.post("/tasks/bulk-delete")
async def bulk_delete_tasks(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk delete tasks. Body: {ids: []}"""
    ids = data.get("ids", [])
    if not ids:
        return {"deleted": 0}
    result = await db.tasks.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.post("/tasks/bulk-archive")
async def bulk_archive_tasks(data: dict, current_user: dict = Depends(get_current_user)):
    """Bulk archive/unarchive tasks. Body: {ids: [], archive: true/false}"""
    ids = data.get("ids", [])
    archive = data.get("archive", True)
    result = await db.tasks.update_many({"id": {"$in": ids}}, {"$set": {"is_archived": archive, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"updated": result.modified_count}


# =================== SINGLE TASK OPERATIONS ===================

@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, current_user: dict = Depends(get_current_user)) -> dict:
    raw = data.model_dump()
    update_data = {}
    for k, v in raw.items():
        if v is not None:
            update_data[k] = v
        elif k in {"assignees", "labels", "checklist", "attachments", "tags"}:
            # Allow clearing list fields explicitly
            update_data[k] = []
        elif k in {"list_id", "board_id", "position", "assignee", "is_archived"}:
            update_data[k] = v
    update_data.pop("id", None)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_one({"id": task_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    await _broadcast_board(task.get("board_id"), "card_updated", {
        "task_id": task_id,
        "task": task,
    }, exclude_user=current_user["id"])

    # Email notifications for newly assigned users
    new_assignees = update_data.get("assignees")
    if new_assignees:
        try:
            old_task = await db.tasks.find_one({"id": task_id}, {"_id": 0, "assignees": 1})
            old_assignees = set(old_task.get("assignees", [])) if old_task else set()
            newly_added = set(new_assignees) - old_assignees
            if newly_added:
                from email_helpers import notify_task_assigned
                board = await db.boards.find_one({"id": task.get("board_id")}, {"_id": 0, "name": 1})
                for uid in newly_added:
                    assignee = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "name": 1})
                    if assignee and assignee.get("email"):
                        await notify_task_assigned(
                            assignee["email"], assignee.get("name", ""), task.get("title", ""),
                            current_user.get("name", ""), board.get("name", "") if board else ""
                        )
        except Exception as e:
            logger.warning(f"Task assignment email failed: {e}")

    return task


@router.patch("/tasks/{task_id}/move")
async def move_task(task_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Move task to a different list and/or update position"""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    from_list_id = task.get("list_id")
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "list_id" in data:
        update["list_id"] = data["list_id"]
    if "board_id" in data:
        update["board_id"] = data["board_id"]
    if "position" in data:
        update["position"] = data["position"]
    if "status" in data:
        update["status"] = data["status"]
    await db.tasks.update_one({"id": task_id}, {"$set": update})
    moved = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    await _broadcast_board(moved.get("board_id"), "card_moved", {
        "task_id": task_id,
        "from_list_id": from_list_id,
        "to_list_id": moved.get("list_id"),
        "task": moved,
    }, exclude_user=current_user["id"])
    return moved


@router.post("/tasks/{task_id}/snooze")
async def snooze_task(task_id: str, data: dict = None, current_user: dict = Depends(get_current_user)):
    """Snooze a task: suppress the daily overdue-reminder cron and the "due today/tomorrow"
    push notifications until `snooze_until`. Body: { days: 7 } OR { until: 'YYYY-MM-DD' }.
    Default snooze = 7 days. Caller must be the task assignee or a manager+.
    Pass `{ clear: true }` to remove an existing snooze."""
    data = data or {}
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Authorisation: assignees, creator, or manager+ can snooze
    assignees = set(task.get("assignees") or [])
    if task.get("assignee"):
        assignees.add(task["assignee"])
    is_assignee = current_user["id"] in assignees or task.get("created_by") == current_user["id"]
    privileged = (current_user.get("role") or "") in {
        "admin", "system_admin", "Executive Director", "Adviser", "Director", "Manager",
    }
    if not (is_assignee or privileged):
        raise HTTPException(status_code=403, detail="Only assignees or managers can snooze this task")
    if data.get("clear"):
        await db.tasks.update_one({"id": task_id}, {"$unset": {"snooze_until": "", "snoozed_by": "", "snoozed_at": ""}})
        return {"snoozed": False, "task_id": task_id}
    until_iso = (data.get("until") or "").strip()
    if not until_iso:
        from datetime import date as _date
        days = max(1, min(int(data.get("days") or 7), 90))
        until_iso = (_date.today() + timedelta(days=days)).isoformat()
    else:
        until_iso = until_iso[:10]
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.tasks.update_one(
        {"id": task_id},
        {"$set": {"snooze_until": until_iso, "snoozed_by": current_user["id"], "snoozed_at": now_iso, "updated_at": now_iso}},
    )
    fresh = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    await _broadcast_board(fresh.get("board_id"), "card_updated", {"task_id": task_id, "task": fresh}, exclude_user=current_user["id"])
    return {"snoozed": True, "task_id": task_id, "snooze_until": until_iso}



@router.post("/tasks/{task_id}/archive")
async def archive_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """Archive a card (soft delete — removed from board view)"""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.tasks.update_one({"id": task_id}, {"$set": {
        "is_archived": True,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "archived_by": current_user["id"],
    }})
    await _broadcast_board(task.get("board_id"), "card_archived", {
        "task_id": task_id,
        "list_id": task.get("list_id"),
    }, exclude_user=current_user["id"])
    return {"message": "Card archived"}


@router.post("/tasks/{task_id}/restore")
async def restore_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """Restore an archived card to its list"""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.tasks.update_one({"id": task_id}, {
        "$set": {"is_archived": False},
        "$unset": {"archived_at": "", "archived_by": ""},
    })
    restored = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    await _broadcast_board(restored.get("board_id"), "card_restored", {
        "task_id": task_id,
        "list_id": restored.get("list_id"),
        "task": restored,
    }, exclude_user=current_user["id"])
    return restored


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await db.tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    await _broadcast_board(task.get("board_id"), "card_deleted", {
        "task_id": task_id,
        "list_id": task.get("list_id"),
    }, exclude_user=current_user["id"])
    return {"message": "Task deleted"}



# =================== ATTACHMENTS ===================

@router.post("/tasks/{task_id}/attachments")
async def upload_attachment(
    task_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload a file attachment to a card; stores in object storage"""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    contents = await file.read()
    att_id = f"att_{str(uuid.uuid4())[:8]}"
    storage_path = f"card-attachments/{task_id}/{att_id}_{file.filename}"

    stored_url = None
    try:
        from upload_helper import save_upload_sync
        stored_url = save_upload_sync(f"card-attachments/{task_id}", f"{att_id}_{file.filename}", contents, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.warning(f"Attachment upload failed: {e}")
        stored_url = f"/api/tasks/{task_id}/attachments/{att_id}/file"

    att_doc = {
        "id": att_id,
        "name": file.filename,
        "url": stored_url,
        "storage_path": storage_path,
        "mime_type": file.content_type or "application/octet-stream",
        "size": len(contents),
        "source": "upload",
        "uploaded_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.tasks.update_one({"id": task_id}, {"$push": {"attachments": att_doc}})
    task_updated = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    await _broadcast_board(task.get("board_id"), "card_updated", {
        "task_id": task_id,
        "task": task_updated,
    }, exclude_user=current_user["id"])
    return att_doc


@router.delete("/tasks/{task_id}/attachments/{att_id}")
async def delete_attachment(task_id: str, att_id: str, current_user: dict = Depends(get_current_user)):
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.tasks.update_one({"id": task_id}, {"$pull": {"attachments": {"id": att_id}}})
    return {"message": "Attachment deleted"}


# =================== TRELLO IMPORT (flat) ===================

@router.get("/tasks/{task_id}/attachments/{att_id}/file")
async def serve_local_attachment(task_id: str, att_id: str, current_user: dict = Depends(get_current_user)):
    """Serve a locally stored card attachment file."""
    from fastapi.responses import FileResponse
    import os
    local_dir = f"/app/backend/uploads/card-attachments/{task_id}"
    if not os.path.exists(local_dir):
        raise HTTPException(status_code=404, detail="Attachment not found")
    matches = [f for f in os.listdir(local_dir) if f.startswith(att_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = os.path.join(local_dir, matches[0])
    import mimetypes
    mime, _ = mimetypes.guess_type(file_path)
    return FileResponse(file_path, media_type=mime or "application/octet-stream", filename=matches[0][len(att_id)+1:])


@router.post("/tasks/import-trello")
async def import_trello(data: dict, current_user: dict = Depends(get_current_user)):
    """Import tasks from Trello JSON export or generic kanban format."""
    cards = data.get("cards", [])
    lists = data.get("lists", [])
    list_map = {lst.get("id", ""): lst.get("name", "todo") for lst in lists}

    status_mapping = {
        "to do": "todo", "todo": "todo", "backlog": "todo",
        "doing": "in-progress", "in progress": "in-progress",
        "done": "done", "complete": "done", "completed": "done",
    }

    imported = 0
    for card in cards:
        name = card.get("name", "").strip()
        if not name:
            continue
        list_name = list_map.get(card.get("idList", ""), card.get("list", "todo"))
        status = status_mapping.get(list_name.lower(), "todo")

        labels = []
        for lbl in card.get("labels", []):
            if isinstance(lbl, dict):
                labels.append(lbl.get("name", lbl.get("color", "")))
            elif isinstance(lbl, str):
                labels.append(lbl)

        checklist_items = []
        for cl in card.get("checklists", []):
            for item in cl.get("checkItems", cl.get("items", [])):
                checklist_items.append({
                    "text": item.get("name", item.get("text", "")),
                    "completed": item.get("state", "") == "complete" or item.get("completed", False),
                })

        attachments = []
        for att in card.get("attachments", []):
            attachments.append({
                "id": f"att_{str(uuid.uuid4())[:8]}",
                "name": att.get("name", "attachment"),
                "url": att.get("url", ""),
                "mime_type": att.get("mimeType", ""),
                "source": "trello",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        task = {
            "id": f"task_{str(uuid.uuid4())[:8]}",
            "title": name,
            "description": card.get("desc", card.get("description", "")),
            "status": status,
            "priority": "medium",
            "assignee": None,
            "assignees": card.get("idMembers", []),
            "due_date": (card.get("due") or card.get("due_date") or "")[:10] if (card.get("due") or card.get("due_date")) else None,
            "tags": labels[:5],
            "labels": labels,
            "checklist": checklist_items,
            "attachments": attachments,
            "is_archived": False,
            "source": "trello_import",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.tasks.insert_one(task)
        imported += 1

    return {"imported": imported, "message": f"Successfully imported {imported} cards"}


# ========== TASK TIME-TRACKING (P3: Project depth) ==========

@router.post("/tasks/{task_id}/time/start")
async def start_task_timer(task_id: str, data: dict = None, current_user: dict = Depends(get_current_user)):
    """Start a timer for a task. Idempotent — returns the existing open timer if one exists.
    Body: { notes? }"""
    data = data or {}
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0, "id": 1, "title": 1, "board_id": 1})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    existing = await db.task_time_entries.find_one({
        "task_id": task_id,
        "user_id": current_user["id"],
        "ended_at": None,
    }, {"_id": 0})
    if existing:
        return {"already_running": True, "entry": existing}
    now = datetime.now(timezone.utc)
    entry = {
        "id": f"tte_{uuid.uuid4().hex[:10]}",
        "task_id": task_id,
        "task_title": task.get("title"),
        "board_id": task.get("board_id"),
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "started_at": now.isoformat(),
        "ended_at": None,
        "duration_minutes": None,
        "notes": (data.get("notes") or "")[:300],
    }
    await db.task_time_entries.insert_one(entry)
    entry.pop("_id", None)
    return {"already_running": False, "entry": entry}


@router.post("/tasks/{task_id}/time/stop")
async def stop_task_timer(task_id: str, data: dict = None, current_user: dict = Depends(get_current_user)):
    """Stop the current user's running timer for a task. Body: { notes? }"""
    data = data or {}
    entry = await db.task_time_entries.find_one({
        "task_id": task_id,
        "user_id": current_user["id"],
        "ended_at": None,
    }, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=400, detail="No timer running for this task")
    now = datetime.now(timezone.utc)
    try:
        start = datetime.fromisoformat(entry["started_at"].replace("Z", "+00:00"))
        duration = int((now - start).total_seconds() / 60)
    except Exception:
        duration = 0
    update = {
        "ended_at": now.isoformat(),
        "duration_minutes": max(0, duration),
    }
    if data.get("notes"):
        update["notes"] = ((entry.get("notes") or "") + " · " + data["notes"][:300]).strip(" ·")
    await db.task_time_entries.update_one({"id": entry["id"]}, {"$set": update})
    return await db.task_time_entries.find_one({"id": entry["id"]}, {"_id": 0})


@router.post("/tasks/{task_id}/time/log")
async def log_task_time(task_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Manually log time on a task (without a live timer).
    Body: { minutes (int), date? (YYYY-MM-DD, default today), notes? }"""
    task = await db.tasks.find_one({"id": task_id}, {"_id": 0, "id": 1, "title": 1, "board_id": 1})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        minutes = int(data.get("minutes") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="minutes must be an integer")
    if minutes <= 0:
        raise HTTPException(status_code=400, detail="minutes must be positive")
    if minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="Cannot log more than 24h in one entry")
    date_str = (data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": f"tte_{uuid.uuid4().hex[:10]}",
        "task_id": task_id,
        "task_title": task.get("title"),
        "board_id": task.get("board_id"),
        "user_id": current_user["id"],
        "user_name": current_user.get("name", ""),
        "started_at": f"{date_str}T00:00:00+00:00",
        "ended_at": now_iso,
        "duration_minutes": minutes,
        "manual": True,
        "date": date_str,
        "notes": (data.get("notes") or "")[:300],
    }
    await db.task_time_entries.insert_one(entry)
    entry.pop("_id", None)
    return entry


@router.get("/tasks/{task_id}/time")
async def list_task_time_entries(task_id: str, current_user: dict = Depends(get_current_user)):
    """Time entries on a task (everyone's, sorted newest first)."""
    entries = await db.task_time_entries.find({"task_id": task_id}, {"_id": 0}).sort("started_at", -1).to_list(500)
    total_minutes = sum(int(e.get("duration_minutes") or 0) for e in entries if e.get("ended_at"))
    return {
        "entries": entries,
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 2),
    }


@router.delete("/tasks/{task_id}/time/{entry_id}")
async def delete_task_time_entry(task_id: str, entry_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a time entry. Only owner may delete."""
    entry = await db.task_time_entries.find_one({"id": entry_id, "task_id": task_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Only the owner may delete this entry")
    await db.task_time_entries.delete_one({"id": entry_id})
    return {"deleted": True}


@router.get("/time/me/active")
async def my_active_task_timer(current_user: dict = Depends(get_current_user)):
    """Return the user's currently-running task timer (or null)."""
    entry = await db.task_time_entries.find_one({
        "user_id": current_user["id"],
        "ended_at": None,
    }, {"_id": 0})
    return entry

