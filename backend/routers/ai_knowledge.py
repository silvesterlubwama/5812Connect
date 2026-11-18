"""What the assistant is allowed to know, for this person, right now.

Two jobs:
  • find the paperwork that answers a question (and nothing the asker may not see)
  • answer money / people questions only when the asker actually has that access,
    and say plainly why not when they don't

Permission is decided here in Python, never by the model. The model only ever
receives documents and figures this person is already entitled to.
"""
import os
import re
from datetime import date, timedelta
from typing import Optional

from deps import db, get_role_level, has_module_access, is_system_admin, logger, find_linked_member

from routers.org_documents import visible_filter, _local_path, DOC_TYPES

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


PERSON_FILE_WORDS = re.compile(
    r"\b(id|identity|passport|birth\s+certificate|contract|cv|letter|photo|report\s+card|lc1|"
    r"medical|document|documents|file|files|paperwork)\b", re.I)


async def _may_read_person_files(current_user: dict) -> bool:
    """Staff read people's files; a portal member only ever sees their own."""
    return (get_role_level(current_user.get("role")) >= 5
            or is_system_admin(current_user)
            or has_module_access(current_user, "hr")
            or has_module_access(current_user, "social_work"))


async def search_person_files(current_user: dict, text: str, limit: int = 3) -> list:
    """Documents already attached to people's profiles — IDs, contracts, letters.

    They are not re-filed anywhere; we search them where they already live and
    present them in the same shape as organisation paperwork.
    """
    words = _keywords(text)
    if not words or not PERSON_FILE_WORDS.search(text):
        return []
    query = {"is_deleted": False}
    if not await _may_read_person_files(current_user):
        own = await find_linked_member(current_user.get("id"), current_user.get("email"), {"_id": 0, "id": 1})
        ids = [current_user.get("id")] + ([own["id"]] if own else [])
        query["member_id"] = {"$in": ids}
    ors = []
    for w in words:
        rx = {"$regex": re.escape(w), "$options": "i"}
        ors += [{"label": rx}, {"doc_type": rx}, {"member_name": rx}, {"original_filename": rx}]
    query["$or"] = ors
    rows = await db.files.find(query, {"_id": 0}).sort("created_at", -1).to_list(120)

    def score(f):
        hay = " ".join([f.get("label", ""), f.get("doc_type", ""), f.get("member_name", ""),
                        f.get("original_filename", "")]).lower()
        return -sum(2 if w in (f.get("member_name", "") or "").lower() else 1 if w in hay else 0 for w in words)

    rows.sort(key=score)
    out = []
    for f in rows[:limit]:
        out.append({
            "id": f["id"],
            "title": f"{f.get('member_name') or 'Person'} — {f.get('label') or f.get('doc_type') or 'document'}",
            "doc_type": f.get("doc_type") or "id",
            "mime": f.get("content_type") or "application/octet-stream",
            "issuer": "",
            "summary": f"On {f.get('member_name') or 'the person'}'s profile, uploaded {str(f.get('created_at') or '')[:10]}.",
            "expires_on": "",
            "file_url": f"/api/documents/{f['id']}/file",
            "_disk_path": os.path.join("/app/backend", f.get("local_path") or ""),
            "source": "person_file",
        })
    return out


def attachment_of(doc: dict) -> dict:
    """What the chat needs to render and offer a download."""
    person = doc.get("source") in ("person_file", "child_file")
    return {
        "document_id": doc["id"],
        "title": doc.get("title"),
        "doc_type": doc.get("doc_type"),
        "mime": doc.get("mime"),
        "url": doc["file_url"] if person else f"/api/org-documents/{doc['id']}/file",
        "has_file": bool(doc.get("file_url")),
        "from_profile": person,
        "expires_on": doc.get("expires_on") or "",
        "issuer": doc.get("issuer") or "",
    }


