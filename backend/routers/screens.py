"""Screens on the wall: the kitchen's ticket board and the customer's display.

A screen is a device, not a person. A cook should not have to find a password
to see what to cook, and a customer-facing display has no business holding a
staff session at all. So a manager at the store pairs the device once; the
link it gets back IS the credential, and it only ever shows that store's
kitchen or that till's running total (iter420).

The pairing link is created by someone signed in to that store, can be
revoked, and gives no access to anything else in the app.
"""
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pymongo import ReturnDocument

from deps import db, require_manager, require_staff
from routers.kitchen import STAGES, STAGE_LABELS, _roll_up, _next_stage
from store_access import is_store_member

router = APIRouter(prefix="/api", tags=["screens"])

KINDS = {"kitchen": "Kitchen screen", "sales": "Customer display", "bridge": "Shop print helper"}

# A queued receipt is worthless an hour later, and a helper that died mid-job
# must not hold onto it forever (iter422).
JOB_TTL_SECONDS = 600
CLAIM_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 3
HELPER_ALIVE_SECONDS = 120          # it polls every 2s, so this is generous


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScreenCreate(BaseModel):
    kind: str
    location_id: str
    name: Optional[str] = ""
    till_id: Optional[str] = "main"


class LiveSale(BaseModel):
    location_id: str
    till_id: Optional[str] = "main"
    lines: list = []
    subtotal: float = 0
    discount: float = 0
    total: float = 0
    currency: Optional[str] = "UGX"
    state: str = "selling"              # selling | paid | idle
    customer_name: Optional[str] = ""
    change_due: Optional[float] = None
    receipt_number: Optional[str] = ""
    store_name: Optional[str] = ""
    cashier: Optional[str] = ""
    model_config = {"extra": "allow"}


def _key(location_id: str, till_id: Optional[str]) -> str:
    return f"{location_id}|{(till_id or 'main').strip() or 'main'}"


async def _screen(token: str) -> dict:
    row = await db.device_screens.find_one({"token": token, "revoked": {"$ne": True}}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="This screen link is not valid any more — ask for a new one")
    await db.device_screens.update_one({"token": token}, {"$set": {"last_seen_at": _now()}})
    return row


# ============================ PAIRING (staff) ============================

@router.get("/screens")
async def list_screens(location_id: Optional[str] = None,
                       current_user: dict = Depends(require_staff)):
    store = location_id or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if store and not await is_store_member(current_user, store):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    query = {"revoked": {"$ne": True}}
    if store:
        query["location_id"] = store
    return await db.device_screens.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/screens")
async def pair_screen(data: ScreenCreate, current_user: dict = Depends(require_manager)):
    if data.kind not in KINDS:
        raise HTTPException(status_code=400, detail="A screen is either a kitchen screen or a customer display")
    if not data.location_id:
        raise HTTPException(status_code=400, detail="Which store is this screen in?")
    if not await is_store_member(current_user, data.location_id):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    doc = {
        "id": f"scr_{uuid.uuid4().hex[:10]}",
        "token": secrets.token_urlsafe(12),
        "kind": data.kind,
        "location_id": data.location_id,
        "till_id": (data.till_id or "main").strip() or "main",
        "name": (data.name or "").strip()[:80] or KINDS[data.kind],
        "revoked": False,
        "created_at": _now(),
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", ""),
    }
    await db.device_screens.insert_one(dict(doc))
    return {"message": f"{doc['name']} paired — open the link on that screen once and leave it there",
            "screen": doc}


