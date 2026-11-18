"""What the assistant is allowed to know, for this person, right now.

Two jobs:
  • find the paperwork that answers a question (and nothing the asker may not see)
  • answer money / people questions only when the asker actually has that access,
    and say plainly why not when they don't

Permission is decided here in Python, never by the model. The model only ever
receives documents and figures this person is already entitled to.
"""
import re
from datetime import date, timedelta
from typing import Optional

from deps import db, get_role_level, has_module_access, is_system_admin, logger

from routers.org_documents import visible_filter, _local_path

STOP_WORDS = {
    "the", "our", "does", "do", "when", "what", "how", "much", "many", "is", "are", "a", "an", "of", "for",
    "we", "us", "my", "me", "in", "on", "at", "to", "and", "or", "it", "this", "that", "did", "was", "were",
    "show", "tell", "give", "can", "you", "please", "about", "with", "from", "have", "has", "there", "their",
    "expire", "expires", "expiry", "copy", "find", "need", "want", "last", "month", "year",
}

# Rough topic → module map. If a question is clearly about one of these and the
# person doesn't hold that module, we refuse instead of guessing.
MONEY_WORDS = re.compile(
    r"\b(spend|spent|spending|expense|expenses|expenditure|income|revenue|budget|profit|loss|balance|cash|bank|"
    r"donation|donations|turnover|sales\s+total|financial|finances|accounts?)\b", re.I)
PAYROLL_WORDS = re.compile(r"\b(payroll|salary|salaries|payslip|payslips|wages|staff\s+pay|net\s+pay)\b", re.I)
SALES_WORDS = re.compile(r"\b(sales|sold|takings|till|pos|shop\s+revenue)\b", re.I)
MINE_WORDS = re.compile(r"\b(my|mine|i\s+(spent|claimed|requested)|my\s+own)\b", re.I)
EXPIRY_WORDS = re.compile(r"\b(expire|expires|expiry|expiring|renew|renewal|valid\s+until)\b", re.I)


def _keywords(text: str) -> list:
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9'\-]{2,}", text.lower()) if w not in STOP_WORDS]
    return words[:8]


def _month_window(text: str) -> tuple:
    """(start, end, label) — 'last month' by default when a month is implied."""
    today = date.today()
    if re.search(r"\blast\s+month\b", text, re.I):
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        return start.isoformat(), end.isoformat(), end.strftime("%B %Y")
    if re.search(r"\b(this\s+year|year\s+to\s+date|ytd)\b", text, re.I):
        return today.replace(month=1, day=1).isoformat(), today.isoformat(), str(today.year)
    if re.search(r"\blast\s+year\b", text, re.I):
        y = today.year - 1
        return f"{y}-01-01", f"{y}-12-31", str(y)
    start = today.replace(day=1)
    return start.isoformat(), today.isoformat(), today.strftime("%B %Y")


# --------------------------------------------------------------- documents
async def search_documents(current_user: dict, text: str, limit: int = 4) -> list:
    """Paperwork this person may read, best match first."""
    words = _keywords(text)
    if not words:
        return []
    ors = []
    for w in words:
        rx = {"$regex": re.escape(w), "$options": "i"}
        ors += [{"title": rx}, {"summary": rx}, {"tags": rx}, {"issuer": rx}, {"text": rx}]
    query = {**visible_filter(current_user), "$or": ors}
    rows = await db.org_documents.find(query, {"_id": 0}).sort("created_at", -1).to_list(30)
    if EXPIRY_WORDS.search(text):
        rows.sort(key=lambda r: (not r.get("expires_on"), r.get("expires_on") or ""))

    def score(doc):
        hay = " ".join([doc.get("title", ""), doc.get("summary", ""), doc.get("issuer", ""),
                        " ".join(doc.get("tags") or []), (doc.get("text") or "")[:4000]]).lower()
        s = sum(3 if w in (doc.get("title", "") + " ".join(doc.get("tags") or [])).lower() else
                1 if w in hay else 0 for w in words)
        if EXPIRY_WORDS.search(text) and doc.get("expires_on"):
            s += 2
        return -s

    rows.sort(key=score)
    return rows[:limit]


def attachment_of(doc: dict) -> dict:
    """What the chat needs to render and offer a download."""
    return {
        "document_id": doc["id"],
        "title": doc.get("title"),
        "doc_type": doc.get("doc_type"),
        "mime": doc.get("mime"),
        "url": f"/api/org-documents/{doc['id']}/file",
        "expires_on": doc.get("expires_on") or "",
        "issuer": doc.get("issuer") or "",
    }


def readable_files(docs: list, limit: int = 2) -> list:
    """Local paths Gemini can actually open, newest/best first."""
    out = []
    for d in docs:
        p = _local_path(d.get("file_url"))
        if p and d.get("mime") in ("application/pdf", "image/jpeg", "image/png", "image/webp", "text/plain", "text/csv"):
            out.append((p, d["mime"]))
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------- money / people
async def _spend_and_income(start: str, end: str) -> dict:
    coa = {a["id"]: a async for a in db.finance_chart_of_accounts.find({}, {"_id": 0, "id": 1, "type": 1, "name": 1, "code": 1})}
    spend, income, by_account = 0.0, 0.0, {}
    async for je in db.finance_journal_entries.find(
        {"date": {"$gte": start, "$lte": end}, "voided": {"$ne": True}}, {"_id": 0, "lines": 1}
    ):
        for ln in je.get("lines") or []:
            acct = coa.get(ln.get("account_id"))
            if not acct:
                continue
            if acct["type"] == "expense":
                amt = float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
                spend += amt
                if amt:
                    by_account[acct["name"]] = by_account.get(acct["name"], 0) + amt
            elif acct["type"] == "revenue":
                income += float(ln.get("credit") or 0) - float(ln.get("debit") or 0)
    top = sorted(by_account.items(), key=lambda kv: -kv[1])[:6]
    return {"spend": round(spend, 2), "income": round(income, 2), "top": top}