def readable_files(docs: list, limit: int = 2) -> list:
    """Local paths Gemini can actually open, newest/best first."""
    out = []
    for d in docs:
        p = d.get("_disk_path") if d.get("source") == "person_file" else _local_path(d.get("file_url"))
        if p and not os.path.exists(p):
            p = None
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


# --------------------------------------------------------------- expiring paperwork
EXPIRY_LIST_WORDS = re.compile(
    r"\b(which|what|any|list|all)\b.{0,40}\b(expir\w*|renew\w*|laps\w*|run(?:ning)?\s+out|due)\b", re.I)


async def expiry_rundown(current_user: dict, text: str = "", days: int = 92) -> Optional[dict]:
    """A real list of what runs out, straight from the records.

    The model is given the list rather than asked to recall dates — it can
    summarise, but it cannot invent an expiry.
    """
    if text and not EXPIRY_LIST_WORDS.search(text):
        return None
    if re.search(r"\b(month|30\s*days)\b", text or "", re.I):
        days = 31
    elif re.search(r"\b(year|12\s*months)\b", text or "", re.I):
        days = 366
    today = date.today()
    horizon = (today + timedelta(days=days)).isoformat()
    rows = await db.org_documents.find(
        {**visible_filter(current_user), "expires_on": {"$gt": "", "$lte": horizon}},
        {"_id": 0},
    ).sort("expires_on", 1).to_list(40)
    if not rows:
        return {"facts": f"Nothing on file expires in the next {days} days (of the documents this person may see).",
                "docs": []}
    lines = []
    for r in rows:
        try:
            left = (date.fromisoformat(r["expires_on"]) - today).days
        except Exception:
            left = None
        when = "already expired" if left is not None and left < 0 else f"{left} days left" if left is not None else ""
        lines.append(f"- {r['title']} ({DOC_TYPES.get(r.get('doc_type'), 'document')}): {r['expires_on']} — {when}"
                     + (f", issued by {r['issuer']}" if r.get("issuer") else ""))
    return {"facts": "Paperwork expiring, soonest first:\n" + "\n".join(lines), "docs": rows[:3]}


async def heads_up(current_user: dict) -> str:
    """One line for a director or admin: what is about to lapse, unprompted."""
    if get_role_level(current_user.get("role")) < 8 and not is_system_admin(current_user):
        return ""
    today = date.today()
    soon = (today + timedelta(days=45)).isoformat()
    rows = await db.org_documents.find(
        {**visible_filter(current_user), "expires_on": {"$gt": "", "$lte": soon}},
        {"_id": 0, "title": 1, "expires_on": 1},
    ).sort("expires_on", 1).to_list(5)
    if not rows:
        return ""
    return ("EXPIRING SOON (mention this once, briefly, even if not asked): "
            + "; ".join(f"{r['title']} on {r['expires_on']}" for r in rows))


# --------------------------------------------------------------- managers fix things by saying so
EDIT_WORDS = re.compile(
    r"(\b(rename|retitle|change|correct|fix|update|set|make)\b.{0,60}"
    r"\b(title|name|expir\w*|renewal|date|visib\w*|who\s+(can|may)\s+see|access|level|confidential)\b)"
    r"|(\b(only|restrict\w*|limit|hide|confidential|private)\b.{0,60}\b(see|view|read|access|open)\b)", re.I)
NOTE_WORDS = re.compile(r"^\s*(remember(\s+this)?|note(\s+this)?|file this note|add to (the )?knowledge)\b[:,\-]?\s*", re.I)
URL_RX = re.compile(r"https?://[^\s<>\"')]+")


