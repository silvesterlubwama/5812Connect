"""Kanban Boards — Trello-like boards per location, with lists and tasks"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, logger
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["boards"])


def _is_admin(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    return role in {"admin", "system_admin", "executive director", "director"}


async def _can_access_board(board: dict, user: dict) -> bool:
    if _is_admin(user):
        return True
    if board.get("is_global"):
        return True
    if board.get("location_id") and user.get("location_id") == board["location_id"]:
        return True
    # Managers/Coordinators see boards for their location
    role = (user.get("role") or "").lower()
    if role in {"manager", "coordinator", "staff", "hr"}:
        return board.get("location_id") == user.get("location_id") or not board.get("location_id")
    return False


# =================== BOARDS ===================

@router.get("/boards")
async def list_boards(current_user: dict = Depends(get_current_user)):
    """Return all boards accessible to the current user"""
    if _is_admin(current_user):
        boards = await db.boards.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    else:
        user_loc = current_user.get("location_id")
        query = {"$or": [{"is_global": True}, {"location_id": user_loc}]}
        if not user_loc:
            query = {"is_global": True}
        boards = await db.boards.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    # Attach list counts
    for b in boards:
        b["list_count"] = await db.board_lists.count_documents({"board_id": b["id"]})
        b["card_count"] = await db.tasks.count_documents({"board_id": b["id"]})
    return boards


@router.post("/boards")
async def create_board(data: dict, current_user: dict = Depends(get_current_user)):
    board_id = f"board_{str(uuid.uuid4())[:8]}"
    board = {
        "id": board_id,
        "name": data.get("name", "New Board"),
        "description": data.get("description", ""),
        "location_id": data.get("location_id"),
        "location_name": data.get("location_name", ""),
        "background": data.get("background", "#0052cc"),
        "is_global": not data.get("location_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.boards.insert_one(board)
    board.pop("_id", None)

    # Auto-create default lists
    default_lists = data.get("default_lists", ["To Do", "In Progress", "Done"])
    for i, list_name in enumerate(default_lists):
        await db.board_lists.insert_one({
            "id": f"list_{str(uuid.uuid4())[:8]}",
            "board_id": board_id,
            "name": list_name,
            "position": i,
            "color": "",
            "is_archived": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    await _audit(current_user["id"], "create", "board", board_id, {"name": board["name"]})
    return board


@router.get("/boards/{board_id}")
async def get_board(board_id: str, current_user: dict = Depends(get_current_user)):
    """Get board with its lists"""
    board = await db.boards.find_one({"id": board_id}, {"_id": 0})
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    if not await _can_access_board(board, current_user):
        raise HTTPException(status_code=403, detail="Access denied")
    lists = await db.board_lists.find(
        {"board_id": board_id, "is_archived": {"$ne": True}}, {"_id": 0}
    ).sort("position", 1).to_list(100)
    board["lists"] = lists
    return board


@router.put("/boards/{board_id}")
async def update_board(board_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "description", "background", "location_id", "location_name", "is_global"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.boards.update_one({"id": board_id}, {"$set": update})
    return await db.boards.find_one({"id": board_id}, {"_id": 0})


@router.delete("/boards/{board_id}")
async def delete_board(board_id: str, current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin only")
    await db.boards.delete_one({"id": board_id})
    await db.board_lists.delete_many({"board_id": board_id})
    await db.tasks.delete_many({"board_id": board_id})
    return {"message": "Board deleted"}


# =================== LISTS ===================

@router.post("/boards/{board_id}/lists")
async def add_list(board_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    board = await db.boards.find_one({"id": board_id})
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    # Get max position
    last = await db.board_lists.find_one({"board_id": board_id}, {"_id": 0, "position": 1}, sort=[("position", -1)])
    pos = (last["position"] + 1) if last else 0
    lst = {
        "id": f"list_{str(uuid.uuid4())[:8]}",
        "board_id": board_id,
        "name": data.get("name", "New List"),
        "position": pos,
        "color": data.get("color", ""),
        "is_archived": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.board_lists.insert_one(lst)
    lst.pop("_id", None)
    return lst


@router.put("/boards/{board_id}/lists/{list_id}")
async def update_list(board_id: str, list_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "position", "color", "is_archived"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields")
    await db.board_lists.update_one({"id": list_id, "board_id": board_id}, {"$set": update})
    return await db.board_lists.find_one({"id": list_id}, {"_id": 0})


@router.delete("/boards/{board_id}/lists/{list_id}")
async def delete_list(board_id: str, list_id: str, current_user: dict = Depends(get_current_user)):
    # Move cards from this list to first remaining list
    await db.tasks.update_many({"board_id": board_id, "list_id": list_id}, {"$unset": {"list_id": ""}})
    await db.board_lists.delete_one({"id": list_id, "board_id": board_id})
    return {"message": "List deleted"}


@router.post("/boards/{board_id}/lists/reorder")
async def reorder_lists(board_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    """data: {"list_ids": ["list_a", "list_b", ...]} — new order"""
    for i, lid in enumerate(data.get("list_ids", [])):
        await db.board_lists.update_one({"id": lid, "board_id": board_id}, {"$set": {"position": i}})
    return {"message": "Reordered"}


# =================== TRELLO IMPORT ===================

@router.post("/boards/import-trello")
async def import_trello_board(data: dict, current_user: dict = Depends(get_current_user)):
    """Full Trello board JSON import — creates board + lists + cards"""
    board_name = data.get("name", "Imported Board")
    location_id = data.get("location_id")  # optional: assign to a location
    lists_raw = [l for l in data.get("lists", []) if not l.get("closed", False)]
    cards_raw = [c for c in data.get("cards", []) if not c.get("closed", False)]
    checklists_raw = data.get("checklists", [])
    attachments_raw = data.get("attachments", [])
    labels_raw = data.get("labels", [])

    # Create board
    board_id = f"board_{str(uuid.uuid4())[:8]}"
    board_doc = {
        "id": board_id,
        "name": board_name,
        "description": data.get("desc", ""),
        "location_id": location_id,
        "is_global": not location_id,
        "background": data.get("prefs", {}).get("backgroundColor") or "#0052cc",
        "source": "trello_import",
        "trello_id": data.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.boards.insert_one(board_doc)

    # Create lists
    list_id_map = {}  # trello list id → our list id
    for i, lst in enumerate(sorted(lists_raw, key=lambda x: x.get("pos", 0))):
        new_list_id = f"list_{str(uuid.uuid4())[:8]}"
        list_doc = {
            "id": new_list_id,
            "board_id": board_id,
            "name": lst.get("name", "List"),
            "position": i,
            "color": "",
            "is_archived": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.board_lists.insert_one(list_doc)
        list_id_map[lst["id"]] = new_list_id

    # Build checklist map
    checklist_map = {}
    for cl in checklists_raw:
        checklist_map[cl["id"]] = cl

    # Build label map
    label_map = {}
    for lbl in labels_raw:
        if lbl.get("id"):
            label_map[lbl["id"]] = {"name": lbl.get("name", ""), "color": lbl.get("color", "")}

    # Create cards (tasks)
    imported = 0
    for card in sorted(cards_raw, key=lambda x: x.get("pos", 0)):
        trello_list_id = card.get("idList", "")
        list_id = list_id_map.get(trello_list_id)

        # Labels
        labels = []
        for lbl in card.get("labels", []):
            if isinstance(lbl, dict):
                labels.append({"name": lbl.get("name", lbl.get("color", "")), "color": lbl.get("color", "")})
        # Also resolve from idLabels
        for lbl_id in card.get("idLabels", []):
            if lbl_id in label_map and not any(l.get("name") == label_map[lbl_id]["name"] for l in labels):
                labels.append(label_map[lbl_id])

        # Checklists
        checklist_items = []
        for cl_id in card.get("idChecklists", []):
            cl = checklist_map.get(cl_id, {})
            for item in cl.get("checkItems", []):
                checklist_items.append({
                    "text": item.get("name", ""),
                    "completed": item.get("state", "") == "complete",
                })

        # Members/assignees
        assignees = card.get("idMembers", [])

        # Determine status from list name
        list_name = ""
        for lst in lists_raw:
            if lst["id"] == trello_list_id:
                list_name = lst.get("name", "")
                break
        status_map = {
            "to do": "todo", "todo": "todo", "backlog": "todo",
            "in progress": "in-progress", "doing": "in-progress", "in-progress": "in-progress",
            "done": "done", "complete": "done", "completed": "done",
        }
        status = status_map.get(list_name.lower().strip(), "todo")

        task = {
            "id": f"task_{str(uuid.uuid4())[:8]}",
            "board_id": board_id,
            "list_id": list_id,
            "list_name": list_name,
            "title": card.get("name", ""),
            "description": card.get("desc", ""),
            "status": status,
            "priority": "medium",
            "assignees": assignees,
            "assignee": None,
            "due_date": (card.get("due") or "")[:10] if card.get("due") else None,
            "labels": labels,
            "tags": [l.get("name") or l.get("color", "") for l in labels][:5],
            "checklist": checklist_items,
            "trello_id": card.get("id"),
            "position": card.get("pos", 0),
            "cover_color": (card.get("cover") or {}).get("color"),
            "source": "trello_import",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": current_user["id"],
        }
        await db.tasks.insert_one(task)
        imported += 1

    board_doc.pop("_id", None)
    await _audit(current_user["id"], "create", "trello_import", board_id, {"board": board_name, "cards": imported})
    return {"board_id": board_id, "board_name": board_name, "lists": len(list_id_map), "imported": imported}
