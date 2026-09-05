"""TOTP-based 2FA endpoints — moved out of server.py in iter303.

Setup, verify (enable), validate (during login), and disable. Uses `pyotp`
for TOTP and `qrcode` to render the enrollment QR.
"""
import base64
from io import BytesIO

import pyotp
from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user

router = APIRouter(prefix="/api")


@router.post("/auth/2fa/setup")
async def setup_2fa(current_user: dict = Depends(get_current_user)):
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.get("email", ""), issuer_name="58:12 Global Connect")
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"totp_secret": secret, "totp_enabled": False}})
    try:
        import qrcode
        img = qrcode.make(uri)
        buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        qr_base64 = base64.b64encode(buf.read()).decode()
        return {"secret": secret, "uri": uri, "qr_code": f"data:image/png;base64,{qr_base64}"}
    except Exception:
        return {"secret": secret, "uri": uri}


@router.post("/auth/2fa/verify")
async def verify_2fa(data: dict, current_user: dict = Depends(get_current_user)):
    code = data.get("code", "")
    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0, "totp_secret": 1})
    secret = user.get("totp_secret") if user else None
    if not secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    totp = pyotp.TOTP(secret)
    if totp.verify(code):
        await db.users.update_one({"id": current_user["id"]}, {"$set": {"totp_enabled": True}})
        return {"verified": True, "message": "2FA enabled successfully"}
    raise HTTPException(status_code=400, detail="Invalid code")


@router.post("/auth/2fa/validate")
async def validate_2fa_login(data: dict):
    """Validate 2FA code during login."""
    user_id = data.get("user_id")
    code = data.get("code", "")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "totp_secret": 1, "totp_enabled": 1})
    if not user or not user.get("totp_enabled"):
        return {"valid": True}
    totp = pyotp.TOTP(user["totp_secret"])
    if totp.verify(code):
        return {"valid": True}
    raise HTTPException(status_code=400, detail="Invalid 2FA code")


@router.delete("/auth/2fa")
async def disable_2fa(current_user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": current_user["id"]}, {"$set": {"totp_enabled": False, "totp_secret": None}})
    return {"message": "2FA disabled"}
