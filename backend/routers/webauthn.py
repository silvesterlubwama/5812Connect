"""WebAuthn (Passkey/FIDO2) registration and authentication"""
from fastapi import APIRouter, Depends, HTTPException, Request
from deps import db, get_current_user, create_token, logger
from datetime import datetime, timezone, timedelta
import json
import uuid

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes

router = APIRouter(prefix="/api/webauthn", tags=["webauthn"])

RP_NAME = "58:12 Global Connect"


def _get_rp_id(request: Request, body_rp_id: str = None) -> str:
    """Extract RP ID — prefer client-provided, fallback to headers"""
    # Client can pass rpId from window.location.hostname
    if body_rp_id and len(body_rp_id) > 3 and '.' in body_rp_id and '/' not in body_rp_id:
        return body_rp_id
    # Try X-Forwarded-Host (set by some reverse proxies)
    fwd = request.headers.get("x-forwarded-host", "")
    if fwd and '.' in fwd:
        return fwd.split(":")[0]
    # Try origin header
    origin = request.headers.get("origin", "")
    if origin and '.' in origin:
        host = origin.replace("https://", "").replace("http://", "").split(":")[0]
        if '.' in host:
            return host
    # Fall back to host header
    return request.headers.get("host", "localhost").split(":")[0]


# ===== REGISTRATION =====

@router.post("/register/begin")
async def webauthn_register_begin(request: Request, body: dict = {}, current_user: dict = Depends(get_current_user)):
    """Start passkey registration for the authenticated user"""
    rp_id = _get_rp_id(request, body.get("rpId"))
    user_id = current_user["id"]

    # Get existing credentials to exclude (prevent re-registration)
    existing = await db.webauthn_credentials.find(
        {"user_id": user_id, "active": True}, {"_id": 0, "credential_id": 1}
    ).to_list(20)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            type=PublicKeyCredentialType.PUBLIC_KEY,
            id=base64url_to_bytes(cred["credential_id"]),
        )
        for cred in existing
    ]

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_name=current_user.get("email") or current_user.get("name", user_id),
        user_display_name=current_user.get("name", ""),
        user_id=user_id.encode(),
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.PREFERRED,
        ),
        exclude_credentials=exclude_credentials,
    )

    # Store challenge
    challenge_b64 = bytes_to_base64url(options.challenge)
    await db.webauthn_challenges.replace_one(
        {"user_id": user_id, "type": "registration"},
        {
            "user_id": user_id,
            "type": "registration",
            "challenge": challenge_b64,
            "rp_id": rp_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        },
        upsert=True,
    )

    return json.loads(options_to_json(options))


@router.post("/register/complete")
async def webauthn_register_complete(request: Request, body: dict, current_user: dict = Depends(get_current_user)):
    """Complete passkey registration — verify and store credential"""
    rp_id = _get_rp_id(request)
    user_id = current_user["id"]

    stored = await db.webauthn_challenges.find_one({"user_id": user_id, "type": "registration"})
    if not stored:
        raise HTTPException(status_code=400, detail="No pending registration found. Start again.")

    expected_challenge = base64url_to_bytes(stored["challenge"])
    expected_rp_id = stored.get("rp_id", rp_id)

    origin = request.headers.get("origin", f"https://{expected_rp_id}")
    if body.get("expectedOrigin"):
        origin = body["expectedOrigin"]

    try:
        verification = verify_registration_response(
            credential=body,
            expected_challenge=expected_challenge,
            expected_rp_id=expected_rp_id,
            expected_origin=origin,
        )
    except Exception as e:
        logger.warning(f"WebAuthn registration failed: {e}")
        raise HTTPException(status_code=400, detail=f"Registration verification failed: {str(e)}")

    credential_id_b64 = bytes_to_base64url(verification.credential_id)
    public_key_b64 = bytes_to_base64url(verification.credential_public_key)

    # Check not already registered
    existing = await db.webauthn_credentials.find_one({"credential_id": credential_id_b64})
    if existing:
        raise HTTPException(status_code=400, detail="Credential already registered")

    device_name = body.get("device_name") or "Passkey"
    cred_doc = {
        "id": f"wk_{str(uuid.uuid4())[:8]}",
        "user_id": user_id,
        "credential_id": credential_id_b64,
        "public_key": public_key_b64,
        "sign_count": verification.sign_count,
        "aaguid": str(verification.aaguid) if verification.aaguid else None,
        "device_name": device_name,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.webauthn_credentials.insert_one(cred_doc)
    cred_doc.pop("_id", None)

    # Clean up challenge
    await db.webauthn_challenges.delete_one({"user_id": user_id, "type": "registration"})

    return {"success": True, "credential": {k: v for k, v in cred_doc.items() if k not in ("public_key",)}}


# ===== AUTHENTICATION =====

@router.post("/authenticate/begin")
async def webauthn_authenticate_begin(request: Request, body: dict):
    """Start passkey authentication (no auth required — user not yet logged in)"""
    rp_id = _get_rp_id(request, body.get("rpId"))
    email = body.get("email", "").strip().lower()

    allow_credentials = []
    user_id_hint = None

    if email:
        user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
        if user:
            user_id_hint = user["id"]
            creds = await db.webauthn_credentials.find(
                {"user_id": user_id_hint, "active": True}, {"_id": 0, "credential_id": 1}
            ).to_list(20)
            allow_credentials = [
                PublicKeyCredentialDescriptor(
                    type=PublicKeyCredentialType.PUBLIC_KEY,
                    id=base64url_to_bytes(c["credential_id"]),
                )
                for c in creds
            ]

    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=allow_credentials,
    )

    challenge_b64 = bytes_to_base64url(options.challenge)
    # Store challenge keyed by challenge itself for lookup at complete step
    await db.webauthn_challenges.replace_one(
        {"challenge": challenge_b64},
        {
            "challenge": challenge_b64,
            "type": "authentication",
            "rp_id": rp_id,
            "user_id_hint": user_id_hint,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        },
        upsert=True,
    )

    return json.loads(options_to_json(options))


