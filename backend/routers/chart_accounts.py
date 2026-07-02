"""Chart-of-actual cash accounts (cash drawer / bank / mobile money / etc).

Distinct from `financial_accounts` — those are per-sublocation aggregation
buckets. `chart_accounts` are the real-world tills, wallets, and bank accounts
that hold actual money. Any user can only pull from an account they've been
explicitly assigned to (admins bypass this)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import time
import uuid

from deps import (
    db, get_current_user, require_admin, require_manager, _audit,
    is_system_admin, get_campus_filter,
)

router = APIRouter(prefix="/api/financial/chart-accounts", tags=["chart-accounts"])


# In-process TTL cache for balance deltas (iter208). Keeps hot list views snappy
# without introducing Redis. TTL is intentionally short so writes don't create
# stale reads for long. Cache is invalidated explicitly on any write path that
# mutates donations/expenses/sales/transfers.
_BAL_CACHE: dict = {}   # {account_id: (expiry_epoch, delta)}
_BAL_TTL_SECONDS = 5


def _cache_get(ids: list) -> dict:
    """Return {aid: delta} for whichever ids are still hot in cache."""
    now = time.time()
    hits = {}
    stale = []
    for aid in ids:
        entry = _BAL_CACHE.get(aid)
        if entry and entry[0] > now:
            hits[aid] = entry[1]
        elif entry:
            stale.append(aid)
    for aid in stale:
        _BAL_CACHE.pop(aid, None)
    return hits


def _cache_set(deltas: dict) -> None:
    expiry = time.time() + _BAL_TTL_SECONDS
    for aid, val in deltas.items():
        _BAL_CACHE[aid] = (expiry, val)


def invalidate_balance_cache(account_ids: Optional[list] = None) -> None:
    """Drop cached balances. Callers that write donations/expenses/sales/transfers
    must invoke this for the affected account_id so the next read is fresh."""
    if account_ids is None:
        _BAL_CACHE.clear()
        return
    for aid in account_ids:
        if aid:
            _BAL_CACHE.pop(aid, None)


ACCOUNT_KINDS = {"cash", "bank", "mobile_money", "credit", "petty_cash", "other"}


class ChartAccountCreate(BaseModel):
    name: str
    kind: str = "cash"
    currency: str = "UGX"
    starting_balance: float = 0
    location_id: Optional[str] = None  # sub-location or campus, or blank for org-wide
    campus_id: Optional[str] = None
    assigned_user_ids: List[str] = []
    notes: str = ""


class ChartAccountUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    currency: Optional[str] = None
    starting_balance: Optional[float] = None
    location_id: Optional[str] = None
    campus_id: Optional[str] = None
    assigned_user_ids: Optional[List[str]] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


def _user_can_admin_accounts(user: dict) -> bool:
    if is_system_admin(user):
        return True
    role = (user.get("role") or "").lower()
    return role in {"admin", "system_admin", "executive director", "director"}


async def _compute_balance(account_id: str, starting_balance: float = 0) -> float:
    """Compute live balance for an account:
    starting + Σ inflows − Σ outflows (donations, expenses, sales, transfers)."""
    balances = await _batch_compute_balances([account_id])
    starting = float(starting_balance or 0)
    return round(starting + balances.get(account_id, 0), 2)


async def _batch_compute_balances(account_ids: list) -> dict:
    """Batch-compute the DELTA (excluding starting_balance) for a list of account IDs
    in a small, fixed number of aggregation round-trips (5 total, regardless of N).
    Returns {account_id: delta}. Callers add starting_balance themselves.

    Uses an in-process TTL cache (iter208) — the same list view rendering under
    a burst of requests only pays the 5 aggregations once per _BAL_TTL_SECONDS."""
    if not account_ids:
        return {}
    ids = list(set(account_ids))  # dedupe
    # Fast path: fully cached
    hits = _cache_get(ids)
    misses = [aid for aid in ids if aid not in hits]
    if not misses:
        return {aid: hits[aid] for aid in ids}
    delta = {aid: 0.0 for aid in misses}
    # Donation inflows
    async for r in db.donations.aggregate([
        {"$match": {"deposit_to_account_id": {"$in": misses}}},
        {"$group": {"_id": "$deposit_to_account_id", "total": {"$sum": "$amount"}}},
    ]):
        delta[r["_id"]] = delta.get(r["_id"], 0) + (r.get("total") or 0)
    # Sales inflows (non-voided)
    async for r in db.sales.aggregate([
        {"$match": {"deposit_to_account_id": {"$in": misses}, "voided": {"$ne": True}}},
        {"$group": {"_id": "$deposit_to_account_id", "total": {"$sum": "$total"}}},
    ]):
        delta[r["_id"]] = delta.get(r["_id"], 0) + (r.get("total") or 0)
    # Expense outflows (approved/legacy only)
    async for r in db.expenses.aggregate([
        {"$match": {"paid_from_account_id": {"$in": misses}, "status": {"$in": ["approved", None]}}},
        {"$group": {"_id": "$paid_from_account_id", "total": {"$sum": "$amount"}}},
    ]):
        delta[r["_id"]] = delta.get(r["_id"], 0) - (r.get("total") or 0)
    # Transfer in
    async for r in db.chart_account_transfers.aggregate([
        {"$match": {"to_account_id": {"$in": misses}}},
        {"$group": {"_id": "$to_account_id", "total": {"$sum": "$amount"}}},
    ]):
        delta[r["_id"]] = delta.get(r["_id"], 0) + (r.get("total") or 0)
    # Transfer out
    async for r in db.chart_account_transfers.aggregate([
        {"$match": {"from_account_id": {"$in": misses}}},
        {"$group": {"_id": "$from_account_id", "total": {"$sum": "$amount"}}},
    ]):
        delta[r["_id"]] = delta.get(r["_id"], 0) - (r.get("total") or 0)
    # Persist to cache and merge with earlier hits
    _cache_set(delta)
    merged = {**hits, **delta}
    return {aid: merged.get(aid, 0.0) for aid in ids}


async def _load_account_or_404(account_id: str) -> dict:
    acct = await db.chart_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acct:
        raise HTTPException(status_code=404, detail="Chart account not found")
    return acct


async def user_can_use_account(user: dict, account_id: str) -> bool:
    """Non-admins can only use accounts they're assigned to. Admins bypass."""
    if _user_can_admin_accounts(user):
        return True
    acct = await db.chart_accounts.find_one({"id": account_id}, {"_id": 0, "assigned_user_ids": 1})
    if not acct:
        return False
    return user["id"] in (acct.get("assigned_user_ids") or [])


