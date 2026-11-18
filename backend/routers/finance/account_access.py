"""Who may touch which account.

By default everyone with finance access can post against any account — that
is how this system has always worked. The moment a director grants a person
an explicit list, that list becomes their whole world: they only see those
accounts (and their balances) and can only post income/expense against them.

No grant row = unrestricted, so switching this on is opt-in per person.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import db, require_staff, require_director, get_role_level

from ._common import _now

router = APIRouter(prefix="/api/finance/account-access", tags=["finance"])

# Directors and above are never restricted — they sign the books.
UNRESTRICTED_LEVEL = 8


def _is_unrestricted(user: dict) -> bool:
    try:
        return get_role_level(user.get("role")) >= UNRESTRICTED_LEVEL
    except Exception:
        return False


async def allowed_account_ids(user: dict) -> Optional[set]:
    """None = no restriction. Otherwise the exact set they may use."""
    if _is_unrestricted(user):
        return None
    grant = await db.finance_account_access.find_one({"user_id": user["id"]}, {"_id": 0})
    if not grant or not grant.get("account_ids"):
        return None
    return set(grant["account_ids"])


async def assert_can_use_account(user: dict, account: dict) -> None:
    """Raise 403 if this person was not given that account to work with."""
    allowed = await allowed_account_ids(user)
    if allowed is None or account.get("id") in allowed:
        return
    raise HTTPException(
        status_code=403,
        detail=f"You have not been given access to '{account.get('name')}' — ask a director to add it to your accounts",
    )


@router.get("/mine")
async def my_accounts(with_balances: bool = True, current_user: dict = Depends(require_staff)):
    """The accounts this person may post against, optionally with balances.

    `with_balances=false` is what entry forms use — a picker should not leak
    what is sitting in the bank to everyone recording a school fee.
    """
    allowed = await allowed_account_ids(current_user)
    q: dict = {"active": True}
    if allowed is not None:
        q["id"] = {"$in": list(allowed)}
    accounts = await db.finance_chart_of_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    out = {"restricted": allowed is not None, "accounts": accounts}
    if with_balances and accounts:
        from .reports import _balances_by_account
        bals = await _balances_by_account(None, None, None)
        for a in accounts:
            row = bals.get(a["id"]) or {}
            a["balance"] = row.get("balance", 0)
            a["debit_total"] = row.get("debit", 0)
            a["credit_total"] = row.get("credit", 0)
    return out


@router.get("/staff")
async def access_candidates(current_user: dict = Depends(require_director)):
    """Everyone a director could pin to specific accounts, with their current grant."""
    users = await db.users.find(
        {"status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    ).sort("name", 1).to_list(1000)
    grants = {g["user_id"]: g.get("account_ids", []) async for g in db.finance_account_access.find({}, {"_id": 0})}
    for u in users:
        u["account_ids"] = grants.get(u["id"], [])
    return users


@router.get("")
async def list_grants(current_user: dict = Depends(require_director)):
    """Everyone who has been pinned to specific accounts."""
    grants = await db.finance_account_access.find({}, {"_id": 0}).to_list(500)
    coa = {a["id"]: a for a in await db.finance_chart_of_accounts.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1}).to_list(500)}
    for g in grants:
        g["accounts"] = [
            {"id": i, "code": coa.get(i, {}).get("code", "?"), "name": coa.get(i, {}).get("name", "(deleted account)")}
            for i in g.get("account_ids", [])
        ]
    return grants


@router.put("/{user_id}")
async def set_grant(user_id: str, data: dict, current_user: dict = Depends(require_director)):
    """Set (or clear, with an empty list) the accounts one person may use."""
    account_ids = [str(i) for i in (data.get("account_ids") or [])]
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if account_ids:
        found = await db.finance_chart_of_accounts.count_documents({"id": {"$in": account_ids}})
        if found != len(set(account_ids)):
            raise HTTPException(status_code=400, detail="One of those accounts no longer exists")
    doc = {
        "id": f"facc_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "user_name": user.get("name", ""),
        "user_role": user.get("role", ""),
        "account_ids": account_ids,
        "updated_at": _now(),
        "updated_by": current_user["id"],
        "updated_by_name": current_user.get("name", ""),
    }
    if account_ids:
        await db.finance_account_access.update_one(
            {"user_id": user_id}, {"$set": {k: v for k, v in doc.items() if k != "id"}, "$setOnInsert": {"id": doc["id"]}}, upsert=True
        )
    else:
        await db.finance_account_access.delete_one({"user_id": user_id})
    return {"ok": True, "user_id": user_id, "account_ids": account_ids,
            "message": f"{user.get('name') or 'They'} may now use {len(account_ids)} account(s)" if account_ids
            else f"{user.get('name') or 'They'} is back to unrestricted access"}
