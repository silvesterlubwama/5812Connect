"""The organisation's own paperwork — permits, certificates, agreements, receipts.

Files are dropped into the AI chat by a manager or admin; there is no separate
library screen. On the way in the file is read once: text is pulled out of PDFs,
the model names what the document is, who issued it and when it expires, and all
of that is stored so a staff member can later simply ask "when does our NGO
permit expire?".

Every document carries a `min_level` — the role level needed to see it. A staff
member never learns that a document they can't see even exists.
"""
import os
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse

from deps import db, require_staff, require_manager, get_role_level, logger, _audit
from upload_helper import _disk_fallback, UPLOAD_ROOT

router = APIRouter(prefix="/api/org-documents", tags=["org-documents"])

DOC_TYPES = {
    "permit": "Permit / licence",
    "certificate": "Certificate",
    "agreement": "Agreement / MOU",
    "contract": "Contract",
    "receipt": "Receipt / invoice",
    "policy": "Policy",
    "id": "Identity document",
    "report": "Report",
    "other": "Other",
}

# Who may read it, by role level (deps.get_role_level).
VISIBILITY_LEVELS = {
    5: "Every staff member",
    6: "Coordinators and above",
    7: "Managers and above",
    8: "Directors and above",
    10: "Admins only",
}

ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "text/plain": ".txt",
    "text/csv": ".csv",
}
MAX_BYTES = 25 * 1024 * 1024


def _local_path(file_url: str) -> Optional[str]:
    """Disk path for a file we stored ourselves, if it is still there."""
    if not file_url or not file_url.startswith("/api/uploads/"):
        return None
    p = os.path.join(UPLOAD_ROOT, file_url.replace("/api/uploads/", "", 1))
    return p if os.path.exists(p) else None


def _extract_text(path: str, mime: str) -> str:
    """Whatever text we can read without a model — PDFs and plain files."""
    try:
        if mime == "application/pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join((pg.extract_text() or "") for pg in reader.pages[:25])[:20000]
        if mime in ("text/plain", "text/csv"):
            with open(path, "r", errors="ignore") as fh:
                return fh.read(20000)
    except Exception as e:
        logger.warning(f"Text extraction failed for {path}: {e}")
    return ""