# ========== LIST + MY ACCOUNTS ==========

@router.get("")
async def list_chart_accounts(
    include_balance: bool = True,
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
):
    """Admins see all; regular users see only accounts they're assigned to."""
    q = {}
    if active_only:
        q["active"] = {"$ne": False}
    if not _user_can_admin_accounts(current_user):
        q["assigned_user_ids"] = current_user["id"]
    accounts = await db.chart_accounts.find(q, {"_id": 0}).sort("name", 1).to_list(200)
    if include_balance and accounts:
        ids = [a["id"] for a in accounts]
        deltas = await _batch_compute_balances(ids)
        for a in accounts:
            a["balance"] = round(float(a.get("starting_balance", 0) or 0) + deltas.get(a["id"], 0), 2)
    return accounts


@router.get("/mine")
async def my_chart_accounts(current_user: dict = Depends(get_current_user)):
    """Accounts the current user can pull from — always with live balance."""
    q = {"active": {"$ne": False}}
    if not _user_can_admin_accounts(current_user):
        q["assigned_user_ids"] = current_user["id"]
    accounts = await db.chart_accounts.find(q, {"_id": 0}).sort("name", 1).to_list(200)
    if accounts:
        ids = [a["id"] for a in accounts]
        deltas = await _batch_compute_balances(ids)
        for a in accounts:
            a["balance"] = round(float(a.get("starting_balance", 0) or 0) + deltas.get(a["id"], 0), 2)
    return accounts


# ========== CRUD ==========

