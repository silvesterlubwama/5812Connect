"""Kanban Boards — Trello-like boards per location, with lists and tasks"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, get_current_user, _audit, logger, is_system_admin, get_campus_filter
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api", tags=["boards"])


def _is_admin(user: dict) -> bool:
    return is_system_admin(user)


async def _can_access_board(board: dict, user: dict) -> bool:
    if _is_admin(user):
        return True
    if board.get("is_global"):
        return True
    board_loc = board.get("location_id")
    user_locs = user.get("location_ids") or []
    user_loc = user.get("location_id")
    if user_loc and user_loc not in user_locs:
        user_locs = user_locs + [user_loc]
    # Restricted boards in restricted sub-locations: only tagged members + admins
    if board.get("is_restricted") or board.get("is_private"):
        return user["id"] in (board.get("tagged_members") or []) or user["id"] == board.get("created_by")
    # Check location match
    if board_loc:
        if board_loc in user_locs:
            return True
        # Check if board's location is a sub-location of user's campus
        loc = await db.locations.find_one({"id": board_loc}, {"_id": 0, "parent_id": 1})
        if loc and loc.get("parent_id") in user_locs:
            return True
        return False
    # No location set = visible to all staff
    role = (user.get("role") or "").lower()
    return role in {"manager", "coordinator", "staff", "hr", "director", "adviser"}


async def _broadcast_board(board_id: str, action: str, payload: dict, exclude_user: str = None):
    """Lazily import manager to avoid circular deps and broadcast a board event."""
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


# =================== BOARDS ===================

@router.get("/boards")
async def list_boards(current_user: dict = Depends(get_current_user)):
    """Return all boards accessible to the current user.
    Restricted/private boards in restricted sub-locations: only tagged members.
    Otherwise: boards in user's location(s)."""
    if _is_admin(current_user):
        # Admins see boards filtered by active campus if set, otherwise all
        active = current_user.get("active_campus_id")
        if active:
            sub_locs = await db.locations.find({"parent_id": active, "type": "sub-location"}, {"_id": 0, "id": 1}).to_list(200)
            all_locs = [active] + [s["id"] for s in sub_locs]
            boards = await db.boards.find({"$or": [
                {"location_id": {"$in": all_locs}},
                {"is_global": True},
                {"location_id": {"$exists": False}}, {"location_id": None}, {"location_id": ""},
                {"tagged_members": current_user["id"]}, {"created_by": current_user["id"]},
            ]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        else:
            boards = await db.boards.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    else:
        user_locs_raw = current_user.get("location_ids") or []
        user_loc = current_user.get("location_id")
        if user_loc and user_loc not in user_locs_raw:
            user_locs_raw.append(user_loc)
        # Expand sub-locations
        if user_locs_raw:
            sub_locs = await db.locations.find({"parent_id": {"$in": user_locs_raw}, "type": "sub-location"}, {"_id": 0, "id": 1}).to_list(200)
            user_locs = list(set(user_locs_raw + [s["id"] for s in sub_locs]))
        else:
            user_locs = user_locs_raw
        user_id = current_user["id"]

        # All boards user can see: global + their location + assigned to them
        or_clauses = [
            {"is_global": True},
            {"tagged_members": user_id},
            {"created_by": user_id},
        ]
        if user_locs:
            or_clauses.append({"location_id": {"$in": user_locs}})
        # Also boards with no location (legacy/unassigned)
        or_clauses.append({"location_id": {"$exists": False}})
        or_clauses.append({"location_id": None})
        or_clauses.append({"location_id": ""})

        all_boards = await db.boards.find({"$or": or_clauses}, {"_id": 0}).sort("created_at", -1).to_list(200)
        # Post-filter: remove restricted/private boards unless user is tagged
        boards = []
        for b in all_boards:
            if b.get("is_restricted") or b.get("is_private"):
                if user_id in (b.get("tagged_members") or []) or user_id == b.get("created_by") or _is_admin(current_user):
                    boards.append(b)
            else:
                boards.append(b)

    for b in boards:
        b["list_count"] = await db.board_lists.count_documents({"board_id": b["id"]})
        b["card_count"] = await db.tasks.count_documents({"board_id": b["id"], "is_archived": {"$ne": True}})
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
        "is_restricted": data.get("is_restricted", False),
        "is_private": data.get("is_private", False),
        "tagged_members": data.get("tagged_members", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.boards.insert_one(board)
    board.pop("_id", None)

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
    """Get board with its active lists"""
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
    allowed = {"name", "description", "background", "location_id", "location_name", "is_global", "is_shared", "tagged_members", "is_restricted", "is_private"}
    update = {k: v for k, v in data.items() if k in allowed}
    if data.get("is_shared") and not (await db.boards.find_one({"id": board_id})).get("share_token"):
        update["share_token"] = str(uuid.uuid4())[:12]
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
    await _broadcast_board(board_id, "list_created", {"list": lst}, exclude_user=current_user["id"])
    return lst


@router.put("/boards/{board_id}/lists/{list_id}")
async def update_list(board_id: str, list_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "position", "color", "is_archived", "assigned_to"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise HTTPException(status_code=400, detail="No valid fields")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.board_lists.update_one({"id": list_id, "board_id": board_id}, {"$set": update})
    lst = await db.board_lists.find_one({"id": list_id}, {"_id": 0})
    await _broadcast_board(board_id, "list_updated", {"list_id": list_id, "list": lst}, exclude_user=current_user["id"])
    return lst


@router.post("/boards/{board_id}/lists/{list_id}/archive")
async def archive_list(board_id: str, list_id: str, current_user: dict = Depends(get_current_user)):
    """Archive a list (soft delete — hidden from active board, cards preserved)"""
    await db.board_lists.update_one(
        {"id": list_id, "board_id": board_id},
        {"$set": {"is_archived": True, "archived_at": datetime.now(timezone.utc).isoformat()}}
    )
    await _broadcast_board(board_id, "list_archived", {"list_id": list_id}, exclude_user=current_user["id"])
    return {"message": "List archived"}


@router.post("/boards/{board_id}/lists/{list_id}/restore")
async def restore_list(board_id: str, list_id: str, current_user: dict = Depends(get_current_user)):
    """Restore an archived list back to the active board"""
    await db.board_lists.update_one(
        {"id": list_id, "board_id": board_id},
        {"$set": {"is_archived": False}, "$unset": {"archived_at": ""}}
    )
    lst = await db.board_lists.find_one({"id": list_id}, {"_id": 0})
    await _broadcast_board(board_id, "list_restored", {"list_id": list_id, "list": lst}, exclude_user=current_user["id"])
    return lst


@router.get("/boards/{board_id}/lists/archived")
async def get_archived_lists(board_id: str, current_user: dict = Depends(get_current_user)):
    """Get all archived lists for a board"""
    lists = await db.board_lists.find(
        {"board_id": board_id, "is_archived": True}, {"_id": 0}
    ).sort("archived_at", -1).to_list(100)
    return lists


@router.delete("/boards/{board_id}/lists/{list_id}")
async def delete_list(board_id: str, list_id: str, current_user: dict = Depends(get_current_user)):
    await db.tasks.update_many({"board_id": board_id, "list_id": list_id}, {"$unset": {"list_id": ""}})
    await db.board_lists.delete_one({"id": list_id, "board_id": board_id})
    await _broadcast_board(board_id, "list_deleted", {"list_id": list_id}, exclude_user=current_user["id"])
    return {"message": "List deleted"}


@router.post("/boards/{board_id}/lists/reorder")
async def reorder_lists(board_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    for i, lid in enumerate(data.get("list_ids", [])):
        await db.board_lists.update_one({"id": lid, "board_id": board_id}, {"$set": {"position": i}})
    await _broadcast_board(board_id, "lists_reordered", {"list_ids": data.get("list_ids", [])}, exclude_user=current_user["id"])
    return {"message": "Reordered"}


# =================== TRELLO IMPORT ===================

@router.post("/boards/import-trello")
async def import_trello_board(data: dict, current_user: dict = Depends(get_current_user)):
    """Full Trello board JSON import — creates board + lists + cards + attachments"""
    board_name = data.get("name", "Imported Board")
    location_id = data.get("location_id")
    lists_raw = [l for l in data.get("lists", []) if not l.get("closed", False)]
    cards_raw = [c for c in data.get("cards", []) if not c.get("closed", False)]
    checklists_raw = data.get("checklists", [])
    labels_raw = data.get("labels", [])

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

    list_id_map = await _import_board_lists(lists_raw, board_id)
    imported = await _import_trello_cards(cards_raw, lists_raw, checklists_raw, labels_raw, list_id_map, board_id, current_user["id"])

    board_doc.pop("_id", None)
    await _audit(current_user["id"], "create", "trello_import", board_id, {"board": board_name, "cards": imported})
    return {"board_id": board_id, "board_name": board_name, "lists": len(list_id_map), "imported": imported}


async def _import_board_lists(lists_raw: list, board_id: str) -> dict:
    """Create board lists from Trello data. Returns mapping of trello_list_id -> new_list_id."""
    list_id_map = {}
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
    return list_id_map


async def _import_trello_cards(cards_raw: list, lists_raw: list, checklists_raw: list, labels_raw: list, list_id_map: dict, board_id: str, user_id: str) -> int:
    """Import Trello cards into the board. Returns count of imported cards."""
    import httpx

    checklist_map = {cl["id"]: cl for cl in checklists_raw}
    label_map = {}
    for lbl in labels_raw:
        if lbl.get("id"):
            label_map[lbl["id"]] = {"name": lbl.get("name", ""), "color": lbl.get("color", "")}

    imported = 0
    for card in sorted(cards_raw, key=lambda x: x.get("pos", 0)):
        task = _build_trello_card_doc(card, lists_raw, checklist_map, label_map, list_id_map, board_id, user_id)
        task["attachments"] = await _process_card_attachments(card.get("attachments", []), board_id)
        await db.tasks.insert_one(task)
        imported += 1
    return imported


def _build_trello_card_doc(card: dict, lists_raw: list, checklist_map: dict, label_map: dict, list_id_map: dict, board_id: str, user_id: str) -> dict:
    """Build a task document from a Trello card."""
    trello_list_id = card.get("idList", "")
    list_id = list_id_map.get(trello_list_id)
    list_name = next((lst.get("name", "") for lst in lists_raw if lst["id"] == trello_list_id), "")

    labels = []
    for lbl in card.get("labels", []):
        if isinstance(lbl, dict):
            labels.append({"name": lbl.get("name", lbl.get("color", "")), "color": lbl.get("color", "")})
    for lbl_id in card.get("idLabels", []):
        if lbl_id in label_map and not any(l.get("name") == label_map[lbl_id]["name"] for l in labels):
            labels.append(label_map[lbl_id])

    checklist_items = []
    for cl_id in card.get("idChecklists", []):
        cl = checklist_map.get(cl_id, {})
        for item in cl.get("checkItems", []):
            checklist_items.append({"text": item.get("name", ""), "completed": item.get("state", "") == "complete"})

    status_map = {
        "to do": "todo", "todo": "todo", "backlog": "todo",
        "in progress": "in-progress", "doing": "in-progress",
        "done": "done", "complete": "done", "completed": "done",
    }

    return {
        "id": f"task_{str(uuid.uuid4())[:8]}",
        "board_id": board_id,
        "list_id": list_id,
        "list_name": list_name,
        "title": card.get("name", ""),
        "description": card.get("desc", ""),
        "status": status_map.get(list_name.lower().strip(), "todo"),
        "priority": "medium",
        "assignees": card.get("idMembers", []),
        "assignee": None,
        "due_date": (card.get("due") or "")[:10] if card.get("due") else None,
        "labels": labels,
        "tags": [l.get("name") or l.get("color", "") for l in labels][:5],
        "checklist": checklist_items,
        "attachments": [],
        "trello_id": card.get("id"),
        "position": card.get("pos", 0),
        "cover_color": (card.get("cover") or {}).get("color"),
        "source": "trello_import",
        "is_archived": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user_id,
    }


async def _process_card_attachments(attachments_raw: list, board_id: str) -> list:
    """Process and optionally download Trello card attachments."""
    import httpx
    attachments = []
    for att in attachments_raw:
        att_url = att.get("url", "")
        att_name = att.get("name", "") or att.get("fileName", "") or "attachment"
        att_mime = att.get("mimeType", "")
        att_bytes = att.get("bytes")

        attachment_doc = {
            "id": f"att_{str(uuid.uuid4())[:8]}",
            "name": att_name,
            "url": att_url,
            "mime_type": att_mime,
            "source": "trello",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if att_url and att_bytes and int(att_bytes or 0) < 10 * 1024 * 1024:
            try:
                from storage import put_object
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(att_url)
                    if resp.status_code == 200:
                        storage_path = f"card-attachments/{board_id}/{str(uuid.uuid4())[:8]}_{att_name}"
                        put_object(storage_path, resp.content, att_mime or "application/octet-stream")
                        attachment_doc["storage_path"] = storage_path
                        attachment_doc["copied"] = True
            except Exception as e:
                logger.warning(f"Could not copy Trello attachment: {e}")

        attachments.append(attachment_doc)
    return attachments



# =================== PUBLIC SHARED BOARD ===================

@router.get("/public/boards/{share_token}")
async def get_shared_board(share_token: str):
    """Public read-only access to a shared board."""
    board = await db.boards.find_one({"share_token": share_token, "is_shared": True}, {"_id": 0})
    if not board:
        raise HTTPException(status_code=404, detail="Board not found or sharing disabled")
    lists = await db.board_lists.find({"board_id": board["id"], "is_archived": {"$ne": True}}, {"_id": 0}).sort("position", 1).to_list(100)
    tasks = await db.tasks.find({"board_id": board["id"], "is_archived": {"$ne": True}}, {"_id": 0}).to_list(500)
    return {"board": board, "lists": lists, "tasks": tasks}
