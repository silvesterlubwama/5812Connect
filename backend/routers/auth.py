"""Auth routes: register, login, me, logout, google-session, password reset"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pin_security import pin_digest, pin_query, pin_matches
from deps import SECRET_KEY, db, raw_db, get_current_user, hash_password, verify_password, create_token, create_token_with_session, logger, is_system_admin, _audit, enforce_public_rate_limit, can_view_pay, is_super_admin, org_for_hostname, org_bypass, set_current_org
from models import UserRegister, UserLogin
from org_bootstrap import ensure_default_organization
from datetime import datetime, timezone, timedelta
import uuid

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/pin-login")
async def pin_login(data: dict, request: Request) -> dict:
    """Cashier / Kiosk PIN sign-in. Used on POS to switch cashiers without typing email+password.
    Body: {pin: "1234", store_id?: "loc_xxx"}
    Returns a short-lived staff token (8h) + cashier info.
    Requires the user to have an `active` status and a non-empty `pin` field.
    Optionally restricts to staff at the given store/sub-location's parent campus."""
    pin = (data.get("pin") or "").strip()
    if not pin or len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 digits")
    # iter371 — PINs have been stored as an HMAC digest since iter353; this
    # route was still querying the cleartext `pin` field that the migration
    # removed, so every cashier PIN sign-in failed.
    await enforce_public_rate_limit(request, "pin_login", limit=10, window_minutes=10)
    user = await db.users.find_one({**pin_query(pin), "status": "active"}, {"_id": 0, "password_hash": 0})
    if not user or not pin_matches(pin, user):
        raise HTTPException(status_code=401, detail="Invalid PIN")
    # Optional store restriction: cashier must be at this store, its parent campus, or its sub-locations
    store_id = (data.get("store_id") or "").strip()
    if store_id:
        user_locs = set(user.get("location_ids") or [])
        if user.get("location_id"):
            user_locs.add(user["location_id"])
        # Add parent campus and sibling sub-locations
        if user_locs:
            parents = await db.locations.find(
                {"id": {"$in": list(user_locs)}, "parent_id": {"$exists": True, "$nin": [None, ""]}},
                {"_id": 0, "parent_id": 1}
            ).to_list(50)
            for p in parents:
                if p.get("parent_id"):
                    user_locs.add(p["parent_id"])
            subs = await db.locations.find(
                {"parent_id": {"$in": list(user_locs)}},
                {"_id": 0, "id": 1}
            ).to_list(200)
            for s in subs:
                user_locs.add(s["id"])
        if store_id not in user_locs and not is_system_admin(user):
            raise HTTPException(status_code=403, detail=f"This PIN is not assigned to {store_id}")
    token = await create_token_with_session(user["id"], request)
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "name": user.get("name", ""),
            "role": user.get("role", ""),
            "email": user.get("email", ""),
            "location_id": user.get("location_id"),
        },
    }