async def _my_money(current_user: dict, start: str, end: str) -> Optional[dict]:
    """What this person can see of their own: their granted accounts, their own
    postings and their own fund requests."""
    grant = await db.finance_account_access.find_one({"user_id": current_user["id"]}, {"_id": 0})
    account_ids = (grant or {}).get("account_ids") or []
    accounts = []
    if account_ids:
        coa = await db.finance_chart_of_accounts.find({"id": {"$in": account_ids}}, {"_id": 0}).to_list(100)
        totals = {a["id"]: 0.0 for a in coa}
        async for je in db.finance_journal_entries.find(
            {"date": {"$gte": start, "$lte": end}, "voided": {"$ne": True}}, {"_id": 0, "lines": 1}
        ):
            for ln in je.get("lines") or []:
                if ln.get("account_id") in totals:
                    totals[ln["account_id"]] += float(ln.get("debit") or 0) - float(ln.get("credit") or 0)
        accounts = [{"code": a["code"], "name": a["name"], "type": a["type"],
                     "movement": round(totals.get(a["id"], 0), 2)} for a in coa]
    own_spend = 0.0
    async for je in db.finance_journal_entries.find(
        {"date": {"$gte": start, "$lte": end}, "created_by": current_user["id"], "voided": {"$ne": True}},
        {"_id": 0, "total": 1, "source": 1},
    ):
        if je.get("source") in ("expense", "fund_request", "social_expense"):
            own_spend += float(je.get("total") or 0)
    requests_ = await db.approval_requests.find(
        {"subject_kind": "fund_request", "submitted_by": current_user["id"]},
        {"_id": 0, "title": 1, "amount": 1, "currency": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(10)
    if not accounts and not own_spend and not requests_:
        return None
    return {"accounts": accounts, "own_spend": round(own_spend, 2), "requests": requests_}


async def answer_data_question(current_user: dict, text: str) -> Optional[dict]:
    """Money/people questions, gated. Returns None when the question isn't one.

    `{"facts": "...", "denied": False}` — facts get handed to the model.
    `{"answer": "...", "denied": True}` — refusal, sent back verbatim.
    """
    role = current_user.get("role") or "staff"
    wants_money = bool(MONEY_WORDS.search(text))
    wants_payroll = bool(PAYROLL_WORDS.search(text))
    wants_sales = bool(SALES_WORDS.search(text))
    if not (wants_money or wants_payroll or wants_sales):
        return None

    start, end, label = _month_window(text)
    admin = is_system_admin(current_user)

    if wants_payroll and not (admin or has_module_access(current_user, "hr")):
        return {"denied": True, "answer": (
            f"I can't show payroll figures — as {role} you don't have HR access, and salaries are limited to HR "
            "and directors. Your own payslips are on HR & Payroll → My payslips, and a director can grant you "
            "HR access if you need the wider numbers."
        )}

    if (wants_money or wants_sales) and not (admin or has_module_access(current_user, "finance")
                                             or (wants_sales and has_module_access(current_user, "sales"))):
        mine = await _my_money(current_user, start, end)
        if mine:
            lines = [f"Organisation-wide figures are finance-only, but here is your own for {label}:"]
            if mine["accounts"]:
                lines.append("Your accounts: " + "; ".join(
                    f"{a['code']} {a['name']} — movement {a['movement']:,.2f}" for a in mine["accounts"]))
            if mine["own_spend"]:
                lines.append(f"Money you recorded or were paid out: {mine['own_spend']:,.2f}")
            if mine["requests"]:
                lines.append("Your fund requests: " + "; ".join(
                    f"{r['title']} — {r.get('currency', '')} {float(r.get('amount') or 0):,.0f} ({r.get('status')})"
                    for r in mine["requests"][:5]))
            return {"denied": False, "facts": "\n".join(lines), "scope": "own",
                    "preamble": f"As {role} you can see your own accounts and claims, not the organisation's totals."}
        return {"denied": True, "answer": (
            f"I can't share what the organisation spent — as {role} you don't have finance access, and the ledger "
            "is limited to finance staff and directors. If you're meant to see a particular account, a director "
            "can give you access under Finance → Chart of Accounts → Account access, and I'll report on it here."
        )}

    totals = await _spend_and_income(start, end)
    facts = [
        f"Window: {label} ({start} to {end}).",
        f"Total spend (expense accounts): {totals['spend']:,.2f}",
        f"Total income (revenue accounts): {totals['income']:,.2f}",
    ]
    if totals["top"]:
        facts.append("Biggest expense accounts: " + "; ".join(f"{n} {v:,.2f}" for n, v in totals["top"]))
    return {"denied": False, "facts": "\n".join(facts), "scope": "org"}


def access_summary(current_user: dict) -> str:
    """One line the model must respect when deciding what to repeat."""
    mods = [m for m in ("finance", "hr", "sales", "accounting", "banking", "social_work")
            if has_module_access(current_user, m)]
    return (f"role {current_user.get('role') or 'Staff'} (level {get_role_level(current_user.get('role'))}), "
            f"modules: {', '.join(mods) if mods else 'none beyond general staff access'}")