async def try_document_edit(current_user: dict, text: str) -> Optional[dict]:
    """"Change the NGO permit's expiry to 2028-03-31" — done, and confirmed.

    Only managers and above get here, and only documents they can already see
    can be touched. The model turns the sentence into fields; the write itself
    is ordinary validated code.
    """
    if get_role_level(current_user.get("role")) < 7 and not is_system_admin(current_user):
        return None
    if not EDIT_WORDS.search(text):
        return None
    docs = await search_documents(current_user, text, limit=3)
    if not docs:
        return {"answer": "I couldn't tell which document you mean — say its title and I'll change it."}

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    fields = {}
    if api_key:
        try:
            import json as _json
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(
                api_key=api_key, session_id=f"docedit_{current_user['id']}",
                system_message=(
                    "Turn the instruction into ONE JSON object and nothing else: "
                    '{"document_title": which of the listed documents it refers to, '
                    '"title": new title or "", "expires_on": "YYYY-MM-DD" or "", '
                    '"min_level": 5 (all staff) | 6 (coordinators+) | 7 (managers+) | 8 (directors+) | 10 (admins) or 0, '
                    '"doc_type": one of ' + str(sorted(DOC_TYPES)) + ' or ""}. '
                    "Use \"\" or 0 for anything the instruction does not change."
                ),
            ).with_model("gemini", "gemini-2.5-flash")
            listing = "; ".join(d["title"] for d in docs)
            raw = await chat.send_message(UserMessage(text=f"Documents on file: {listing}\n\nInstruction: {text}"))
            m = re.search(r"\{.*\}", raw or "", re.S)
            fields = _json.loads(m.group(0)) if m else {}
        except Exception as e:
            logger.warning(f"Could not read the edit instruction: {e}")

    target = next((d for d in docs if fields.get("document_title")
                   and fields["document_title"].lower() in d["title"].lower()), docs[0])
    if target.get("source") == "person_file":
        return {"answer": f"'{target['title']}' sits on someone's profile — change it on their profile page, not here."}

    update = {}
    if fields.get("title"):
        update["title"] = str(fields["title"])[:200]
    if fields.get("expires_on"):
        update["expires_on"] = str(fields["expires_on"])[:10]
    if fields.get("doc_type") in DOC_TYPES:
        update["doc_type"] = fields["doc_type"]
    if int(fields.get("min_level") or 0):
        update["min_level"] = int(fields["min_level"])
    if not update:
        return {"answer": f"I found '{target['title']}' but couldn't tell what to change — try "
                          "\"change its expiry to 2028-03-31\" or \"only directors may see it\"."}

    from routers.org_documents import update_document, VISIBILITY_LEVELS
    try:
        saved = await update_document(target["id"], update, current_user)
    except Exception as e:
        detail = getattr(e, "detail", None) or str(e)
        return {"answer": f"I couldn't change '{target['title']}': {detail}"}
    said = []
    if "title" in update:
        said.append(f"renamed it to \"{saved['title']}\"")
    if "expires_on" in update:
        said.append(f"set its expiry to {saved['expires_on'] or 'none'}")
    if "doc_type" in update:
        said.append(f"filed it as a {DOC_TYPES.get(saved['doc_type'], saved['doc_type']).lower()}")
    if "min_level" in update:
        said.append(f"limited it to {VISIBILITY_LEVELS[saved['min_level']].lower()}")
    return {"answer": f"Done — {', and '.join(said)}.", "document": saved, "edited": True}


async def try_knowledge_note(current_user: dict, text: str) -> Optional[dict]:
    """"Remember this: the bureau moved to Plot 12" — kept, and searchable.

    A link is fetched once and stored as text, because the person explicitly
    handed it over; the assistant never goes looking on the internet itself.
    """
    if get_role_level(current_user.get("role")) < 7 and not is_system_admin(current_user):
        return None
    if not NOTE_WORDS.search(text):
        return None
    body = NOTE_WORDS.sub("", text).strip()
    if not body:
        return {"answer": "Tell me what to remember — a note, or a link to a page."}
    from routers.org_documents import store_note
    found = URL_RX.search(body)
    url = found.group(0) if found else None
    doc = await store_note(current_user, body, url=url)
    where = f" from {url}" if url else ""
    return {"answer": f"Noted{where} as \"{doc['title']}\" — "
                      f"{'anyone on staff' if doc['min_level'] <= 5 else 'people at the level you set'} can ask me about it now.",
            "document": doc, "noted": True}