@router.post("")
async def create_chart_account(data: ChartAccountCreate, current_user: dict = Depends(require_admin)):
    if data.kind not in ACCOUNT_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(ACCOUNT_KINDS)}")
    doc = {
        "id": f"cha_{uuid.uuid4().hex[:10]}",
        "name": data.name.strip(),
        "kind": data.kind,
        "currency": data.currency,
        "starting_balance": float(data.starting_balance or 0),
        "location_id": data.location_id or "",
        "campus_id": data.campus_id or current_user.get("active_campus_id") or "",
        "assigned_user_ids": list(dict.fromkeys(data.assigned_user_ids or [])),
        "notes": data.notes or "",
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.chart_accounts.insert_one(doc)
    doc.pop("_id", None)
    doc["balance"] = doc["starting_balance"]
    await _audit(current_user["id"], "create", "chart_account", doc["id"])
    return doc


@router.put("/{account_id}")
async def update_chart_account(account_id: str, data: ChartAccountUpdate, current_user: dict = Depends(require_admin)):
    await _load_account_or_404(account_id)
    update = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None or k == "notes"}
    if "kind" in update and update["kind"] not in ACCOUNT_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(ACCOUNT_KINDS)}")
    if "assigned_user_ids" in update:
        update["assigned_user_ids"] = list(dict.fromkeys(update["assigned_user_ids"] or []))
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = current_user["id"]
    await db.chart_accounts.update_one({"id": account_id}, {"$set": update})
    await _audit(current_user["id"], "update", "chart_account", account_id)
    fresh = await db.chart_accounts.find_one({"id": account_id}, {"_id": 0})
    fresh["balance"] = await _compute_balance(account_id, fresh.get("starting_balance", 0))
    return fresh


@router.put("/{account_id}/assignees")
async def set_account_assignees(account_id: str, data: dict, current_user: dict = Depends(require_admin)):
    """Set the list of user IDs allowed to spend from this account."""
    await _load_account_or_404(account_id)
    user_ids = list(dict.fromkeys(data.get("user_ids") or []))
    await db.chart_accounts.update_one({"id": account_id}, {"$set": {
        "assigned_user_ids": user_ids,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": current_user["id"],
    }})
    await _audit(current_user["id"], "update", "chart_account_assignees", account_id, {"count": len(user_ids)})
    return {"account_id": account_id, "assigned_user_ids": user_ids}


@router.delete("/{account_id}")
async def delete_chart_account(account_id: str, current_user: dict = Depends(require_admin)):
    """Soft-delete by default (active=false). Pass ?hard=true for hard delete (only if no txns)."""
    await _load_account_or_404(account_id)
    # Check if any transactions reference it
    exp_count = await db.expenses.count_documents({"paid_from_account_id": account_id})
    don_count = await db.donations.count_documents({"deposit_to_account_id": account_id})
    sale_count = await db.sales.count_documents({"deposit_to_account_id": account_id})
    if exp_count + don_count + sale_count > 0:
        # Soft-delete only
        await db.chart_accounts.update_one({"id": account_id}, {"$set": {
            "active": False,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": current_user["id"],
        }})
        await _audit(current_user["id"], "archive", "chart_account", account_id)
        return {"archived": True, "referenced_txns": exp_count + don_count + sale_count}
    await db.chart_accounts.delete_one({"id": account_id})
    await _audit(current_user["id"], "delete", "chart_account", account_id)
    return {"deleted": True}


# ========== BALANCE + TRANSACTIONS ==========

@router.get("/{account_id}")
async def get_chart_account(account_id: str, current_user: dict = Depends(get_current_user)):
    acct = await _load_account_or_404(account_id)
    # Non-admins can only see accounts they're assigned to
    if not _user_can_admin_accounts(current_user):
        if current_user["id"] not in (acct.get("assigned_user_ids") or []):
            raise HTTPException(status_code=403, detail="You are not assigned to this account")
    acct["balance"] = await _compute_balance(account_id, acct.get("starting_balance", 0))
    return acct


