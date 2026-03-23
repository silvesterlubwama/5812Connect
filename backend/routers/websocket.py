"""WebSocket real-time notifications and chat"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging
from datetime import datetime, timezone
import uuid
from deps import db

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per user"""
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WS connected: {user_id} (total: {sum(len(v) for v in self.active_connections.values())})")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id] = [ws for ws in self.active_connections[user_id] if ws != websocket]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WS disconnected: {user_id}")

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

    def get_online_users(self) -> List[str]:
        return list(self.active_connections.keys())


manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
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

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "typing":
                    # Notify conversation participants
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
                    if not conv_id or not text:
                        continue
                    conv = await db.conversations.find_one({"id": conv_id}, {"_id": 0, "participants": 1})
                    participants = conv.get("participants", []) if conv else [user_id]
                    if not participants:
                        participants = [user_id]
                    sender_name = msg.get("sender_name")
                    if not sender_name:
                        user = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
                        sender_name = user.get("name") if user else "Unknown"
                    msg_doc = {
                        "id": f"msg_{str(uuid.uuid4())[:8]}",
                        "conversation_id": conv_id,
                        "sender_id": user_id,
                        "sender_name": sender_name,
                        "text": text,
                        "type": "text",
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

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        await manager.broadcast({
            "type": "user_offline",
            "user_id": user_id
        })