# --------------------------------------------------------------- children's own paperwork
CHILD_FILE_WORDS = re.compile(
    r"\b(guardian|lc1|lc\s?1|local\s+council|birth\s+certificate|consent|referral|child'?s?\s+(id|file|document)|"
    r"sponsor\s+letter|immunisation|immunization|school\s+report)\b", re.I)


def _may_read_child_files(current_user: dict) -> bool:
    """Children's paperwork belongs to social work — and to nobody browsing."""
    return (is_system_admin(current_user)
            or has_module_access(current_user, "social_work")
            or get_role_level(current_user.get("role")) >= 8)


async def search_child_files(current_user: dict, text: str, limit: int = 3) -> list:
    """Guardian IDs, LC1 letters and the rest, where social work already keeps them."""
    words = _keywords(text)
    if not words:
        return []
    if not (CHILD_FILE_WORDS.search(text) or PERSON_FILE_WORDS.search(text)):
        return []
    if not _may_read_child_files(current_user):
        return []
    ors = []
    for w in words:
        rx = {"$regex": re.escape(w), "$options": "i"}
        ors += [{"child_name": rx}, {"doc_label": rx}, {"doc_type": rx}, {"caption": rx}, {"file_name": rx}]
    rows = await db.child_extras.find({"$or": ors}, {"_id": 0}).sort("created_at", -1).to_list(120)

    def score(f):
        hay = " ".join([f.get("child_name", ""), f.get("doc_label", ""), f.get("doc_type", ""),
                        f.get("caption", ""), f.get("file_name", "")]).lower()
        return -sum(2 if w in (f.get("child_name") or "").lower() else 1 if w in hay else 0 for w in words)

    rows.sort(key=score)
    out = []
    for f in rows[:limit]:
        label = f.get("doc_label") or f.get("doc_type") or f.get("kind") or "file"
        out.append({
            "id": f["id"],
            "title": f"{f.get('child_name') or 'Child'} — {label}",
            "doc_type": (f.get("doc_type") or "id"),
            "mime": "application/octet-stream",
            "issuer": "",
            "summary": ((f.get("caption") + " ") if f.get("caption") else "")
                       + f"On {f.get('child_name') or 'the child'}'s record"
                        + (f", issued {f['issued_date']}" if f.get("issued_date") else "") + ".",
            "expires_on": "",
            "file_url": f.get("file_url") or "",
            "source": "child_file",
        })
    return out


# --------------------------------------------------------------- the rest of the application
def _fmt_money(v) -> str:
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return str(v or "")


