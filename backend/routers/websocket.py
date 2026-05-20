"""WebSocket real-time notifications, chat, and call signaling"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import json
import logging
from datetime import datetime, timezone
import uuid
from deps import db

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Board room presence ─────────────────────────────────────────────────────
board_rooms: Dict[str, set] = {}   # board_id → {user_id, ...}

# ── Call signaling ──────────────────────────────────────────────────────────
active_calls: Dict[str, Dict] = {}  # call_id → call info
call_participants: Dict[str, Set[str]] = {}  # call_id → set of user_ids

# ── Typing indicators ───────────────────────────────────────────────────────
typing_users: Dict[str, Set[str]] = {}  # conversation_id → set of user_ids

# ── User presence ───────────────────────────────────────────────────────────
try:
    from routers.presence import set_user_online, set_user_offline, update_user_activity
except ImportError:
    def set_user_online(user_id): pass
    def set_user_offline(user_id): pass
    def update_user_activity(user_id): pass


class ConnectionManager:
    """Manages WebSocket connections per user"""
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        # Update presence
        set_user_online(user_id)
        logger.info(f"WS connected: {user_id} (total: {sum(len(v) for v in self.active_connections.values())})")
        # Broadcast presence update
        await self.broadcast_presence(user_id, "online")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id] = [ws for ws in self.active_connections[user_id] if ws != websocket]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Update presence only when all connections closed
                set_user_offline(user_id)
        # Remove from all board rooms on disconnect
        for board_id in list(board_rooms.keys()):
            board_rooms[board_id].discard(user_id)
            if not board_rooms[board_id]:
                del board_rooms[board_id]
        # Remove from typing indicators
        for conv_id in list(typing_users.keys()):
            typing_users[conv_id].discard(user_id)
        logger.info(f"WS disconnected: {user_id}")

    async def broadcast_presence(self, user_id: str, status: str):
        """Broadcast presence change to all connected users"""
        message = {
            "type": "presence_update",
            "user_id": user_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        for uid, connections in self.active_connections.items():
            if uid != user_id:
                for ws in connections:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass

    def is_user_online(self, user_id: str) -> bool:
        """Check if user has active WebSocket connections"""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    def get_online_users(self) -> List[str]:
        """Get list of all online user IDs"""
        return list(self.active_connections.keys())

    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            dead = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active_connections[user_id].remove(ws)

    async def send_to_users(self, user_ids: List[str], message: dict):
        for uid in user_ids:
            await self.send_to_user(uid, message)

    async def broadcast(self, message: dict):
        dead_users = []
        for user_id, connections in self.active_connections.items():
            dead = []
            for ws in connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                connections.remove(ws)
            if not connections:
                dead_users.append(user_id)
        for uid in dead_users:
            del self.active_connections[uid]

    async def broadcast_to_board(self, board_id: str, message: dict, exclude_user: str = None):
        """Send a message to all users currently viewing a board"""
        viewers = board_rooms.get(board_id, set())
        for uid in list(viewers):
            if uid != exclude_user:
                await self.send_to_user(uid, message)

    def get_board_viewers(self, board_id: str) -> List[str]:
        return list(board_rooms.get(board_id, set()))


manager = ConnectionManager()


@router.websocket("/api/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        # Send initial online users
        await websocket.send_json({
            "type": "online_users",
            "users": manager.get_online_users()
        })
        # Notify others
        await manager.broadcast({
            "type": "user_online",
            "user_id": user_id
        })

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                # Update activity on any message
                update_user_activity(user_id)

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                # ══════════════════════════════════════════════════════════════
                # TYPING INDICATORS
                # ══════════════════════════════════════════════════════════════
                elif msg_type == "typing_start":
                    conv_id = msg.get("conversation_id")
                    if conv_id:
                        if conv_id not in typing_users:
                            typing_users[conv_id] = set()
                        typing_users[conv_id].add(user_id)
                        # Get conversation participants and notify them
                        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                        if conv:
                            for pid in conv.get("participants", []):
                                if pid != user_id:
                                    await manager.send_to_user(pid, {
                                        "type": "typing_indicator",
                                        "conversation_id": conv_id,
                                        "user_id": user_id,
                                        "is_typing": True
                                    })

                elif msg_type == "typing_stop":
                    conv_id = msg.get("conversation_id")
                    if conv_id and conv_id in typing_users:
                        typing_users[conv_id].discard(user_id)
                        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                        if conv:
                            for pid in conv.get("participants", []):
                                if pid != user_id:
                                    await manager.send_to_user(pid, {
                                        "type": "typing_indicator",
                                        "conversation_id": conv_id,
                                        "user_id": user_id,
                                        "is_typing": False
                                    })

                # ══════════════════════════════════════════════════════════════
                # MESSAGE REACTIONS (real-time)
                # ══════════════════════════════════════════════════════════════
                elif msg_type == "reaction_add":
                    message_id = msg.get("message_id")
                    emoji = msg.get("emoji")
                    conv_id = msg.get("conversation_id")
                    if message_id and emoji and conv_id:
                        # Get user name
                        u = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
                        user_name = u.get("name", "Unknown") if u else "Unknown"
                        # Notify conversation participants
                        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                        if conv:
                            for pid in conv.get("participants", []):
                                await manager.send_to_user(pid, {
                                    "type": "reaction_update",
                                    "message_id": message_id,
                                    "conversation_id": conv_id,
                                    "action": "add",
                                    "emoji": emoji,
                                    "user_id": user_id,
                                    "user_name": user_name
                                })

                elif msg_type == "reaction_remove":
                    message_id = msg.get("message_id")
                    emoji = msg.get("emoji")
                    conv_id = msg.get("conversation_id")
                    if message_id and emoji and conv_id:
                        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                        if conv:
                            for pid in conv.get("participants", []):
                                await manager.send_to_user(pid, {
                                    "type": "reaction_update",
                                    "message_id": message_id,
                                    "conversation_id": conv_id,
                                    "action": "remove",
                                    "emoji": emoji,
                                    "user_id": user_id
                                })

                # ══════════════════════════════════════════════════════════════
                # PRESENCE / ACTIVITY
                # ══════════════════════════════════════════════════════════════
                elif msg_type == "heartbeat":
                    # Client sends periodic heartbeats to update activity
                    update_user_activity(user_id)
                    await websocket.send_json({"type": "heartbeat_ack"})

                elif msg_type == "set_status":
                    status = msg.get("status", "online")  # online, away, dnd
                    # Broadcast to others
                    await manager.broadcast_presence(user_id, status)

                elif msg_type == "join_board":
                    board_id = msg.get("board_id")
                    if board_id:
                        if board_id not in board_rooms:
                            board_rooms[board_id] = set()
                        board_rooms[board_id].add(user_id)
                        viewers = list(board_rooms[board_id])
                        await websocket.send_json({
                            "type": "board_presence",
                            "board_id": board_id,
                            "viewers": viewers,
                        })
                        await manager.broadcast_to_board(board_id, {
                            "type": "board_presence",
                            "board_id": board_id,
                            "viewers": viewers,
                        }, exclude_user=user_id)

                elif msg_type == "leave_board":
                    board_id = msg.get("board_id")
                    if board_id and board_id in board_rooms:
                        board_rooms[board_id].discard(user_id)
                        if not board_rooms[board_id]:
                            del board_rooms[board_id]
                        else:
                            await manager.broadcast_to_board(board_id, {
                                "type": "board_presence",
                                "board_id": board_id,
                                "viewers": list(board_rooms[board_id]),
                            })

                elif msg_type == "typing":
                    conv_id = msg.get("conversation_id")
                    participants = msg.get("participants", [])
                    for pid in participants:
                        if pid != user_id:
                            await manager.send_to_user(pid, {
                                "type": "typing",
                                "user_id": user_id,
                                "conversation_id": conv_id,
                            })

                elif msg_type == "chat_message":
                    conv_id = msg.get("conversation_id")
                    text = msg.get("text", "").strip()
                    reply_to = msg.get("reply_to")
                    if not conv_id or not text:
                        continue
                    conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                    participants = conv.get("participants", []) if conv else [user_id]
                    if not participants:
                        participants = [user_id]
                    sender_name = msg.get("sender_name")
                    if not sender_name:
                        user_doc = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
                        sender_name = user_doc.get("name") if user_doc else "Unknown"
                    msg_doc = {
                        "id": f"msg_{str(uuid.uuid4())[:8]}",
                        "conversation_id": conv_id,
                        "sender_id": user_id,
                        "sender_name": sender_name,
                        "text": text,
                        "type": "text",
                        "reply_to": reply_to,
                        "read_by": [user_id],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.chat_messages.insert_one(msg_doc)
                    msg_doc.pop("_id", None)
                    await db.conversations.update_one(
                        {"id": conv_id},
                        {"$set": {"updated_at": msg_doc["created_at"], "last_message": text[:100]}}
                    )
                    await manager.send_to_users(participants, {
                        "type": "chat_message",
                        "conversation_id": conv_id,
                        "message": msg_doc,
                    })

                elif msg_type == "read_receipt":
                    conv_id = msg.get("conversation_id")
                    message_id = msg.get("message_id")
                    if conv_id and message_id:
                        await db.chat_messages.update_one(
                            {"id": message_id},
                            {"$addToSet": {"read_by": user_id}}
                        )
                        conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                        if conv:
                            await manager.send_to_users(conv.get("participants", []), {
                                "type": "read_receipt",
                                "conversation_id": conv_id,
                                "message_id": message_id,
                                "user_id": user_id,
                            })

                # ══════════════════════════════════════════════════════════════
                # CALL SIGNALING
                # ══════════════════════════════════════════════════════════════
                elif msg_type == "call_offer":
                    # Initiating a call - send offer to target
                    call_id = msg.get("call_id")
                    target_user_id = msg.get("target_user_id")
                    sdp = msg.get("sdp")
                    call_type = msg.get("call_type", "audio")
                    caller_name = msg.get("caller_name", "Unknown")
                    caller_extension = msg.get("caller_extension")
                    
                    if target_user_id and sdp:
                        # Store call info
                        active_calls[call_id] = {
                            "id": call_id,
                            "caller_id": user_id,
                            "caller_name": caller_name,
                            "caller_extension": caller_extension,
                            "target_user_id": target_user_id,
                            "call_type": call_type,
                            "status": "ringing",
                            "started_at": datetime.now(timezone.utc).isoformat()
                        }
                        call_participants[call_id] = {user_id, target_user_id}
                        
                        # Send offer to target
                        await manager.send_to_user(target_user_id, {
                            "type": "incoming_call",
                            "call_id": call_id,
                            "caller_id": user_id,
                            "caller_name": caller_name,
                            "caller_extension": caller_extension,
                            "call_type": call_type,
                            "sdp": sdp
                        })
                        logger.info(f"Call offer from {user_id} to {target_user_id}")

                elif msg_type == "call_answer":
                    # Answering a call - send answer back to caller
                    call_id = msg.get("call_id")
                    sdp = msg.get("sdp")
                    caller_id = msg.get("caller_id")
                    
                    if call_id in active_calls:
                        active_calls[call_id]["status"] = "connected"
                        active_calls[call_id]["answered_at"] = datetime.now(timezone.utc).isoformat()
                    
                    if caller_id and sdp:
                        await manager.send_to_user(caller_id, {
                            "type": "call_answered",
                            "call_id": call_id,
                            "sdp": sdp,
                            "answerer_id": user_id
                        })
                        logger.info(f"Call {call_id} answered by {user_id}")

                elif msg_type == "ice_candidate":
                    # ICE candidate exchange
                    call_id = msg.get("call_id")
                    candidate = msg.get("candidate")
                    target_user_id = msg.get("target_user_id")
                    
                    if target_user_id and candidate:
                        await manager.send_to_user(target_user_id, {
                            "type": "ice_candidate",
                            "call_id": call_id,
                            "candidate": candidate,
                            "from_user_id": user_id
                        })

                elif msg_type == "call_reject":
                    # Rejecting an incoming call
                    call_id = msg.get("call_id")
                    caller_id = msg.get("caller_id")
                    reason = msg.get("reason", "rejected")
                    
                    if call_id in active_calls:
                        active_calls[call_id]["status"] = "rejected"
                        del active_calls[call_id]
                    if call_id in call_participants:
                        del call_participants[call_id]
                    
                    if caller_id:
                        await manager.send_to_user(caller_id, {
                            "type": "call_rejected",
                            "call_id": call_id,
                            "rejected_by": user_id,
                            "reason": reason
                        })
                        logger.info(f"Call {call_id} rejected by {user_id}")

                elif msg_type == "call_hangup":
                    # Ending a call
                    call_id = msg.get("call_id")
                    
                    if call_id in call_participants:
                        # Notify all participants
                        for pid in call_participants[call_id]:
                            if pid != user_id:
                                await manager.send_to_user(pid, {
                                    "type": "call_ended",
                                    "call_id": call_id,
                                    "ended_by": user_id
                                })
                        del call_participants[call_id]
                    if call_id in active_calls:
                        del active_calls[call_id]
                    logger.info(f"Call {call_id} ended by {user_id}")

                elif msg_type == "call_hold":
                    call_id = msg.get("call_id")
                    is_held = msg.get("is_held", True)
                    
                    if call_id in call_participants:
                        for pid in call_participants[call_id]:
                            if pid != user_id:
                                await manager.send_to_user(pid, {
                                    "type": "call_hold_changed",
                                    "call_id": call_id,
                                    "is_held": is_held,
                                    "by_user_id": user_id
                                })

                elif msg_type == "call_mute":
                    call_id = msg.get("call_id")
                    is_muted = msg.get("is_muted", True)
                    media_type = msg.get("media_type", "audio")  # audio or video
                    
                    if call_id in call_participants:
                        for pid in call_participants[call_id]:
                            if pid != user_id:
                                await manager.send_to_user(pid, {
                                    "type": "call_mute_changed",
                                    "call_id": call_id,
                                    "is_muted": is_muted,
                                    "media_type": media_type,
                                    "by_user_id": user_id
                                })

                elif msg_type == "call_transfer":
                    # Transfer call to another user
                    call_id = msg.get("call_id")
                    transfer_to_user_id = msg.get("transfer_to_user_id")
                    sdp = msg.get("sdp")
                    
                    if transfer_to_user_id:
                        call_info = active_calls.get(call_id, {})
                        await manager.send_to_user(transfer_to_user_id, {
                            "type": "incoming_transfer",
                            "call_id": call_id,
                            "from_user_id": user_id,
                            "original_call": call_info,
                            "sdp": sdp
                        })
                        logger.info(f"Call {call_id} transfer initiated to {transfer_to_user_id}")

                elif msg_type == "conference_add":
                    # Add participant to conference
                    call_id = msg.get("call_id")
                    new_participant_id = msg.get("participant_id")
                    sdp = msg.get("sdp")
                    
                    if call_id and new_participant_id:
                        if call_id not in call_participants:
                            call_participants[call_id] = set()
                        call_participants[call_id].add(new_participant_id)
                        
                        call_info = active_calls.get(call_id, {})
                        await manager.send_to_user(new_participant_id, {
                            "type": "conference_invite",
                            "call_id": call_id,
                            "from_user_id": user_id,
                            "participants": list(call_participants[call_id]),
                            "sdp": sdp
                        })
                        
                        # Notify existing participants
                        for pid in call_participants[call_id]:
                            if pid != user_id and pid != new_participant_id:
                                await manager.send_to_user(pid, {
                                    "type": "conference_participant_added",
                                    "call_id": call_id,
                                    "new_participant_id": new_participant_id
                                })

                elif msg_type == "screen_share_start":
                    call_id = msg.get("call_id")
                    if call_id in call_participants:
                        for pid in call_participants[call_id]:
                            if pid != user_id:
                                await manager.send_to_user(pid, {
                                    "type": "screen_share_started",
                                    "call_id": call_id,
                                    "by_user_id": user_id
                                })

                elif msg_type == "screen_share_stop":
                    call_id = msg.get("call_id")
                    if call_id in call_participants:
                        for pid in call_participants[call_id]:
                            if pid != user_id:
                                await manager.send_to_user(pid, {
                                    "type": "screen_share_stopped",
                                    "call_id": call_id,
                                    "by_user_id": user_id
                                })

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        await manager.broadcast({
            "type": "user_offline",
            "user_id": user_id
        })
