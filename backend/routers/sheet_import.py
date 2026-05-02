"""Google-Sheet financial import — extracted from financial.py"""
from fastapi import APIRouter, Depends, HTTPException
from deps import db, require_manager, _audit
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["sheet_import"])


@router.post("/financial/import-sheet")
async def import_google_sheet_financial(data: dict, current_user: dict = Depends(require_manager)):
    """Bulk-import expenses (or donations) from a Google-Sheet-style CSV/JSON.
    Body: { type: 'expense'|'donation', rows: [{date, vendor, purpose, receipt_number, account, department, budget_category, amount_ugx, usd}], location_id?, default_status?: 'pending'|'approved' }
    """
    entry_type = (data.get("type") or "expense").lower()
    rows = data.get("rows") or []
    default_status = data.get("default_status") or "pending"
    target_loc = data.get("location_id") or current_user.get("active_campus_id") or current_user.get("location_id") or ""
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided")
    created = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            # Normalize keys — accept spreadsheet column names too
            date_val = (row.get("date") or row.get("Date") or "").strip()
            # Support DD/MM or DD/MM/YY or DD/MM/YYYY — normalize to YYYY-MM-DD
            if date_val:
                parts = date_val.replace("-", "/").split("/")
                try:
                    if len(parts) == 3:
                        d, m, y = parts
                        if len(y) == 2:
                            y = "20" + y
                        date_val = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                    elif len(parts) == 2:
                        d, m = parts
                        y = str(datetime.now(timezone.utc).year)
                        date_val = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                except Exception:
                    pass
            amount_raw = row.get("amount") or row.get("Amount") or row.get("TOTAL UGX") or row.get("total_ugx") or 0
            if isinstance(amount_raw, str):
                amount_raw = amount_raw.replace("UGX", "").replace(",", "").replace(" ", "").strip() or "0"
            amount = float(amount_raw)
            if amount <= 0:
                skipped += 1
                continue
            vendor = (row.get("vendor") or row.get("Vendor") or row.get("Donor") or row.get("donor_name") or "").strip()
            purpose = (row.get("purpose") or row.get("Purpose/Beneficiary/Notes") or row.get("notes") or row.get("Notes") or "").strip()
            receipt_number = (row.get("receipt_number") or row.get("Reff./ Reciept#") or row.get("Reff./Receipt#") or row.get("Receipt#") or "").strip()
            account = (row.get("account") or row.get("ACCOUNT") or "").strip()
            department = (row.get("department") or row.get("Department") or "").strip()
            budget = (row.get("budget_category") or row.get("Budget") or row.get("category") or row.get("Category") or "general").strip()
            usd_raw = row.get("usd_equivalent") or row.get("USD") or row.get("usd") or None
            usd_val = None
            if usd_raw:
                try:
                    usd_val = float(str(usd_raw).replace("$", "").replace(",", "").strip())
                except Exception:
                    usd_val = None
            title = purpose or vendor or f"Imported row {i+1}"
            if entry_type == "expense":
                doc = {
                    "id": f"exp_{uuid.uuid4().hex[:8]}",
                    "title": title,
                    "amount": amount,
                    "currency": row.get("currency") or "UGX",
                    "category": budget or "general",
                    "date": date_val or datetime.now(timezone.utc).isoformat()[:10],
                    "notes": purpose,
                    "vendor": vendor,
                    "purpose": purpose,
                    "receipt_number": receipt_number,
                    "account": account,
                    "department": department,
                    "budget_category": budget,
                    "usd_equivalent": usd_val,
                    "location_id": target_loc,
                    "status": default_status,
                    "source": "sheet_import",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": current_user["id"],
                }
                await db.expenses.insert_one(doc)
            else:
                # donation
                doc = {
                    "id": f"don_{uuid.uuid4().hex[:8]}",
                    "donor_name": vendor or "Anonymous",
                    "amount": amount,
                    "currency": row.get("currency") or "UGX",
                    "type": budget or "donation",
                    "category": budget,
                    "department": department,
                    "date": date_val or datetime.now(timezone.utc).isoformat()[:10],
                    "notes": purpose,
                    "receipt_number": receipt_number,
                    "location_id": target_loc,
                    "source": "sheet_import",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": current_user["id"],
                }
                await db.donations.insert_one(doc)
            created += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)[:100]}")
            skipped += 1
    await _audit(current_user["id"], "create", "sheet_import", f"{entry_type}_{created}")
    return {"created": created, "skipped": skipped, "errors": errors[:20], "type": entry_type}
