"""Tasks CRUD routes — archive/restore, assignees, attachments, WebSocket broadcasts"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from deps import db, get_current_user, _audit, logger
from models import TaskCreate, TaskUpdate
from datetime import datetime, timezone
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
):
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
async def create_task(data: TaskCreate, current_user: dict = Depends(get_current_user)):
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


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, current_user: dict = Depends(get_current_user)):
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
async def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
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
        from storage import put_object, init_storage
        result = put_object(storage_path, contents, file.content_type or "application/octet-stream")
        stored_url = result.get("url") or result.get("public_url")
    except Exception as e:
        logger.warning(f"Object storage failed, using local: {e}")
        # Fallback: save locally
        import os
        local_dir = f"/app/backend/uploads/card-attachments/{task_id}"
        os.makedirs(local_dir, exist_ok=True)
        local_path = f"{local_dir}/{att_id}_{file.filename}"
        with open(local_path, "wb") as f_out:
            f_out.write(contents)
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
