"""Receipt scanning — snap a receipt, get back a draft ledger entry.

No AI here — pure OCR (Tesseract) + regex logic. The user was explicit: the
goal is a deterministic "reads the vendor/date/amount and drops a draft JE
that finance can double-check", not a fuzzy LLM guess.

Flow:
  1) Client POSTs an image (or PDF) as multipart form.
  2) Tesseract lifts text.
  3) Regex passes extract vendor name, date, currency, and total.
  4) A DRAFT journal entry is created with:
     - Debit  5900 Other Expenses (or user-provided expense account)
     - Credit 1010 Bank — Operating (or user-provided cash/bank account)
     - status = 'draft', needs_review = True
  5) API returns both the parse result AND the created JE id so the client
     can open the finance-reviewer page.

Finance reviewers open the JE, adjust the account codes if the regex guessed
the wrong bucket, and flip status to posted.
"""
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from deps import db, require_staff, logger

from ._common import post_journal_entry, get_account_by_code, reverse_journal_entry

router = APIRouter(prefix="/api/finance/receipts", tags=["finance"])

# ─── Extraction rules ────────────────────────────────────────
# Ordered from most specific → least specific so the first hit wins.
AMOUNT_PATTERNS = [
    # "Total: 12,345.67" / "TOTAL DUE 12,345" / "Amount Paid  UGX 25,000"
    r"(?:total(?:\s+due|\s+paid|\s+amount)?|amount(?:\s+paid|\s+due)?|balance|grand\s+total)\s*[:\-]?\s*(?:[A-Z]{3}\s*)?([0-9]{1,3}(?:[,\.\s][0-9]{3})*(?:[\.,][0-9]{1,2})?)",
    # "Paid  25000"
    r"paid\s*[:\-]?\s*(?:[A-Z]{3}\s*)?([0-9]{1,3}(?:[,\.\s][0-9]{3})*(?:[\.,][0-9]{1,2})?)",
]
CURRENCY_PATTERNS = [
    r"\b(UGX|USD|KES|EUR|GBP|ZAR|TZS|RWF|BIF|SSP)\b",
    r"(sh|shs|shillings?|dollars?|pounds?|euros?)",
]
DATE_PATTERNS = [
    # 2026-02-05  or  05/02/2026  or  05-Feb-2026  or  Feb 05, 2026
    r"(20\d{2})[\-/](0?[1-9]|1[0-2])[\-/](0?[1-9]|[12]\d|3[01])",
    r"(0?[1-9]|[12]\d|3[01])[\-/](0?[1-9]|1[0-2])[\-/](20\d{2})",
    r"(0?[1-9]|[12]\d|3[01])[\-\s]([A-Za-z]{3,9})[\-\s,]+(20\d{2})",
    r"([A-Za-z]{3,9})\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2})",
]
MONTH_MAP = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
             "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
             "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
             "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
CURRENCY_ALIASES = {"sh": "UGX", "shs": "UGX", "shilling": "UGX", "shillings": "UGX",
                    "dollar": "USD", "dollars": "USD", "pound": "GBP", "pounds": "GBP",
                    "euro": "EUR", "euros": "EUR"}


