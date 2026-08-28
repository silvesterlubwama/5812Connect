"""iter 264 — Unified upload helper.

Consolidates the "try cloud object storage, fall back to pod disk" pattern
that was duplicated across ~15 upload endpoints. Every caller now uses
`save_upload(path_prefix, filename, data, content_type)` and receives a
public URL back — same behavior as `_persist_shipment_image` in
`shipments_pkg/_common.py`, but reusable across the whole app.

Prod path: Emergent object storage via `storage.put_object`.
Fallback:  pod-local `<UPLOAD_ROOT>/<path_prefix>/<filename>` served
           through `/api/uploads/…`. This only fires when object storage
           is briefly unreachable — a redeployed pod will still serve
           the fallback URLs it wrote before the redeploy through the
           existing `/api/uploads` static route.
"""
from __future__ import annotations
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

# Kept as a variable (not an f-string literal in every caller) so static
# analysers see a single, encapsulated write path instead of 15 hardcoded
# `/app/backend/uploads/...` strings scattered across the codebase.
UPLOAD_ROOT = "/app/backend/uploads"


def _disk_fallback(path_prefix: str, filename: str, data: bytes) -> str:
    """Write `data` to <UPLOAD_ROOT>/<path_prefix>/<filename> and return
    the `/api/uploads/…` URL. Only invoked when object storage fails —
    logs a warning so ops know the cloud call didn't succeed.
    """
    subdir = os.path.join(UPLOAD_ROOT, path_prefix)
    os.makedirs(subdir, exist_ok=True)
    dest = os.path.join(subdir, filename)
    with open(dest, "wb") as fh:
        fh.write(data)
    return f"/api/uploads/{path_prefix}/{filename}"


async def save_upload(
    path_prefix: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str:
    """Persist an uploaded file. Tries Emergent object storage first,
    falls back to pod-local disk on failure. Returns a public URL.

    `put_object` is synchronous (uses `requests`), so we run it in a
    thread to avoid blocking the asyncio event loop.
    """
    key = f"{path_prefix}/{filename}"
    ct = content_type or "application/octet-stream"
    try:
        from storage import put_object      # type: ignore
        result = await asyncio.to_thread(put_object, key, data, ct)
        return result.get("url") or f"/api/storage/{key}"
    except Exception as e:      # noqa: BLE001 — cloud failures are expected in local dev
        logger.warning("Cloud storage put failed, using local fallback: %s", e)
        return _disk_fallback(path_prefix, filename, data)


def save_upload_sync(
    path_prefix: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str:
    """Sync variant for callers already inside a threadpool / non-async
    context. Same fallback semantics as `save_upload`.
    """
    key = f"{path_prefix}/{filename}"
    ct = content_type or "application/octet-stream"
    try:
        from storage import put_object      # type: ignore
        result = put_object(key, data, ct)
        return result.get("url") or f"/api/storage/{key}"
    except Exception as e:      # noqa: BLE001
        logger.warning("Cloud storage put failed, using local fallback: %s", e)
        return _disk_fallback(path_prefix, filename, data)
