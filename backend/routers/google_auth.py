"""Google OAuth login endpoint — moved out of server.py in iter303.

Verifies a Google-issued ID token (via emergentintegrations when available,
falling back to a raw JWT payload decode) and returns a normal 58:12 JWT.
New Google users land in `status=pending` awaiting admin approval.
"""
import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from deps import db, create_token

router = APIRouter(prefix="/api")


@router.post("/auth/google")
async def google_auth(data: dict):
    """Authenticate via Google OAuth token."""
    google_token = data.get("token") or data.get("credential")
    if not google_token:
        raise HTTPException(status_code=400, detail="Google token required")
    try:
        from emergentintegrations.llm.google_auth import verify_google_token
        google_user = verify_google_token(google_token)
    except ImportError:
        # Fallback: decode JWT manually
        parts = google_token.split(".")
        if len(parts) >= 2:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
            google_user = {"email": payload.get("email"), "name": payload.get("name"), "picture": payload.get("picture")}
        else:
            raise HTTPException(status_code=400, detail="Invalid Google token")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Google auth failed: {str(e)}")
    email = google_user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email from Google")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user = {
            "id": str(uuid.uuid4()), "name": google_user.get("name", email.split("@")[0]),
            "email": email, "phone": "", "password_hash": "",
            "role": "Guest", "status": "pending", "avatar": google_user.get("picture", ""),
            "auth_provider": "google",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one({**user})
        user.pop("_id", None)
    else:
        if google_user.get("picture"):
            await db.users.update_one({"email": email}, {"$set": {"avatar": google_user["picture"]}})
    token = create_token(user["id"])
    return {"token": token, "user": {k: v for k, v in user.items() if k != "password_hash"}}
