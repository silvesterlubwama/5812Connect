"""Tasks CRUD routes"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user
from models import TaskCreate, TaskUpdate
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, priority: Optional[str] = None, assignee: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if status and status != "all": query["status"] = status
    if priority and priority != "all": query["priority"] = priority
    if assignee: query["assignee"] = assignee
    return await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/tasks")
async def create_task(data: TaskCreate, current_user: dict = Depends(get_current_user)):
    task = {"id": f"task_{str(uuid.uuid4())[:8]}", **data.model_dump(), "created_at": datetime.now(timezone.utc).isoformat(), "created_by": current_user["id"]}
    await db.tasks.insert_one(task)
    task.pop("_id", None)
    return task


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.tasks.update_one({"id": task_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return await db.tasks.find_one({"id": task_id}, {"_id": 0})


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.tasks.delete_one({"id": task_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}