# What the assistant may look through, and who may look. Every query runs on the
# org-scoped `db`, so one organisation never sees another's records.
APP_SOURCES = [
    {"col": "members", "label": "Member", "level": 5,
     "fields": ["name", "email", "phone", "badge_id", "department", "group"],
     "line": lambda r: f"{r.get('name')} — member{', ' + r['department'] if r.get('department') else ''}"
                       f"{', ' + r['phone'] if r.get('phone') else ''}"},
    {"col": "children", "label": "Child", "level": 5, "module": "social_work",
     "fields": ["name", "class_group", "grade", "school"],
     "line": lambda r: f"{r.get('name')} — child, {r.get('class_group') or r.get('grade') or 'no class on file'}"
                       f"{', sponsored' if r.get('is_sponsored') else ''}"},
    {"col": "families", "label": "Family", "level": 5,
     "fields": ["family_name", "primary_contact_name", "primary_contact_phone"],
     "line": lambda r: f"{r.get('family_name')} — family, contact {r.get('primary_contact_name') or '—'}"
                       f" {r.get('primary_contact_phone') or ''}"},
    {"col": "social_cases", "label": "Welfare case", "level": 6, "module": "social_work",
     "fields": ["subject_name", "category", "status", "risk_level"],
     "line": lambda r: f"{r.get('subject_name')} — {str(r.get('category') or '').replace('_', ' ')} case,"
                       f" {r.get('status')}, risk {r.get('risk_level') or 'n/a'}"},
    {"col": "events", "label": "Event", "level": 5,
     "fields": ["title", "description", "location", "programme_name"],
     "line": lambda r: f"{r.get('title')} — event on {r.get('date')} {r.get('start_time') or ''}"
                       f" at {r.get('location') or 'n/a'}"},
    {"col": "resources", "label": "Resource", "level": 5,
     "fields": ["name", "category", "description", "barcode"],
     "line": lambda r: f"{r.get('name')} — {r.get('category') or 'resource'},"
                       f" {'available' if r.get('available') else 'in use'}"},
    {"col": "products", "label": "Product", "level": 5,
     "fields": ["name", "sku", "category", "barcode"],
     "line": lambda r: f"{r.get('name')} — product, {_fmt_money(r.get('price'))} {r.get('currency') or ''},"
                       f" {r.get('stock', 0)} in stock"},
    {"col": "sales", "label": "Sale", "level": 6, "module": "sales",
     "fields": ["receipt_number", "customer_name", "cashier"],
     "line": lambda r: f"Receipt {r.get('receipt_number') or r.get('id')} — {_fmt_money(r.get('total'))}"
                       f" on {str(r.get('created_at') or '')[:10]}, served by {r.get('cashier') or '—'}"},
    {"col": "financial", "label": "Finance entry", "level": 6, "module": "finance",
     "fields": ["description", "category", "notes", "vendor"],
     "line": lambda r: f"{r.get('type', 'entry').title()} {_fmt_money(r.get('amount'))} {r.get('currency') or ''}"
                       f" — {r.get('description') or r.get('category')} on {r.get('date')}"},
    {"col": "approval_requests", "label": "Request", "level": 5,
     "fields": ["title", "summary"],
     "line": lambda r: f"{r.get('title')} — {str(r.get('subject_kind') or '').replace('_', ' ')},"
                       f" {_fmt_money(r.get('amount'))} {r.get('currency') or ''}, {r.get('status')}"},
    {"col": "users", "label": "Staff", "level": 7, "module": "hr",
     "fields": ["name", "email", "role", "department"],
     "line": lambda r: f"{r.get('name')} — {r.get('role')}{', ' + r['department'] if r.get('department') else ''}"},
]


def _source_allowed(src: dict, current_user: dict) -> bool:
    if is_system_admin(current_user):
        return True
    if get_role_level(current_user.get("role")) < src.get("level", 5):
        return False
    module = src.get("module")
    if module and not has_module_access(current_user, module):
        # Social work records stay open to general staff; money and people don't.
        return module == "social_work" and get_role_level(current_user.get("role")) >= 5
    return True


async def search_app_records(current_user: dict, text: str, per_source: int = 3, total: int = 10) -> list:
    """Everything else in the app this person may see — people, cases, events,
    stock, sales, requests — searched in one pass, org-scoped by the database
    wrapper so one organisation's records never leak into another's answers."""
    words = _keywords(text)
    if not words:
        return []
    found = []
    for src in APP_SOURCES:
        if len(found) >= total or not _source_allowed(src, current_user):
            continue
        ors = []
        for w in words:
            rx = {"$regex": re.escape(w), "$options": "i"}
            ors += [{f: rx} for f in src["fields"]]
        try:
            rows = await db[src["col"]].find(
                {"$or": ors, "is_deleted": {"$ne": True}, "deleted": {"$ne": True}}, {"_id": 0}
            ).limit(per_source).to_list(per_source)
        except Exception as e:
            logger.warning(f"App search on {src['col']} failed: {e}")
            continue
        for r in rows:
            try:
                found.append(f"[{src['label']}] {src['line'](r)}")
            except Exception:
                found.append(f"[{src['label']}] {r.get('name') or r.get('title') or r.get('id')}")
    return found[:total]