@router.delete("/screens/{screen_id}")
async def revoke_screen(screen_id: str, current_user: dict = Depends(require_manager)):
    row = await db.device_screens.find_one({"id": screen_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Screen not found")
    if not await is_store_member(current_user, row.get("location_id") or ""):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    await db.device_screens.update_one({"id": screen_id}, {"$set": {
        "revoked": True, "revoked_at": _now(), "revoked_by": current_user.get("name", "")}})
    return {"message": f"{row.get('name')} unpaired — that link no longer opens", "id": screen_id}


# ======================= THE TILL PUSHES (staff) =======================

@router.post("/screens/live-sale")
async def push_live_sale(data: LiveSale, current_user: dict = Depends(require_staff)):
    """What the customer is watching: the basket as it is being rung up."""
    if not data.location_id:
        raise HTTPException(status_code=400, detail="Which till is this?")
    if not await is_store_member(current_user, data.location_id):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    doc = data.model_dump()
    doc["key"] = _key(data.location_id, data.till_id)
    doc["updated_at"] = _now()
    await db.live_sales.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    return {"ok": True, "key": doc["key"]}


# ====================== THE SCREEN READS (no login) ======================

@router.get("/screens/{token}")
async def screen_info(token: str):
    row = await _screen(token)
    loc = await db.locations.find_one({"id": row.get("location_id")}, {"_id": 0, "name": 1})
    settings = await db.store_settings.find_one({"location_id": row.get("location_id")},
                                                {"_id": 0, "store_name": 1, "currency": 1})
    return {
        "kind": row["kind"], "name": row.get("name"), "till_id": row.get("till_id"),
        "location_id": row.get("location_id"),
        "store_name": (settings or {}).get("store_name") or (loc or {}).get("name") or "",
        "currency": (settings or {}).get("currency") or "UGX",
    }


@router.get("/screens/{token}/orders")
async def screen_orders(token: str, limit: int = 60):
    """The kitchen board. Read-only to anyone without the link."""
    row = await _screen(token)
    if row["kind"] != "kitchen":
        raise HTTPException(status_code=400, detail="This screen is a customer display, not a kitchen screen")
    orders = await db.kitchen_orders.find(
        {"location_id": row["location_id"], "cancelled": {"$ne": True}, "status": {"$ne": "served"}},
        {"_id": 0}).sort("created_at", 1).limit(limit).to_list(limit)
    for order in orders:
        order["total"] = round(sum(float(i.get("price") or 0) * float(i.get("qty") or 0)
                                   for i in (order.get("items") or []) if not i.get("cancelled")), 2)
    return orders


@router.patch("/screens/{token}/orders/{order_id}/items/{line_id}")
async def screen_advance_item(token: str, order_id: str, line_id: str, data: dict = None):
    """A cook taps a dish as it comes up. The link is the kitchen's credential."""
    row = await _screen(token)
    if row["kind"] != "kitchen":
        raise HTTPException(status_code=400, detail="This screen cannot change tickets")
    order = await db.kitchen_orders.find_one({"id": order_id, "location_id": row["location_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="That ticket is not on this screen")
    items = order.get("items") or []
    item = next((i for i in items if i.get("line_id") == line_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="That dish is not on this ticket")
    status = (data or {}).get("status") or _next_stage(item.get("status") or "new")
    if status not in STAGES:
        raise HTTPException(status_code=400, detail="Unknown stage")
    now = _now()
    item["status"] = status
    item.setdefault("status_at", {})[status] = now
    rolled = _roll_up(items)
    await db.kitchen_orders.update_one({"id": order_id}, {"$set": {
        "items": items, "status": rolled, "updated_at": now}})
    return {"message": f"{item.get('name')} — {STAGE_LABELS[status]}", "status": status,
            "order_status": rolled}


@router.patch("/screens/{token}/orders/{order_id}")
async def screen_advance_order(token: str, order_id: str, data: dict = None):
    row = await _screen(token)
    if row["kind"] != "kitchen":
        raise HTTPException(status_code=400, detail="This screen cannot change tickets")
    order = await db.kitchen_orders.find_one({"id": order_id, "location_id": row["location_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="That ticket is not on this screen")
    status = (data or {}).get("status") or _next_stage(order.get("status") or "new")
    if status not in STAGES:
        raise HTTPException(status_code=400, detail="Unknown stage")
    now = _now()
    items = order.get("items") or []
    for item in items:
        if item.get("cancelled"):
            continue
        item["status"] = status
        item.setdefault("status_at", {})[status] = now
    await db.kitchen_orders.update_one({"id": order_id}, {"$set": {
        "items": items, "status": status, "updated_at": now, f"status_at.{status}": now}})
    return {"message": f"Ticket {order.get('ticket_number')} — {STAGE_LABELS[status]}", "status": status}


@router.get("/screens/{token}/sale")
async def screen_sale(token: str):
    """The customer display: what has been scanned and what it comes to."""
    row = await _screen(token)
    if row["kind"] != "sales":
        raise HTTPException(status_code=400, detail="This screen is a kitchen screen, not a customer display")
    live = await db.live_sales.find_one({"key": _key(row["location_id"], row.get("till_id"))}, {"_id": 0})
    if not live:
        return {"state": "idle", "lines": [], "total": 0, "currency": "UGX"}
    return live


# ===================== THE SHOP'S PRINT HELPER (iter422) =====================
# A receipt printer with its own IP lives on the shop's network, which a server
# in the cloud cannot see. So the till hands the receipt to the server, and a
# small helper running on any computer or Pi at the shop collects it and walks
# it over to the printer. The helper holds a bridge token, nothing else.

class PrintJob(BaseModel):
    location_id: str
    host: str
    port: int = 9100
    data_b64: str
    title: Optional[str] = "Receipt"
    printer: Optional[str] = "receipt"       # receipt | kitchen


@router.post("/print-jobs")
async def queue_print_job(data: PrintJob, current_user: dict = Depends(require_staff)):
    if not await is_store_member(current_user, data.location_id):
        raise HTTPException(status_code=403, detail="You are not signed in to this store")
    if not data.host:
        raise HTTPException(status_code=400, detail="No printer address")
    if len(data.data_b64) > 2_000_000:
        raise HTTPException(status_code=413, detail="That print job is too big")
    helper = await db.device_screens.find_one(
        {"location_id": data.location_id, "kind": "bridge", "revoked": {"$ne": True}},
        {"_id": 0, "last_seen_at": 1, "name": 1})
    # Queue only for a helper that is actually alive. Handing a receipt to a
    # helper that has gone home means it prints when the machine next boots —
    # and the till has already printed it elsewhere in the meantime (iter422).
    seen = (helper or {}).get("last_seen_at") or ""
    alive = bool(seen) and seen > (datetime.now(timezone.utc) - timedelta(seconds=HELPER_ALIVE_SECONDS)).isoformat()
    if not helper:
        raise HTTPException(status_code=409, detail="No print helper is set up at this shop")
    if not alive:
        raise HTTPException(status_code=409, detail=f"{helper.get('name') or 'The print helper'} is not running at the shop right now")
    job = {
        "id": f"job_{uuid.uuid4().hex[:12]}",
        "location_id": data.location_id,
        "host": data.host, "port": int(data.port or 9100),
        "data_b64": data.data_b64,
        "title": (data.title or "Receipt")[:80],
        "printer": data.printer or "receipt",
        "status": "queued",
        "attempts": 0,
        "error": "",
        "created_at": _now(),
        "queued_by": current_user.get("name", ""),
    }
    await db.print_jobs.insert_one(dict(job))
    return {"queued": True, "job_id": job["id"], "helper_paired": bool(helper),
            "helper_last_seen": (helper or {}).get("last_seen_at")}


@router.get("/print-jobs/{job_id}")
async def print_job_status(job_id: str, current_user: dict = Depends(require_staff)):
    """Did it actually print? The till waits a few seconds on this before
    falling back to its own print window."""
    job = await db.print_jobs.find_one({"id": job_id}, {"_id": 0, "data_b64": 0})
    if not job:
        raise HTTPException(status_code=404, detail="That print job is gone")
    if not await is_store_member(current_user, job.get("location_id") or ""):
        raise HTTPException(status_code=403, detail="That print job belongs to another store")
    return job


@router.get("/screens/{token}/print-jobs")
async def claim_print_jobs(token: str, limit: int = 5):
    """The helper asks what needs printing. Claiming is the credential check."""
    row = await _screen(token)
    if row["kind"] != "bridge":
        raise HTTPException(status_code=400, detail="This link is not a print helper")
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(seconds=CLAIM_TIMEOUT_SECONDS)).isoformat()
    # A helper that was unplugged mid-job leaves claims behind; let them out
    # again rather than losing the receipt.
    await db.print_jobs.update_many(
        {"location_id": row["location_id"], "status": "claimed", "claimed_at": {"$lt": stale},
         "attempts": {"$lt": MAX_ATTEMPTS}},
        {"$set": {"status": "queued"}})
    await db.print_jobs.update_many(
        {"location_id": row["location_id"], "status": {"$in": ["queued", "claimed"]},
         "created_at": {"$lt": (now - timedelta(seconds=JOB_TTL_SECONDS)).isoformat()}},
        {"$set": {"status": "expired", "error": "Nobody collected it in time"}})

    out = []
    for _ in range(max(1, min(int(limit or 5), 20))):
        job = await db.print_jobs.find_one_and_update(
            {"location_id": row["location_id"], "status": "queued"},
            {"$set": {"status": "claimed", "claimed_at": _now()}, "$inc": {"attempts": 1}},
            projection={"_id": 0}, sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER)
        if not job:
            break
        out.append(job)
    return out


@router.post("/screens/{token}/print-jobs/{job_id}")
async def finish_print_job(token: str, job_id: str, data: dict = None):
    """The helper says whether the paper actually moved."""
    row = await _screen(token)
    if row["kind"] != "bridge":
        raise HTTPException(status_code=400, detail="This link is not a print helper")
    job = await db.print_jobs.find_one({"id": job_id, "location_id": row["location_id"]}, {"_id": 0, "data_b64": 0})
    if not job:
        raise HTTPException(status_code=404, detail="That print job is not yours")
    ok = bool((data or {}).get("ok"))
    error = str((data or {}).get("error") or "")[:300]
    if ok:
        fields = {"status": "printed", "printed_at": _now(), "error": ""}
    elif job.get("attempts", 0) >= MAX_ATTEMPTS:
        fields = {"status": "failed", "error": error or "The printer did not answer"}
    else:
        # Worth another go: the printer may have been mid-cut or out of paper.
        fields = {"status": "queued", "error": error}
    await db.print_jobs.update_one({"id": job_id}, {"$set": fields})
    return {"message": "Thank you", "status": fields["status"]}


@router.get("/screens/{token}/helper")
async def bridge_script(token: str, format: str = "ps1", base: str = "", request: Request = None):
    """The helper itself, with this shop's address and token already in it.

    `base` is the address the shop's browser is actually using. Behind an
    ingress the server only sees its own internal name, which the helper could
    never reach — so the page that offers the download tells us (iter422).
    """
    row = await _screen(token)
    if row["kind"] != "bridge":
        raise HTTPException(status_code=400, detail="This link is not a print helper")
    origin = ""
    candidate = (base or "").strip().rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", candidate):
        origin = candidate
    if not origin:
        origin = str(request.base_url).rstrip("/") if request else ""
    api = f"{origin}/api"
    if format == "py":
        return PlainTextResponse(_PY_HELPER.replace("__API__", api).replace("__TOKEN__", token),
                                 headers={"Content-Disposition": 'attachment; filename="print-helper.py"'})
    return PlainTextResponse(_PS1_HELPER.replace("__API__", api).replace("__TOKEN__", token),
                             headers={"Content-Disposition": 'attachment; filename="print-helper.ps1"'})


_PS1_HELPER = r"""# 58:12 shop print helper
# Collects receipts from 58:12 and sends them to the printer on this network.
# Leave this window open on any computer at the shop that can reach the printer.
#
#   Right-click this file and choose "Run with PowerShell".
#   If Windows refuses, open PowerShell and run:
#     powershell -ExecutionPolicy Bypass -File .\print-helper.ps1

$Api   = '__API__'
$Token = '__TOKEN__'

Write-Host "58:12 print helper running. Leave this window open." -ForegroundColor Green
Write-Host "Talking to $Api" -ForegroundColor DarkGray

while ($true) {
  try {
    $jobs = Invoke-RestMethod -Uri "$Api/screens/$Token/print-jobs" -Method Get -TimeoutSec 30 `
      -Headers @{ 'User-Agent' = '58-12-print-helper/1.0' }
    foreach ($job in @($jobs)) {
      $ok = $false
      $err = ''
      try {
        $bytes = [Convert]::FromBase64String($job.data_b64)
        $client = New-Object System.Net.Sockets.TcpClient
        $connect = $client.BeginConnect($job.host, [int]$job.port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(5000)) { throw "no answer from $($job.host):$($job.port)" }
        $client.EndConnect($connect)
        $stream = $client.GetStream()
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        Start-Sleep -Milliseconds 400
        $stream.Close(); $client.Close()
        $ok = $true
        Write-Host ("Printed {0} on {1}" -f $job.title, $job.host) -ForegroundColor Green
      } catch {
        $err = $_.Exception.Message
        Write-Host ("Could not print {0}: {1}" -f $job.title, $err) -ForegroundColor Red
      }
      $body = @{ ok = $ok; error = $err } | ConvertTo-Json
      try {
        Invoke-RestMethod -Uri "$Api/screens/$Token/print-jobs/$($job.id)" -Method Post `
          -Body $body -ContentType 'application/json' -TimeoutSec 30 `
          -Headers @{ 'User-Agent' = '58-12-print-helper/1.0' } | Out-Null
      } catch { Write-Host "Could not report back to 58:12" -ForegroundColor DarkYellow }
    }
  } catch {
    Write-Host "Waiting for 58:12..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
  }
  Start-Sleep -Seconds 2
}
"""

_PY_HELPER = r'''#!/usr/bin/env python3
"""58:12 shop print helper.

Collects receipts from 58:12 and sends them to the printer on this network.
Leave it running on any computer or Raspberry Pi at the shop:

    python3 print-helper.py

Nothing to install — it only uses what Python ships with.
"""
import base64
import json
import socket
import time
import urllib.error
import urllib.request

API = "__API__"
TOKEN = "__TOKEN__"


def call(path, payload=None):
    url = f"{API}/screens/{TOKEN}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                headers={"Content-Type": "application/json",
                                         # Python's own user agent gets turned away by the
                                         # firewall in front of 58:12.
                                         "User-Agent": "58-12-print-helper/1.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read() or "null")


def send(job):
    with socket.create_connection((job["host"], int(job.get("port") or 9100)), timeout=5) as sock:
        sock.sendall(base64.b64decode(job["data_b64"]))
        time.sleep(0.4)


print("58:12 print helper running. Leave this window open.")
print(f"Talking to {API}")
while True:
    try:
        for job in call("/print-jobs") or []:
            ok, err = True, ""
            try:
                send(job)
                print(f"Printed {job.get('title')} on {job.get('host')}")
            except Exception as exc:                       # noqa: BLE001 - report anything
                ok, err = False, str(exc)
                print(f"Could not print {job.get('title')}: {err}")
            try:
                call(f"/print-jobs/{job['id']}", {"ok": ok, "error": err})
            except urllib.error.URLError:
                print("Could not report back to 58:12")
    except urllib.error.URLError:
        print("Waiting for 58:12...")
        time.sleep(5)
    time.sleep(2)
'''
