"""Google sign-in.

iter393 — the previous `POST /api/auth/google` accepted a raw Google ID token
and, whenever `emergentintegrations.llm.google_auth` was unavailable (it always
was), fell back to base64-decoding the token payload WITHOUT verifying its
signature. Anyone could forge `{"email": "<an admin>"}` and receive a valid
session. Nothing in the frontend used the route.

Google sign-in now goes exclusively through `POST /api/auth/google-session` in
routers/auth.py, which exchanges the one-time session_id with Emergent's auth
service server-side and therefore cannot be forged. This module intentionally
registers no routes.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api")