# --------------------------------------------------------------- tidying the shelf
TIDY_LIST_WORDS = re.compile(
    r"(\b(what|which)\b.{0,30}\b(documents?|paperwork|files?)\b)"
    r"|(\b(list|show)\b.{0,25}\b(documents?|paperwork)\b)"
    r"|(\bwhat('?s| is| are)?\s+(on\s+file|filed|stored)\b)", re.I)
TIDY_DUPE_WORDS = re.compile(r"\b(duplicate|duplicates|dupes|tidy|clean\s*up|clear\s+out)\b", re.I)
TIDY_DO_IT = re.compile(r"\b(remove|delete|clear|tidy|clean|get\s+rid)\b", re.I)


def _dupe_key(doc: dict) -> str:
    return "|".join([
        re.sub(r"\s+", " ", (doc.get("title") or "").strip().lower()),
        doc.get("doc_type") or "",
        str(doc.get("size") or ""),
    ])


async def try_document_tidy(current_user: dict, text: str) -> Optional[dict]:
    """"What's filed?" and "clear out the duplicates" — both answered here.

    Removal keeps the oldest of each set (the one people have been citing) and
    only ever soft-deletes, so nothing actually leaves the audit trail.
    """
    wants_list = bool(TIDY_LIST_WORDS.search(text))
    wants_dupes = bool(TIDY_DUPE_WORDS.search(text)) and re.search(r"\b(document|documents|paperwork|file|files|permit|certificate)\b", text, re.I)
    if not (wants_list or wants_dupes):
        return None
    docs = await db.org_documents.find(visible_filter(current_user), {"_id": 0, "text": 0}) \
        .sort("created_at", 1).to_list(400)
    if not docs:
        return {"answer": "Nothing is filed yet that you can see. Drop a file in with “Add document” and I'll remember it."}

    if wants_dupes:
        groups = {}
        for d in docs:
            groups.setdefault(_dupe_key(d), []).append(d)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}
        if not dupes:
            return {"answer": f"No duplicates — {len(docs)} document(s) on file, each one different."}
        manager = get_role_level(current_user.get("role")) >= 7 or is_system_admin(current_user)
        if not (manager and TIDY_DO_IT.search(text)):
            lines = [f"- {v[0]['title']}: {len(v)} copies (filed {', '.join(str(x.get('created_at'))[:10] for x in v)})"
                     for v in dupes.values()]
            tail = ("Say \"clear out the duplicates\" and I'll keep the earliest of each and retire the rest."
                    if manager else "A manager can ask me to clear them out.")
            return {"answer": "Looks like repeats:\n" + "\n".join(lines) + "\n" + tail}
        removed, kept = [], []
        for v in dupes.values():
            kept.append(v[0]["title"])
            for extra in v[1:]:
                await db.org_documents.update_one({"id": extra["id"]}, {"$set": {
                    "deleted": True,
                    "deleted_at": datetime_now(),
                    "deleted_by": current_user["id"],
                    "deleted_by_name": current_user.get("name", ""),
                    "deleted_reason": "duplicate, cleared from chat",
                }})
                removed.append(extra["id"])
        return {"answer": f"Tidied — kept the earliest copy of {len(kept)} document(s) and retired "
                          f"{len(removed)} repeat(s). Nothing is gone for good; a director can still see them in the audit trail.",
                "tidied": True, "removed": removed}

    by_type = {}
    for d in docs:
        by_type.setdefault(DOC_TYPES.get(d.get("doc_type"), "Other"), []).append(d)
    lines = []
    for label, items in sorted(by_type.items()):
        lines.append(f"{label} ({len(items)}): " + "; ".join(
            i["title"] + (f" — expires {i['expires_on']}" if i.get("expires_on") else "") for i in items[:6]
        ) + (" …" if len(items) > 6 else ""))
    return {"facts": f"{len(docs)} document(s) you may see:\n" + "\n".join(lines)}


def datetime_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