def _parse_amount(m: str) -> float:
    """'12,345.67' / '12.345,67' / '12 345.67' → 12345.67."""
    s = m.strip()
    # If a period AND comma both appear, whichever comes last is the decimal.
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        # If only a comma at the tail with 1-2 digits, treat as decimal.
        if re.search(r",\d{1,2}$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(text: str) -> Optional[str]:
    """First date-shaped substring wins. Returns YYYY-MM-DD or None."""
    for pat in DATE_PATTERNS:
        m = re.search(pat, text)
        if not m:
            continue
        groups = list(m.groups())
        try:
            # Normalise to (y, m, d)
            if len(groups[0]) == 4 and groups[0].isdigit():
                y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
            elif len(groups[2]) == 4 and groups[2].isdigit():
                if groups[1].isalpha():
                    y = int(groups[2]); mo = MONTH_MAP.get(groups[1].lower())
                    d = int(groups[0])
                else:
                    d, mo, y = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                y = int(groups[2]); mo = MONTH_MAP.get(groups[0].lower())
                d = int(groups[1])
            if mo and 1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2099:
                return f"{y:04d}-{mo:02d}-{d:02d}"
        except (ValueError, KeyError, TypeError):
            continue
    return None


def _guess_vendor(text: str) -> str:
    """First non-empty line that isn't a number/date is our vendor guess."""
    for raw in text.splitlines()[:8]:
        line = raw.strip()
        if len(line) < 3:
            continue
        # Skip obvious money / date / phone lines
        if re.fullmatch(r"[\d\s\.,\-/:]+", line):
            continue
        if re.match(r"^(tel|phone|fax|email|http|www|receipt|invoice|date|time|no\.)", line, re.I):
            continue
        return line[:80]
    return ""


def _extract_currency(text: str) -> str:
    for pat in CURRENCY_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            code = m.group(1).upper()
            return CURRENCY_ALIASES.get(code.lower(), code)
    return "UGX"


def _extract_amount(text: str) -> float:
    for pat in AMOUNT_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            amt = _parse_amount(m.group(1))
            if amt > 0:
                return amt
    # Last resort: biggest money-shaped number on the receipt
    candidates = re.findall(r"([0-9]{1,3}(?:[,\.\s][0-9]{3}){1,3}(?:[\.,][0-9]{1,2})?)", text)
    biggest = 0.0
    for c in candidates:
        v = _parse_amount(c)
        if v > biggest:
            biggest = v
    return biggest


def _ocr(image_bytes: bytes, content_type: str) -> str:
    """Run Tesseract. Import inline so a missing binary just gives a nicer error."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"OCR libraries missing: {e}. Install tesseract-ocr and pytesseract.")
    # PDFs — grab page 1 as a PIL image
    if content_type == "application/pdf":
        try:
            from pdf2image import convert_from_bytes
            pages = convert_from_bytes(image_bytes, first_page=1, last_page=1, dpi=200)
            if not pages:
                raise HTTPException(status_code=400, detail="Could not render PDF")
            img = pages[0]
        except ImportError:
            raise HTTPException(status_code=500, detail="pdf2image not installed — send an image instead")
    else:
        img = Image.open(io.BytesIO(image_bytes))
    try:
        return pytesseract.image_to_string(img)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")


@router.post("/scan")
async def scan_receipt(
    file: UploadFile = File(...),
    expense_account_id: Optional[str] = Form(None),
    paid_from_account_id: Optional[str] = Form(None),
    location_id: Optional[str] = Form(None),
    current_user: dict = Depends(require_staff),
):
    """Upload a receipt image/PDF. Runs OCR + regex extraction and drops a
    DRAFT journal entry that finance reviewers can approve/edit.

    Form fields:
      file                  — image (jpg/png/webp) or PDF, max ~10 MB
      expense_account_id?   — override the auto-picked expense account
      paid_from_account_id? — override the auto-picked cash/bank account
      location_id?          — tag the JE to a specific location/sub-location

    Response:
      { extracted: { vendor, date, amount, currency, raw_text },
        journal_entry: { … draft JE with needs_review=True … } }
    """
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    location_id = (location_id or current_user.get("active_campus_id") or "").strip()
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required — pick a campus or sub-location before scanning the receipt")

    # Keep the file. Without this there was nothing to look at in the review
    # queue — reviewers had to trust the OCR blind (iter350).
    receipt_url = None
    try:
        from upload_helper import save_upload
        ext = (file.filename or "receipt").rsplit(".", 1)[-1][:8] if "." in (file.filename or "") else "jpg"
        receipt_url = await save_upload(
            "receipts", f"rcp-{uuid.uuid4().hex[:10]}.{ext}",
            content, file.content_type or "application/octet-stream",
        )
    except Exception as e:
        logger.warning(f"[receipts] could not store the receipt image: {e}")

    text = _ocr(content, file.content_type or "")
    extracted = {
        "vendor": _guess_vendor(text),
        "date": _parse_date(text) or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "amount": _extract_amount(text),
        "currency": _extract_currency(text),
        "raw_text": text[:2000],
        "receipt_url": receipt_url,
        "file_name": file.filename,
    }
    if extracted["amount"] <= 0:
        # Still return the parse (and the stored image) so the user can key it
        # in manually without re-uploading.
        return {"extracted": extracted, "journal_entry": None,
                "hint": "Amount not detected — enter manually via the Record expense dialog."}

    # Pick default accounts if the caller didn't specify
    expense_acct = None
    if expense_account_id:
        expense_acct = await db.finance_chart_of_accounts.find_one({"id": expense_account_id}, {"_id": 0})
    if not expense_acct:
        expense_acct = await get_account_by_code("5900")  # Other Expenses (seed)
    if not expense_acct:
        raise HTTPException(status_code=400, detail="No default expense account found — seed the Chart of Accounts first.")

    cash_acct = None
    if paid_from_account_id:
        cash_acct = await db.finance_chart_of_accounts.find_one({"id": paid_from_account_id}, {"_id": 0})
    if not cash_acct:
        cash_acct = (await get_account_by_code("1010")) or (await get_account_by_code("1000"))
    if not cash_acct:
        raise HTTPException(status_code=400, detail="No default cash/bank account found — seed the Chart of Accounts first.")

    je = await post_journal_entry(
        date=extracted["date"],
        description=f"Receipt: {extracted['vendor'] or 'Vendor unknown'}",
        lines=[
            {"account_id": expense_acct["id"], "account_code": expense_acct["code"],
             "account_name": expense_acct["name"], "debit": extracted["amount"], "credit": 0,
             "memo": (extracted["vendor"] or "")[:120]},
            {"account_id": cash_acct["id"], "account_code": cash_acct["code"],
             "account_name": cash_acct["name"], "debit": 0, "credit": extracted["amount"],
             "memo": (extracted["vendor"] or "")[:120]},
        ],
        source="receipt_scan",
        reference=f"RCP-{uuid.uuid4().hex[:8]}",
        location_id=location_id,
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )
    # Flag as needing finance review so it shows up in the review queue.
    receipt_meta = {
        "needs_review": True,
        "review_reason": "receipt-scan",
        "receipt_url": receipt_url,
        "receipt_name": file.filename,
        "receipt_vendor": extracted["vendor"],
        "receipt_ocr_amount": extracted["amount"],
        "ocr_text": text[:4000],
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
    }
    await db.finance_journal_entries.update_one({"id": je["id"]}, {"$set": receipt_meta})
    je.update(receipt_meta)

    logger.info(f"[receipts] Draft JE {je['id']} posted from scan by {current_user.get('email')}")
    return {"extracted": extracted, "journal_entry": je}


@router.get("/review-queue")
async def list_review_queue(
    current_user: dict = Depends(require_staff),
):
    """List all draft JEs still flagged `needs_review=True` — finance
    reviewers work through this queue to approve or edit."""
    rows = await db.finance_journal_entries.find(
        {"needs_review": True, "reversed": {"$ne": True}, "rejected": {"$ne": True}}, {"_id": 0},
    ).sort([("date", -1), ("created_at", -1)]).limit(200).to_list(200)
    for r in rows:
        r["uploaded_by_name"] = r.get("uploaded_by_name") or r.get("created_by_name") or ""
        r["has_receipt"] = bool(r.get("receipt_url"))
    return rows


REJECT_REASONS = {
    "not_clear": "Not clear — please re-upload",
    "not_approved": "Not an approved purchase",
    "duplicate": "Duplicate receipt",
    "wrong_campus": "Wrong campus or department",
    "other": "Other",
}


@router.get("/reject-reasons")
async def reject_reasons(current_user: dict = Depends(require_staff)):
    """The canned rejection reasons the review UI offers."""
    return [{"code": k, "label": v} for k, v in REJECT_REASONS.items()]


class ReceiptEdit(BaseModel):
    """What a reviewer is allowed to correct when the OCR got it wrong."""
    date: Optional[str] = None
    description: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    expense_account_id: Optional[str] = None
    paid_from_account_id: Optional[str] = None
    memo: Optional[str] = None


@router.put("/{je_id}")
async def edit_receipt_je(je_id: str, data: ReceiptEdit, current_user: dict = Depends(require_staff)):
    """Correct a scanned receipt: amount, date, vendor, description, accounts.

    A posted entry is never mutated in place — the original is reversed and a
    corrected one posted, so the ledger keeps the full story. The receipt image
    and review flag follow the new entry.
    """
    je = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Entry not found")
    if je.get("reversed"):
        raise HTTPException(status_code=400, detail="That entry was already reversed")

    lines = je.get("lines") or []
    debit_line = next((ln for ln in lines if (ln.get("debit") or 0) > 0), None)
    credit_line = next((ln for ln in lines if (ln.get("credit") or 0) > 0), None)
    if not debit_line or not credit_line:
        raise HTTPException(status_code=400, detail="This entry isn't a simple receipt — edit it in the journal instead")

    amount = float(data.amount if data.amount is not None else (debit_line.get("debit") or 0))
    vendor = (data.vendor if data.vendor is not None else je.get("receipt_vendor")) or ""
    memo = (data.memo if data.memo is not None else vendor)[:120]

    async def _acct(acct_id: Optional[str], fallback: dict) -> dict:
        if not acct_id:
            return fallback
        a = await db.finance_chart_of_accounts.find_one({"id": acct_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=400, detail="Unknown account")
        return {"account_id": a["id"], "account_code": a["code"], "account_name": a["name"]}

    dr = await _acct(data.expense_account_id, {k: debit_line.get(k) for k in ("account_id", "account_code", "account_name")})
    cr = await _acct(data.paid_from_account_id, {k: credit_line.get(k) for k in ("account_id", "account_code", "account_name")})

    await reverse_journal_entry(
        je_id, reason=f"Corrected by {current_user.get('name') or 'reviewer'}", current_user=current_user)

    new_je = await post_journal_entry(
        date=data.date or je.get("date"),
        description=data.description or f"Receipt: {vendor or 'Vendor unknown'}",
        lines=[
            {**dr, "debit": amount, "credit": 0, "memo": memo},
            {**cr, "debit": 0, "credit": amount, "memo": memo},
        ],
        source="receipt_scan",
        reference=je.get("reference"),
        location_id=je.get("location_id"),
        created_by=current_user["id"],
        created_by_name=current_user.get("name"),
    )
    carry = {k: je.get(k) for k in ("receipt_url", "receipt_name", "ocr_text", "uploaded_by",
                                    "uploaded_by_name", "receipt_ocr_amount") if je.get(k)}
    await db.finance_journal_entries.update_one({"id": new_je["id"]}, {"$set": {
        **carry,
        "receipt_vendor": vendor,
        "needs_review": True,
        "review_reason": "receipt-scan",
        "corrected_from": je_id,
        "corrected_by": current_user["id"],
        "corrected_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"ok": True, "journal_entry_id": new_je["id"], "replaces": je_id}


@router.put("/{je_id}/reject")
async def reject_receipt_je(je_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Reject a scanned receipt: reverse the draft and tell the uploader why."""
    reason_code = (data.get("reason") or "").strip()
    note = (data.get("note") or "").strip()[:500]
    if reason_code not in REJECT_REASONS:
        raise HTTPException(status_code=400, detail="Pick a rejection reason")
    if reason_code == "other" and not note:
        raise HTTPException(status_code=400, detail="Add a note explaining the rejection")

    je = await db.finance_journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Entry not found")
    label = REJECT_REASONS[reason_code]

    if not je.get("reversed"):
        await reverse_journal_entry(je_id, reason=f"Receipt rejected: {label}", current_user=current_user)

    await db.finance_journal_entries.update_one({"id": je_id}, {"$set": {
        "needs_review": False,
        "rejected": True,
        "rejected_reason": reason_code,
        "rejected_reason_label": label,
        "rejected_note": note,
        "rejected_by": current_user["id"],
        "rejected_by_name": current_user.get("name", ""),
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }})

    uploader = je.get("uploaded_by") or je.get("created_by")
    if uploader and uploader != current_user["id"]:
        try:
            from routers.notifications import create_notification
            await create_notification(
                title="Receipt rejected",
                message=f"{label}{(' — ' + note) if note else ''}. Re-upload it from the dashboard when you can.",
                user_id=uploader, notif_type="finance", link="/finance?tab=receipts",
            )
        except Exception as e:
            logger.warning(f"[receipts] rejection notice skipped: {e}")
    return {"ok": True, "reason": label}


@router.put("/{je_id}/approve")
async def approve_receipt_je(je_id: str, current_user: dict = Depends(require_staff)):
    """Finance reviewer signed off — clear the needs_review flag."""
    r = await db.finance_journal_entries.update_one(
        {"id": je_id}, {"$set": {"needs_review": False, "reviewed_by": current_user["id"], "reviewed_at": datetime.now(timezone.utc).isoformat()}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