@router.post("/authenticate/complete")
async def webauthn_authenticate_complete(request: Request, body: dict):
    """Complete passkey authentication — verify response and return JWT"""
    rp_id = _get_rp_id(request, body.get("rpId"))
    origin = request.headers.get("origin", f"https://{rp_id}")
    if body.get("expectedOrigin"):
        origin = body["expectedOrigin"]

    # Find challenge
    client_data_b64 = body.get("response", {}).get("clientDataJSON", "")
    if not client_data_b64:
        raise HTTPException(status_code=400, detail="Missing clientDataJSON")

    import base64 as _base64
    import json as _json
    try:
        client_data = _json.loads(_base64.urlsafe_b64decode(client_data_b64 + "=="))
        challenge_b64 = client_data.get("challenge", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid clientDataJSON")

    stored = await db.webauthn_challenges.find_one({"challenge": challenge_b64, "type": "authentication"})
    if not stored:
        raise HTTPException(status_code=400, detail="Challenge not found or expired")

    expected_rp_id = stored.get("rp_id", rp_id)

    expected_challenge = base64url_to_bytes(stored["challenge"])
    expected_rp_id = stored.get("rp_id", rp_id)

    # Find credential
    credential_id = body.get("id") or body.get("rawId")
    cred_doc = await db.webauthn_credentials.find_one({"credential_id": credential_id, "active": True})
    if not cred_doc:
        raise HTTPException(status_code=400, detail="Credential not found")

    public_key_bytes = base64url_to_bytes(cred_doc["public_key"])

    try:
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=expected_challenge,
            expected_rp_id=expected_rp_id,
            expected_origin=origin,
            credential_public_key=public_key_bytes,
            credential_current_sign_count=cred_doc["sign_count"],
        )
    except Exception as e:
        logger.warning(f"WebAuthn authentication failed: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    # Update sign count
    await db.webauthn_credentials.update_one(
        {"credential_id": credential_id},
        {"$set": {"sign_count": verification.new_sign_count, "last_used_at": datetime.now(timezone.utc).isoformat()}}
    )

    # Get user and issue token
    user = await db.users.find_one({"id": cred_doc["user_id"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_token(user["id"])

    # Cleanup
    await db.webauthn_challenges.delete_one({"challenge": challenge_b64})

    return {"token": token, "user": user}


# ===== CREDENTIAL MANAGEMENT =====

@router.get("/credentials")
async def list_credentials(current_user: dict = Depends(get_current_user)):
    creds = await db.webauthn_credentials.find(
        {"user_id": current_user["id"], "active": True},
        {"_id": 0, "public_key": 0}
    ).sort("created_at", -1).to_list(20)
    return creds


@router.delete("/credentials/{cred_id}")
async def remove_credential(cred_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.webauthn_credentials.update_one(
        {"id": cred_id, "user_id": current_user["id"]},
        {"$set": {"active": False, "removed_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"message": "Passkey removed"}