async def _read_with_model(path: str, mime: str, extracted: str) -> dict:
    """Ask the model what this paper is. Gemini is the only provider that
    takes a file path, which is exactly what we have here."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        chat = LlmChat(
            api_key=api_key,
            session_id=f"orgdoc_{uuid.uuid4().hex[:8]}",
            system_message=(
                "You file paperwork for a non-profit. Reply with ONE JSON object and nothing else: "
                '{"title": short human title, "doc_type": one of '
                f'{sorted(DOC_TYPES)}, "issuer": who issued it or "", '
                '"issued_on": "YYYY-MM-DD" or "", "expires_on": "YYYY-MM-DD" or "", '
                '"reference": any permit/serial/invoice number or "", '
                '"summary": 2-3 plain sentences a staff member would find useful, '
                '"tags": up to 6 lowercase keywords}. Use "" when the document does not say.'
            ),
        ).with_model("gemini", "gemini-2.5-flash")
        msg = UserMessage(
            text="File this document." + (f"\n\nText already read from it:\n{extracted[:6000]}" if extracted else ""),
            file_contents=[FileContentWithMimeType(file_path=path, mime_type=mime)],
        )
        raw = await chat.send_message(msg)
        import json as _json
        import re
        m = re.search(r"\{.*\}", raw or "", re.S)
        return _json.loads(m.group(0)) if m else {}
    except Exception as e:
        logger.warning(f"Model could not read the document: {e}")
        return {}


def _clean_date(value) -> str:
    v = str(value or "")[:10]
    try:
        date.fromisoformat(v)
        return v
    except Exception:
        return ""


def visible_filter(current_user: dict) -> dict:
    """Mongo fragment limiting documents to what this person may read."""
    return {"deleted": {"$ne": True}, "min_level": {"$lte": get_role_level(current_user.get("role"))}}


@router.get("/types")
async def document_types(current_user: dict = Depends(require_staff)):
    return {"types": DOC_TYPES, "visibility_levels": VISIBILITY_LEVELS}


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    min_level: int = Form(5),
    expires_on: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    current_user: dict = Depends(require_manager),
):
    """Managers and admins add paperwork. The model reads it once, here."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Files over 25MB are too big to read — split or compress it")
    mime = (file.content_type or "").split(";")[0].lower()
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"{mime or 'That file type'} can't be filed — use PDF, JPG, PNG, WEBP, TXT or CSV")
    if int(min_level) not in VISIBILITY_LEVELS:
        raise HTTPException(status_code=400, detail="Pick who may see this document")

    doc_id = f"odoc_{uuid.uuid4().hex[:10]}"
    fname = f"{doc_id}{ALLOWED_MIME[mime]}"
    file_url = _disk_fallback("org-documents", fname, data)   # kept local so the model can read it
    path = _local_path(file_url)
    extracted = _extract_text(path, mime) if path else ""
    read = await _read_with_model(path, mime, extracted) if path else {}

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": doc_id,
        "title": (title or read.get("title") or file.filename or "Untitled document")[:200],
        "doc_type": (doc_type or read.get("doc_type") or "other").lower()[:40],
        "issuer": str(read.get("issuer") or "")[:160],
        "reference": str(read.get("reference") or "")[:80],
        "issued_on": _clean_date(read.get("issued_on")),
        "expires_on": _clean_date(expires_on) or _clean_date(read.get("expires_on")),
        "summary": str(read.get("summary") or "")[:1200],
        "tags": [str(t).lower()[:30] for t in (read.get("tags") or [])][:8],
        "notes": (notes or "")[:500],
        "text": extracted[:20000],
        "min_level": int(min_level),
        "file_url": file_url,
        "filename": file.filename,
        "mime": mime,
        "size": len(data),
        "source": "chat_upload",
        "location_id": current_user.get("location_id"),
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
        "created_at": now,
    }
    if doc["doc_type"] not in DOC_TYPES:
        doc["doc_type"] = "other"
    await db.org_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    doc.pop("text", None)
    await _audit(current_user["id"], "create", "org_document", doc_id, {"title": doc["title"], "min_level": doc["min_level"]})
    return doc


@router.get("")
async def list_documents(
    q: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: dict = Depends(require_staff),
):
    query = visible_filter(current_user)
    if doc_type:
        query["doc_type"] = doc_type
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"summary": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
            {"text": {"$regex": q, "$options": "i"}},
        ]
    return await db.org_documents.find(query, {"_id": 0, "text": 0}).sort("created_at", -1).to_list(limit)


@router.get("/expiring")
async def expiring_documents(days: int = 60, current_user: dict = Depends(require_staff)):
    """Permits and certificates running out — asked for by the AI and the UI."""
    from datetime import timedelta
    today = date.today()
    horizon = (today + timedelta(days=max(1, days))).isoformat()
    query = {**visible_filter(current_user), "expires_on": {"$gt": "", "$lte": horizon}}
    rows = await db.org_documents.find(query, {"_id": 0, "text": 0}).sort("expires_on", 1).to_list(100)
    for r in rows:
        try:
            r["days_left"] = (date.fromisoformat(r["expires_on"]) - today).days
        except Exception:
            r["days_left"] = None
    return rows