@router.post("/auth/register")
async def register(data: UserRegister) -> dict:
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    # Allow self-registration as visitor/parent with pending status
    role = getattr(data, 'role', None) or 'Guest'
    if role not in {'Guest', 'Member', 'visitor', 'parent'}:
        role = 'Guest'  # new signups start as guests, approved by director/manager
    expiry = None
    if role == 'visitor':
        # Visitors get 30-day access by default
        expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    user = {
        "id": user_id,
        "name": data.name,
        "email": data.email.lower(),
        "phone": getattr(data, 'phone', None),
        "national_id": getattr(data, 'national_id', None),
        "password_hash": hash_password(data.password),
        "role": role,
        "status": "pending",
        "expires_at": expiry,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = create_token(user_id)
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    return {"token": token, "user": user_out}


@router.post("/auth/visitor-register")
async def visitor_register(data: dict) -> dict:
    """Quick visitor/parent guest account creation — no password required, phone-based."""
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or f"visitor_{uuid.uuid4().hex[:8]}@kiosk.local").strip().lower()
    role = data.get("role", "visitor")
    if role not in {"visitor", "parent"}:
        role = "visitor"
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    existing = await db.users.find_one({"phone": phone}) if phone else None
    if existing:
        user_out = {k: v for k, v in existing.items() if k not in ("password_hash", "_id")}
        return {"token": None, "user": user_out, "existing": True}

    user_id = str(uuid.uuid4())
    pin = data.get("pin") or uuid.uuid4().hex[:4].upper()
    expiry = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    user = {
        "id": user_id,
        "name": name,
        "email": email,
        "phone": phone,
        "national_id": data.get("national_id"),
        "password_hash": hash_password(pin),
        "role": role,
        "status": "pending",
        # iter353 — only the keyed digest is stored; the PIN itself is shown
        # once, here in the response, and never persisted in clear text.
        "guest_pin_lookup": pin_digest(pin),
        "pin_lookup": pin_digest(pin),
        "expires_at": expiry,
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    # Also create a member record for check-in purposes
    member_id = str(uuid.uuid4())
    await db.members.insert_one({
        "id": member_id, "user_id": user_id, "name": name, "email": email,
        "phone": phone, "role": "Guest", "status": "pending",
        "membership_type": role, "national_id": data.get("national_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    return {"token": None, "user": user_out, "pin": pin, "member_id": member_id}


async def _resolve_login_org(user: dict, host_org: dict):
    """Decide which organisation this sign-in belongs to.

    Returns (org_id, org, pending_response). When pending_response is not None
    the caller should return it as-is — that is the super admin being asked
    which organisation to enter, since they are never in more than one."""
    if is_super_admin(user):
        if host_org:
            with org_bypass():
                await raw_db.users.update_one(
                    {"id": user["id"]}, {"$set": {"active_organization_id": host_org["id"]}}
                )
            return host_org["id"], host_org, None
        with org_bypass():
            orgs = await raw_db.organizations.find(
                {}, {"_id": 0, "id": 1, "name": 1, "slug": 1, "status": 1}
            ).sort("name", 1).to_list(500)
        if not orgs:
            # A deployment upgraded before the first-boot bootstrap existed has
            # data but no organisation, and the owner was shown an empty "choose
            # an organisation" screen. Create organisation #1 here and carry on.
            await ensure_default_organization()
            with org_bypass():
                orgs = await raw_db.organizations.find(
                    {}, {"_id": 0, "id": 1, "name": 1, "slug": 1, "status": 1}
                ).sort("name", 1).to_list(500)
        active = user.get("active_organization_id")
        if len(orgs) == 1 and (not active or not any(o["id"] == active for o in orgs)):
            # Nothing to choose between. Asking "which organisation?" with a
            # single option — or with none at all, as a freshly upgraded
            # deployment had — is a dead end, not a safeguard.
            only = orgs[0]
            if only.get("status") == "suspended":
                # Signing them in without entering it: the organisations console
                # is not organisation-scoped, so this is the only way back in to
                # reactivate it. A hard 403 left the owner locked out of their
                # own platform.
                return None, None, {"requires_org_selection": True, "organizations": orgs,
                                    "all_suspended": True}
            with org_bypass():
                await raw_db.users.update_one(
                    {"id": user["id"]}, {"$set": {"active_organization_id": only["id"]}}
                )
                org = await raw_db.organizations.find_one({"id": only["id"]}, {"_id": 0})
            return only["id"], org or {}, None
        if not orgs:
            raise HTTPException(
                status_code=503,
                detail="This site has no organisation yet. It is created automatically when the "
                       "server starts — please try again in a moment.",
            )
        if not active or not any(o["id"] == active for o in orgs):
            return None, None, {"requires_org_selection": True, "organizations": orgs}
        with org_bypass():
            org = await raw_db.organizations.find_one({"id": active}, {"_id": 0})
        if org and org.get("status") == "suspended":
            raise HTTPException(status_code=403, detail=f"{org.get('name')} is suspended")
        return active, org or {}, None

    org_id = user.get("organization_id")
    if not org_id:
        # An account that predates organisations. Their credentials are valid and
        # there is exactly one place they can belong to — the organisation this
        # address maps to, or the default one. Refusing them with "contact your
        # administrator" was wrong: there was nothing an administrator could do
        # from inside the app.
        # Always the default organisation — never "whichever address they used".
        # These accounts predate organisations, so they belong to the original
        # one; a tenant's own address can only admit its own people, and those
        # already carry an organisation.
        with org_bypass():
            fallback = await raw_db.organizations.find_one(
                {"status": "active", "is_default": True}, {"_id": 0}
            ) or await raw_db.organizations.find_one({"status": "active"}, {"_id": 0})
        if not fallback:
            await ensure_default_organization()
            with org_bypass():
                fallback = await raw_db.organizations.find_one(
                    {"status": "active", "is_default": True}, {"_id": 0}
                ) or await raw_db.organizations.find_one({"status": "active"}, {"_id": 0})
        if not fallback:
            raise HTTPException(
                status_code=503,
                detail="This site has no organisation yet. It is created automatically when the "
                       "server starts — please try again in a moment.",
            )
        org_id = fallback["id"]
        with org_bypass():
            await raw_db.users.update_one({"id": user["id"]}, {"$set": {"organization_id": org_id}})
        logger.info("Attached pre-organisation account %s to %s", user.get("email"), fallback.get("name"))
    if host_org and host_org["id"] != org_id:
        raise HTTPException(status_code=403, detail="This account does not belong to this site")
    with org_bypass():
        org = await raw_db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=403, detail="Organisation not found")
    if org.get("status") == "suspended":
        raise HTTPException(
            status_code=403,
            detail=f"{org.get('name', 'This organisation')} is suspended. Contact the system owner.",
        )
    return org_id, org, None


@router.post("/auth/login")
async def login(data: UserLogin, request: Request) -> dict:
    # Brute-force throttle — mirrors the security_checkpoint pair tarpit pattern.
    # Per-IP counter in `login_attempts` collection: 6+ failures in 60s → 429 + tarpit.
    import asyncio
    client_ip = "anon"
    try:
        if request and request.client:
            client_ip = request.client.host or request.headers.get("x-forwarded-for", "anon").split(",")[0].strip() or "anon"
    except Exception:
        pass
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    recent_failures = await db.login_attempts.count_documents(
        {"ip": client_ip, "ok": False, "at": {"$gte": cutoff}},
    )
    if recent_failures >= 6:
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts — wait a minute and try again.",
        )

    identifier = data.identifier.strip()
    identifier_lower = identifier.lower()
    # Build flexible lookup — exact match on email, phone (with normalization), national_id
    phone_variants = [identifier]
    # Handle phone number normalization (e.g. 0700... → +256700...)
    if identifier.startswith('+'):
        phone_variants.append(identifier.lstrip('+'))
        if len(identifier) > 4:
            phone_variants.append('0' + identifier[-9:])  # +256700... → 0700...
    elif identifier.startswith('0') and len(identifier) >= 9:
        phone_variants.append('+256' + identifier[1:])  # 0700... → +256700...
    # Pre-auth lookup: we cannot know the organisation until we know who this
    # is, so this single query is deliberately cross-tenant. Everything after
    # the password check runs pinned to one organisation.
    host_org = await org_for_hostname(request)
    identity_query = {
        "$or": [
            {"email": identifier_lower},
            {"phone": {"$in": phone_variants}},
            {"national_id": identifier},
        ]
    }
    # When the request arrives on an organisation's own hostname, only that
    # organisation's accounts may sign in there — the same email at another
    # tenant is a different person.
    if host_org:
        # …except the platform owner, who belongs to no organisation and is the
        # one account allowed to enter any of them. Without this they were
        # refused on every organisation's own address.
        identity_query = {"$and": [
            identity_query,
            {"$or": [
                {"organization_id": host_org["id"]},
                # Only the owner. An account with no organisation must NOT be
                # let in here: it would be captured by whichever address it
                # happened to use, moving a 58:12 person into another tenant.
                {"role": {"$regex": "^super_admin$", "$options": "i"}},
            ]},
        ]}
    with org_bypass():
        # Two organisations may legitimately hold the same email as two
        # different people, so match on the password too rather than taking
        # whichever row Mongo happens to return first — otherwise only one of
        # them could ever sign in on a shared hostname.
        candidates = await raw_db.users.find(identity_query).to_list(20)
    user = None
    for candidate in candidates:
        if verify_password(data.password, candidate.get("password_hash", "")):
            user = candidate
            break
    if user is None and candidates:
        user = candidates[0]  # fall through to the normal failure path below
    now_iso = datetime.now(timezone.utc).isoformat()

    async def _record_failure():
        try:
            await db.login_attempts.insert_one({
                "ip": client_ip, "identifier": identifier_lower[:80], "at": now_iso, "ok": False,
            })
        except Exception:
            pass

    if not user or not verify_password(data.password, user.get("password_hash", "")):
        await _record_failure()
        await asyncio.sleep(0.4)  # tarpit — slows blind brute-forcing further
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get("status") == "pending":
        raise HTTPException(status_code=403, detail="Your account is pending approval. Please contact your administrator.")
    # Check if 2FA is enabled - require code
    if user.get("totp_enabled") and not data.totp_code:
        return {"requires_2fa": True, "user_id": user["id"], "message": "2FA code required"}
    if user.get("totp_enabled") and data.totp_code:
        import pyotp
        totp = pyotp.TOTP(user.get("totp_secret", ""))
        if not totp.verify(data.totp_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
    # ---- organisation gate ----
    org_id, org, pending = await _resolve_login_org(user, host_org)
    if pending is not None:
        # A super admin with no organisation chosen yet. Issue a token so they
        # can reach the organisation picker — it unlocks nothing else, because
        # every data route resolves scope from active_organization_id, which is
        # still empty.
        pending["token"] = await create_token_with_session(user["id"], request)
        pending["user_id"] = user["id"]
        pending["message"] = "Choose which organisation to enter"
        return pending
    set_current_org(org_id)

    # Always default to user's primary campus on login
    user_loc = user.get("location_id") or (user.get("location_ids") or [None])[0]
    if not user_loc:
        # No location assigned — find the first campus
        first_campus = await db.locations.find_one({"type": {"$in": ["campus", "main"]}}, {"_id": 0, "id": 1})
        if first_campus:
            user_loc = first_campus["id"]
    if user_loc:
        await db.users.update_one({"id": user["id"]}, {"$set": {"active_campus_id": user_loc}})
        user["active_campus_id"] = user_loc
    token = await create_token_with_session(user["id"], request)
    user_out = {k: v for k, v in user.items() if k not in ("password_hash", "_id")}
    user_out["organization_id"] = org_id
    user_out["organization_name"] = org.get("name", "")
    # Record success so a string of recent failures resets for this IP
    try:
        await db.login_attempts.insert_one({"ip": client_ip, "identifier": identifier_lower[:80], "at": now_iso, "ok": True, "user_id": user["id"]})
    except Exception:
        pass
    return {"token": token, "user": user_out}


@router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)) -> dict:
    user_out = {k: v for k, v in current_user.items() if k not in ("password_hash", "_id")}
    # Computed capability flags the UI needs up front (no extra round-trip).
    user_out["can_view_pay"] = can_view_pay(current_user)
    # Enrich with location name for campus display
    if user_out.get("location_id"):
        loc = await db.locations.find_one({"id": user_out["location_id"]}, {"_id": 0, "name": 1})
        user_out["location_name"] = loc.get("name") if loc else ""
    # Enrich security-contractor users with their company name+logo so the
    # portal badge can render dual-logo without a follow-up round-trip.
    if user_out.get("security_company_id"):
        co = await db.security_companies.find_one(
            {"id": user_out["security_company_id"]}, {"_id": 0, "name": 1, "logo_url": 1}
        )
        if co:
            user_out["security_company_name"] = co.get("name")
            user_out["security_company_logo_url"] = co.get("logo_url")
    return user_out


@router.post("/auth/logout")
async def logout(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    """Revoke the current session's jti so the token cannot be reused."""
    try:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            from jose import jwt
            import os
            token = auth.split(" ", 1)[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti:
                await db.sessions.update_one({"jti": jti}, {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()}})
    except Exception as e:
        logger.warning(f"Logout session revoke: {e}")
    # Signing out leaves the organisation too, so the platform owner is asked
    # which one to open next time instead of silently resuming the last.
    if is_super_admin(current_user):
        with org_bypass():
            await raw_db.users.update_one(
                {"id": current_user["id"]}, {"$set": {"active_organization_id": None}}
            )
    return {"message": "Logged out successfully"}


@router.get("/auth/sessions")
async def list_sessions(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    """List all active sessions for the current user; flag the current session."""
    current_jti = None
    try:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            from jose import jwt
            import os
            token = auth.split(" ", 1)[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            current_jti = payload.get("jti")
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    sessions = await db.sessions.find(
        {"user_id": current_user["id"], "revoked": {"$ne": True}, "expires_at": {"$gt": now}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    for s in sessions:
        s["is_current"] = (s.get("jti") == current_jti)
        if isinstance(s.get("expires_at"), datetime):
            s["expires_at"] = s["expires_at"].isoformat()
    return {"sessions": sessions, "current_jti": current_jti}


@router.delete("/auth/sessions/{jti}")
async def revoke_session(jti: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Revoke a specific session (must belong to the current user)."""
    result = await db.sessions.update_one(
        {"jti": jti, "user_id": current_user["id"]},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session revoked"}


@router.post("/auth/sessions/revoke-others")
async def revoke_other_sessions(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    """Revoke all sessions for the current user EXCEPT the current one."""
    current_jti = None
    try:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            from jose import jwt
            import os
            token = auth.split(" ", 1)[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
            current_jti = payload.get("jti")
    except Exception:
        pass
    query = {"user_id": current_user["id"], "revoked": {"$ne": True}}
    if current_jti:
        query["jti"] = {"$ne": current_jti}
    result = await db.sessions.update_many(query, {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat()}})
    return {"revoked": result.modified_count}



@router.post("/auth/sales-portal-login")
async def sales_portal_login(data: dict, request: Request) -> dict:
    """Login for sales portal devices — uses last name + PIN.

    iter371: the PIN is looked up by its HMAC digest (iter353 removed the
    cleartext `pin` field, which this route was still querying, so POS sign-in
    was impossible). The last name is escaped before it reaches the regex, and
    both failure modes return the same 401 so the endpoint cannot be used to
    discover who works here.
    """
    import re as _re
    last_name = (data.get("last_name") or "").strip()
    pin = (data.get("pin") or "").strip()
    if not last_name or not pin:
        raise HTTPException(status_code=400, detail="Last name and PIN required")
    await enforce_public_rate_limit(request, "sales_portal_login", limit=10, window_minutes=10)
    invalid = HTTPException(status_code=401, detail="Invalid last name or PIN")
    user = await db.users.find_one({
        "name": {"$regex": f"\\b{_re.escape(last_name)}$", "$options": "i"},
        **pin_query(pin),
        "status": "active",
    }, {"_id": 0, "password_hash": 0})
    if not user or not pin_matches(pin, user):
        raise invalid
    token = create_token(user["id"])
    return {"token": token, "name": user.get("name", ""), "id": user["id"], "role": user.get("role", "")}



@router.post("/auth/google-session")
async def google_auth_session(data: dict, request: Request) -> dict:
    import httpx
    session_id = data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
                timeout=10.0,
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google session")
        google_data = resp.json()
        email = google_data.get("email", "").lower()
        name = google_data.get("name", "")
        picture = google_data.get("picture", "")
        if not email:
            raise HTTPException(status_code=400, detail="No email from Google")
        # iter396 — find the account the way password sign-in does. The scoped
        # db only sees the organisation this hostname belongs to, so an existing
        # person signing in on the shared address used to come back as "not
        # found" and get a brand-new pending guest account instead — which is
        # exactly what bounced them to the login page.
        host_org = await org_for_hostname(request)
        with org_bypass():
            candidates = await raw_db.users.find(
                {"email": email}, {"_id": 0, "password_hash": 0}
            ).to_list(20)
        if host_org:
            candidates = [c for c in candidates
                          if c.get("organization_id") == host_org["id"] or is_super_admin(c)]
        if len(candidates) > 1:
            # The same address exists in more than one organisation. A Google
            # session can only be exchanged once, so there is no safe way to ask
            # "which one" mid-flow — send them to the right front door instead.
            with org_bypass():
                orgs = await raw_db.organizations.find(
                    {"id": {"$in": [c.get("organization_id") for c in candidates]}},
                    {"_id": 0, "name": 1},
                ).to_list(20)
            names = ", ".join(o.get("name", "") for o in orgs if o.get("name"))
            raise HTTPException(
                status_code=409,
                detail=(f"{email} is used in more than one organisation ({names}). "
                        "Open that organisation's own web address to sign in, or use your password."),
            )
        existing = candidates[0] if candidates else None
        if existing:
            user_id = existing["id"]
            if existing.get("status") == "suspended":
                raise HTTPException(status_code=403, detail="Account suspended. Contact an administrator.")
            org_id, org, pending = await _resolve_login_org(existing, host_org)
            if pending:
                return pending
            set_current_org(org_id)
            if picture and not existing.get("picture"):
                await db.users.update_one({"id": user_id}, {"$set": {"picture": picture}})
        else:
            user_id = str(uuid.uuid4())
            new_user = {
                "id": user_id, "name": name, "email": email,
                "phone": None, "national_id": None,
                "password_hash": hash_password(str(uuid.uuid4())),
                "role": "Guest", "status": "pending", "picture": picture,
                "is_guest": True, "is_parent": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.users.insert_one(new_user)
            # Also create a guest record
            await db.guests.insert_one({
                "id": f"gst_{uuid.uuid4().hex[:8]}", "name": name, "email": email,
                "user_id": user_id, "is_parent": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        # Pending users get a restricted token — frontend must check status
        if user.get("status") == "pending":
            token = create_token(user_id)
            return {"token": token, "user": user, "pending_approval": True}
        token = create_token(user_id)
        return {"token": token, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth error: {e}")
        raise HTTPException(status_code=500, detail="Google authentication failed")


@router.post("/auth/forgot-password")
async def forgot_password(data: dict) -> dict:
    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    user = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "name": 1})
    if not user:
        return {"message": "If an account exists with that email, a reset link has been sent."}
    reset_token = str(uuid.uuid4())
    await db.password_resets.insert_one({
        "token": reset_token,
        "user_id": user["id"],
        "email": email,
        "used": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    try:
        from routers.notifications import send_email
        await send_email(
            email,
            "58:12 Global — Password Reset",
            f"""<h2>Password Reset Request</h2>
            <p>Hi {user.get('name', '')},</p>
            <p>Use this code to reset your password: <strong>{reset_token[:8].upper()}</strong></p>
            <p>This code expires in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
            <p>— 58:12 Global Connect</p>"""
        )
    except Exception as e:
        logger.warning(f"Failed to send reset email: {e}")
    return {"message": "If an account exists with that email, a reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password(data: dict) -> dict:
    token = (data.get("token") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    reset = await db.password_resets.find_one({
        "used": False,
        "$or": [
            {"token": token},
            {"token": {"$regex": f"^{token.lower()[:8]}", "$options": "i"}}
        ]
    }, {"_id": 0})
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    if reset.get("expires_at") and reset["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=400, detail="Reset code has expired")
    await db.users.update_one(
        {"id": reset["user_id"]},
        {"$set": {"password_hash": hash_password(new_password)}}
    )
    await db.password_resets.update_one({"token": reset["token"]}, {"$set": {"used": True}})
    return {"message": "Password reset successfully. You can now login with your new password."}


@router.post("/auth/change-password")
async def change_password(data: dict, current_user: dict = Depends(get_current_user)) -> dict:
    """Authenticated self-service password change.

    Body: { current_password, new_password }
    Requires the caller to prove they know the existing password — defends
    against session-hijacking and shoulder-surfing scenarios. Both `users`
    AND `members` tables are updated when the account is linked, so the
    next login (which may resolve via either record) still works.
    """
    current_password = (data.get("current_password") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Both current and new password are required")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if current_password == new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    user = await db.users.find_one({"id": current_user["id"]}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=404, detail="User record not found")
    if not verify_password(current_password, user["password_hash"]):
        # Tiny tarpit so brute-force is unattractive — same pattern as /auth/login
        import asyncio
        await asyncio.sleep(0.4)
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = hash_password(new_password)
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {
            "password_hash": new_hash,
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    # Mirror into the member record when the account is linked — login can
    # resolve via either collection.
    if current_user.get("member_id"):
        await db.members.update_one(
            {"id": current_user["member_id"]},
            {"$set": {"password_hash": new_hash}},
        )
    try:
        await _audit(current_user["id"], "update", "password_change", current_user["id"], {"self_service": True})
    except Exception:
        pass
    return {"message": "Password changed successfully."}