@router.get("/{account_id}/transactions")
async def account_transactions(account_id: str, limit: int = 200, current_user: dict = Depends(get_current_user)):
    """Ledger for a single account — donations in, expenses out, sales in, transfers.
    Only accessible to admins or the account's assigned users."""
    acct = await _load_account_or_404(account_id)
    if not _user_can_admin_accounts(current_user):
        if current_user["id"] not in (acct.get("assigned_user_ids") or []):
            raise HTTPException(status_code=403, detail="You are not assigned to this account")
    txns = []
    async for d in db.donations.find({"deposit_to_account_id": account_id}, {"_id": 0}).sort("date", -1).limit(limit):
        txns.append({
            "id": d["id"], "date": d.get("date"), "type": "donation",
            "direction": "in", "amount": d.get("amount", 0), "currency": d.get("currency", "UGX"),
            "party": d.get("donor_name", ""), "notes": d.get("notes", ""),
            "ref": d.get("id"),
        })
    async for e in db.expenses.find({"paid_from_account_id": account_id, "status": {"$in": ["approved", None]}}, {"_id": 0}).sort("date", -1).limit(limit):
        txns.append({
            "id": e["id"], "date": e.get("date"), "type": "expense",
            "direction": "out", "amount": e.get("amount", 0), "currency": e.get("currency", "UGX"),
            "party": e.get("vendor") or e.get("title", ""), "notes": e.get("notes", ""),
            "ref": e.get("id"),
        })
    async for s in db.sales.find({"deposit_to_account_id": account_id, "voided": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(limit):
        txns.append({
            "id": s["id"], "date": (s.get("created_at") or "")[:10], "type": "sale",
            "direction": "in", "amount": s.get("total", 0), "currency": s.get("currency", "UGX"),
            "party": s.get("customer_name", "Walk-in"), "notes": s.get("receipt_number", ""),
            "ref": s.get("id"),
        })
    async for t in db.chart_account_transfers.find({"$or": [{"from_account_id": account_id}, {"to_account_id": account_id}]}, {"_id": 0}).sort("date", -1).limit(limit):
        direction = "in" if t.get("to_account_id") == account_id else "out"
        other = t.get("from_account_id") if direction == "in" else t.get("to_account_id")
        txns.append({
            "id": t["id"], "date": t.get("date"), "type": "transfer",
            "direction": direction, "amount": t.get("amount", 0), "currency": t.get("currency", "UGX"),
            "party": f"Transfer {'from' if direction == 'in' else 'to'} account {other}",
            "notes": t.get("notes", ""), "ref": t.get("id"),
        })
    # Sort newest first
    txns.sort(key=lambda x: (x.get("date") or ""), reverse=True)
    return {
        "account_id": account_id,
        "account_name": acct.get("name"),
        "starting_balance": acct.get("starting_balance", 0),
        "balance": await _compute_balance(account_id, acct.get("starting_balance", 0)),
        "transactions": txns[:limit],
    }


# ========== TRANSFERS BETWEEN CHART ACCOUNTS ==========

@router.post("/transfer")
async def transfer_between_accounts(data: dict, current_user: dict = Depends(require_manager)):
    """Move funds between two chart accounts. Only admins/managers can initiate."""
    from_id = data.get("from_account_id")
    to_id = data.get("to_account_id")
    amount = float(data.get("amount") or 0)
    if not from_id or not to_id:
        raise HTTPException(status_code=400, detail="from_account_id and to_account_id required")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    from_acct = await _load_account_or_404(from_id)
    to_acct = await _load_account_or_404(to_id)
    # Check assigned access for non-admins on the source account
    if not _user_can_admin_accounts(current_user):
        if current_user["id"] not in (from_acct.get("assigned_user_ids") or []):
            raise HTTPException(status_code=403, detail="You are not assigned to the source account")
    # Insufficient funds guard (soft — allowed but flagged)
    from_balance = await _compute_balance(from_id, from_acct.get("starting_balance", 0))
    if from_balance < amount:
        raise HTTPException(status_code=400, detail=f"Insufficient balance ({from_acct.get('currency','UGX')} {from_balance:,.2f})")
    doc = {
        "id": f"chtx_{uuid.uuid4().hex[:10]}",
        "from_account_id": from_id,
        "from_name": from_acct.get("name"),
        "to_account_id": to_id,
        "to_name": to_acct.get("name"),
        "amount": amount,
        "currency": data.get("currency") or from_acct.get("currency", "UGX"),
        "date": data.get("date") or datetime.now(timezone.utc).isoformat()[:10],
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
    }
    await db.chart_account_transfers.insert_one(doc)
    doc.pop("_id", None)
    invalidate_balance_cache([from_id, to_id])  # both sides changed — bust cache
    await _audit(current_user["id"], "create", "chart_account_transfer", doc["id"], {"amount": amount, "from": from_id, "to": to_id})
    return doc


@router.get("/transfers/list")
async def list_transfers(limit: int = 100, current_user: dict = Depends(get_current_user)):
    """List recent chart-account transfers. Non-admins see only transfers touching accounts they're assigned to."""
    if _user_can_admin_accounts(current_user):
        q = {}
    else:
        mine = await db.chart_accounts.find({"assigned_user_ids": current_user["id"]}, {"_id": 0, "id": 1}).to_list(200)
        mine_ids = [m["id"] for m in mine]
        q = {"$or": [{"from_account_id": {"$in": mine_ids}}, {"to_account_id": {"$in": mine_ids}}]}
    txns = await db.chart_account_transfers.find(q, {"_id": 0}).sort("date", -1).limit(limit).to_list(limit)
    return txns