@router.get("/{doc_id}")
async def get_document(doc_id: str, current_user: dict = Depends(require_staff)):
    doc = await db.org_documents.find_one({"id": doc_id, **visible_filter(current_user)}, {"_id": 0, "text": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}/file")
async def download_document(doc_id: str, current_user: dict = Depends(require_staff)):
    """Serve the file itself — permission checked, unlike the static uploads path."""
    doc = await db.org_documents.find_one({"id": doc_id, **visible_filter(current_user)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = _local_path(doc.get("file_url"))
    if not path:
        raise HTTPException(status_code=404, detail="The file is no longer on this server")
    return FileResponse(path, media_type=doc.get("mime") or "application/octet-stream",
                        filename=doc.get("filename") or f"{doc_id}")


@router.put("/{doc_id}")
async def update_document(doc_id: str, data: dict, current_user: dict = Depends(require_manager)):
    """Retitle it, re-file it, or change who may see it."""
    doc = await db.org_documents.find_one({"id": doc_id, "deleted": {"$ne": True}}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    update = {}
    if "title" in data:
        update["title"] = str(data["title"])[:200]
    if "doc_type" in data and str(data["doc_type"]).lower() in DOC_TYPES:
        update["doc_type"] = str(data["doc_type"]).lower()
    if "min_level" in data:
        lvl = int(data["min_level"])
        if lvl not in VISIBILITY_LEVELS:
            raise HTTPException(status_code=400, detail="Pick who may see this document")
        update["min_level"] = lvl
    for f in ("expires_on", "issued_on"):
        if f in data:
            update[f] = _clean_date(data[f])
    if "notes" in data:
        update["notes"] = str(data["notes"])[:500]
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to change")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by_name"] = current_user.get("name", "")
    await db.org_documents.update_one({"id": doc_id}, {"$set": update})
    await _audit(current_user["id"], "update", "org_document", doc_id, update)
    return await db.org_documents.find_one({"id": doc_id}, {"_id": 0, "text": 0})


@router.post("/{doc_id}/to-pdf")
async def convert_to_pdf(doc_id: str, current_user: dict = Depends(require_manager)):
    """Turn a photographed permit or receipt into a clean, filable PDF."""
    doc = await db.org_documents.find_one({"id": doc_id, **visible_filter(current_user)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not (doc.get("mime") or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="That one is already a document, not a photo")
    path = _local_path(doc.get("file_url"))
    if not path:
        raise HTTPException(status_code=404, detail="The original image is no longer on this server")
    from PIL import Image
    new_id = f"odoc_{uuid.uuid4().hex[:10]}"
    out_name = f"{new_id}.pdf"
    out_dir = os.path.join(UPLOAD_ROOT, "org-documents")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    img = Image.open(path)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    img.save(out_path, "PDF", resolution=150.0)
    now = datetime.now(timezone.utc).isoformat()
    new_doc = {
        **{k: v for k, v in doc.items() if k not in ("id", "file_url", "mime", "size", "filename", "created_at", "source", "text")},
        "id": new_id,
        "title": f"{doc['title']} (PDF)"[:200],
        "file_url": f"/api/uploads/org-documents/{out_name}",
        "mime": "application/pdf",
        "size": os.path.getsize(out_path),
        "filename": out_name,
        "source": "derived",
        "derived_from": doc["id"],
        "text": doc.get("text", ""),
        "created_at": now,
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
    }
    await db.org_documents.insert_one(dict(new_doc))
    new_doc.pop("_id", None)
    new_doc.pop("text", None)
    await _audit(current_user["id"], "create", "org_document", new_id, {"derived_from": doc["id"], "kind": "image→pdf"})
    return new_doc


@router.delete("/{doc_id}")
async def remove_document(doc_id: str, current_user: dict = Depends(require_manager)):
    """Take it out of circulation — the row stays for the audit trail."""
    res = await db.org_documents.update_one(
        {"id": doc_id, "deleted": {"$ne": True}},
        {"$set": {"deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat(),
                  "deleted_by": current_user["id"], "deleted_by_name": current_user.get("name", "")}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Document not found")
    await _audit(current_user["id"], "delete", "org_document", doc_id, {})
    return {"deleted": True}


async def warn_about_expiring_documents(days: int = 30) -> dict:
    """Tell the people who can act that a permit or certificate is running out.

    Runs once a day. One notification per document per threshold, so nobody is
    nagged daily for the same permit — 30 days out, then 7, then the day it
    lapses.
    """
    from datetime import timedelta
    from routers.notifications import create_notification
    today = date.today()
    horizon = (today + timedelta(days=max(1, days))).isoformat()
    sent = 0
    async for doc in db.org_documents.find(
        {"deleted": {"$ne": True}, "expires_on": {"$gt": "", "$lte": horizon}}, {"_id": 0}
    ):
        try:
            left = (date.fromisoformat(doc["expires_on"]) - today).days
        except Exception:
            continue
        step = 30 if left > 7 else 7 if left > 0 else 0
        if doc.get("last_expiry_warning_step") == step:
            continue
        kind = DOC_TYPES.get(doc.get("doc_type"), "Document")
        when = (f"expires in {left} day{'s' if left != 1 else ''}" if left > 0
                else "has expired" if left == 0 else "expired")
        await create_notification(
            title=f"{kind} {when}",
            message=f"{doc['title']}{' (' + doc['issuer'] + ')' if doc.get('issuer') else ''} {when} — {doc['expires_on']}.",
            user_id="",
            notif_type="warning" if left > 0 else "error",
            link="/comms",
            target_role="Director",
        )
        await db.org_documents.update_one({"id": doc["id"]}, {"$set": {
            "last_expiry_warning_step": step,
            "last_expiry_warning_at": datetime.now(timezone.utc).isoformat(),
        }})
        sent += 1
    return {"warned": sent}


def _strip_html(html: str) -> str:
    """Readable text out of a page, without pulling in a parser."""
    import re as _re
    html = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=_re.S | _re.I)
    html = _re.sub(r"<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"'))
    return _re.sub(r"\s+", " ", html).strip()


async def store_note(current_user: dict, body: str, url: Optional[str] = None,
                     title: Optional[str] = None, min_level: int = 5) -> dict:
    """Keep a typed note, or the text of a page someone handed over.

    The link is fetched once, here, because a person explicitly gave it — the
    assistant itself never browses.
    """
    text = body
    fetched_title = ""
    if url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "5812-Connect/1.0"})
                r.raise_for_status()
                page = r.text[:400000]
            import re as _re
            m = _re.search(r"<title[^>]*>(.*?)</title>", page, _re.S | _re.I)
            fetched_title = _strip_html(m.group(1))[:160] if m else ""
            text = f"{body}\n\nFrom {url}:\n{_strip_html(page)[:18000]}"
        except Exception as e:
            logger.warning(f"Could not read {url}: {e}")
            text = f"{body}\n\n(The page at {url} could not be read when it was filed.)"
    doc_id = f"odoc_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    import re as _re2
    first = _re2.split(r"(?<=[.!?])\s", body.strip())[0] if body.strip() else ""
    auto = (first if len(first) <= 70 else first[:67].rsplit(" ", 1)[0] + "…") or "Note"
    doc = {
        "id": doc_id,
        "title": (title or fetched_title or auto[:1].upper() + auto[1:])[:200],
        "doc_type": "note",
        "issuer": url or "",
        "reference": "",
        "issued_on": now[:10],
        "expires_on": "",
        "summary": body[:600],
        "tags": [],
        "notes": "",
        "text": text[:20000],
        "min_level": int(min_level),
        "file_url": "",
        "filename": "",
        "mime": "text/plain",
        "size": len(text),
        "source": "note" if not url else "link",
        "source_url": url or "",
        "location_id": current_user.get("location_id"),
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
        "created_at": now,
    }
    await db.org_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    doc.pop("text", None)
    await _audit(current_user["id"], "create", "org_document", doc_id, {"kind": doc["source"], "title": doc["title"]})
    return doc


@router.post("/notes")
async def add_note(data: dict, current_user: dict = Depends(require_manager)):
    """Feed the assistant something that isn't a file: a note or a link.

    Body: { text, url?, title?, min_level? }
    """
    body = (data.get("text") or "").strip()
    url = (data.get("url") or "").strip() or None
    if not body and not url:
        raise HTTPException(status_code=400, detail="Give me a note or a link to remember")
    level = int(data.get("min_level") or 5)
    if level not in VISIBILITY_LEVELS:
        raise HTTPException(status_code=400, detail="Pick who may see this note")
    return await store_note(current_user, body or f"Saved link: {url}", url=url,
                            title=data.get("title"), min_level=level)
