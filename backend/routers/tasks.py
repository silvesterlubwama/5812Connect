"""Tasks CRUD routes + Trello import"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, logger
from models import TaskCreate, TaskUpdate
from datetime import datetime, timezone
from typing import Optional, List
import uuid
import json

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    board_id: Optional[str] = None,
    list_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if status and status != "all": query["status"] = status
    if priority and priority != "all": query["priority"] = priority
    if assignee: query["assignee"] = assignee
    if board_id: query["board_id"] = board_id
    if list_id: query["list_id"] = list_id
    return await db.tasks.find(query, {"_id": 0}).sort("position", 1).to_list(1000)


@router.post("/tasks")
async def create_task(data: TaskCreate, current_user: dict = Depends(get_current_user)):
    task = {
        "id": f"task_{str(uuid.uuid4())[:8]}",
        **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.tasks.insert_one(task)
    task.pop("_id", None)
    return task


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    # Allow moving between lists
    if "list_id" in data.model_dump():
        update_data["list_id"] = data.model_dump()["list_id"]
    if "board_id" in data.model_dump():
        update_data["board_id"] = data.model_dump()["board_id"]
    if "position" in data.model_dump():
        update_data["position"] = data.model_dump()["position"]
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_one({"id": task_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return await db.tasks.find_one({"id": task_id}, {"_id": 0})


@router.patch("/tasks/{task_id}/move")
async def move_task(task_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """Move task to a different list and/or update position"""
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "list_id" in data: update["list_id"] = data["list_id"]
    if "board_id" in data: update["board_id"] = data["board_id"]
    if "position" in data: update["position"] = data["position"]
    if "status" in data: update["status"] = data["status"]
    await db.tasks.update_one({"id": task_id}, {"$set": update})
    return await db.tasks.find_one({"id": task_id}, {"_id": 0})


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}


@router.post("/tasks/import-trello")
async def import_trello(data: dict, current_user: dict = Depends(get_current_user)):
    """Import tasks from Trello JSON export or generic kanban format.
    Expects: { "cards": [...] } or Trello board JSON with "cards" key.
    Each card: { "name": "...", "desc": "...", "labels": [...], "due": "...", "idList": "...", "checklists": [...] }
    Also supports: { "lists": [...], "cards": [...] } format.
    """
    cards = data.get("cards", [])
    lists = data.get("lists", [])
    list_map = {}
    for lst in lists:
        list_map[lst.get("id", "")] = lst.get("name", "todo")

    # Map Trello list names to our statuses
    status_mapping = {
        "to do": "todo", "todo": "todo", "backlog": "todo",
        "doing": "in-progress", "in progress": "in-progress", "in-progress": "in-progress",
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

        task = {
            "id": f"task_{str(uuid.uuid4())[:8]}",
            "title": name,
            "description": card.get("desc", card.get("description", "")),
            "status": status,
            "priority": "medium",
            "assignee": None,
            "due_date": (card.get("due") or card.get("due_date") or "")[:10] if card.get("due") or card.get("due_date") else None,
            "tags": labels[:5],
            "labels": labels,
            "checklist": checklist_items,
            "source": "trello_import",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.tasks.insert_one(task)
        imported += 1

    return {"imported": imported, "message": f"Successfully imported {imported} cards"}
