"""CSV file upload and data import routes"""
from fastapi import APIRouter, Depends, UploadFile, File
from deps import db, get_current_user, require_manager, _audit, logger
from datetime import datetime, timezone
import uuid
import csv
import io

router = APIRouter(prefix="/api", tags=["import"])


# ========== JSON IMPORT ==========

@router.post("/import/children-parents")
async def import_children_parents(data: dict, current_user: dict = Depends(get_current_user)):
    rows = data.get("rows", [])
    imported_children = 0
    imported_parents = 0
    imported_families = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            fname = row.get("first_name", "").strip()
            lname = row.get("last_name", "").strip()
            if not fname:
                errors.append(f"Row {i+1}: first_name required")
                continue
            child_name = f"{fname} {lname}".strip()
            family_name = row.get("family_name", lname).strip() or lname

            family = await db.families.find_one({"name": family_name})
            if not family:
                family_id = f"fam_{str(uuid.uuid4())[:8]}"
                family = {"id": family_id, "name": family_name, "members": [], "created_at": datetime.now(timezone.utc).isoformat()}
                await db.families.insert_one(family)
                imported_families += 1
            else:
                family_id = family["id"]

            child_id = f"m_{str(uuid.uuid4())[:8]}"
            child_doc = {
                "id": child_id, "name": child_name, "role": "Child", "group": row.get("grade", ""),
                "date_of_birth": row.get("date_of_birth", ""), "family_id": family_id,
                "allergies": row.get("allergies", ""), "medical_notes": row.get("medical_notes", ""),
                "special_needs": row.get("special_needs", ""), "status": "active",
                "join_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.members.insert_one(child_doc)
            imported_children += 1

            father_name = row.get("fathers_names", "").strip()
            if father_name:
                existing_father = await db.members.find_one({"name": father_name, "is_parent": True})
                if not existing_father:
                    father_doc = {
                        "id": f"m_{str(uuid.uuid4())[:8]}", "name": father_name, "phone": row.get("fathers_phone", ""),
                        "role": "Parent", "is_parent": True, "gender": "male", "family_id": family_id,
                        "status": "active", "join_date": datetime.now(timezone.utc).date().isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.members.insert_one(father_doc)
                    imported_parents += 1

            mother_name = row.get("mothers_names", "").strip()
            if mother_name:
                existing_mother = await db.members.find_one({"name": mother_name, "is_parent": True})
                if not existing_mother:
                    mother_doc = {
                        "id": f"m_{str(uuid.uuid4())[:8]}", "name": mother_name, "phone": row.get("mothers_phone", ""),
                        "role": "Parent", "is_parent": True, "gender": "female", "family_id": family_id,
                        "status": "active", "join_date": datetime.now(timezone.utc).date().isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db.members.insert_one(mother_doc)
                    imported_parents += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "csv_import", f"{imported_children}_children_{imported_parents}_parents")
    return {"imported_children": imported_children, "imported_parents": imported_parents, "imported_families": imported_families, "errors": errors}


@router.post("/import/staff")
async def import_staff(data: dict, current_user: dict = Depends(require_manager)):
    rows = data.get("rows", [])
    imported = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            name = row.get("name", "").strip()
            if not name:
                errors.append(f"Row {i+1}: name required")
                continue
            email = row.get("email", "").strip().lower()
            if email:
                existing = await db.members.find_one({"email": email})
                if existing:
                    errors.append(f"Row {i+1}: Email {email} already exists")
                    continue
            doc = {
                "id": f"m_{str(uuid.uuid4())[:8]}", "name": name, "email": email,
                "phone": row.get("phone", ""), "national_id": row.get("national_id", ""),
                "role": row.get("role", "Staff"), "department": row.get("department", ""),
                "group": "", "gender": "", "status": "active",
                "join_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.members.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "staff_import", f"{imported}_staff")
    return {"imported": imported, "errors": errors, "total": len(rows)}


# ========== REAL CSV FILE UPLOAD ==========

@router.post("/import/csv/members")
async def import_csv_members_file(file: UploadFile = File(...), current_user: dict = Depends(require_manager)):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    errors = []
    for i, row in enumerate(reader):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {i+1}: name required")
                continue
            email = (row.get("email") or "").strip().lower()
            if email:
                existing = await db.members.find_one({"email": email})
                if existing:
                    errors.append(f"Row {i+1}: Email {email} exists")
                    continue
            doc = {
                "id": f"m_{str(uuid.uuid4())[:8]}",
                "name": name,
                "email": email,
                "phone": (row.get("phone") or "").strip(),
                "national_id": (row.get("national_id") or "").strip(),
                "role": (row.get("role") or "Member").strip(),
                "group": (row.get("group") or "General").strip(),
                "gender": (row.get("gender") or "").strip().lower(),
                "department": (row.get("department") or "").strip(),
                "status": "active",
                "join_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.members.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    await _audit(current_user["id"], "create", "csv_file_import", f"{imported}_members")
    return {"imported": imported, "errors": errors}


@router.post("/import/csv/children-parents")
async def import_csv_children_parents_file(file: UploadFile = File(...), current_user: dict = Depends(require_manager)):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    result = await import_children_parents({"rows": rows}, current_user)
    return result


@router.post("/import/csv/staff")
async def import_csv_staff_file(file: UploadFile = File(...), current_user: dict = Depends(require_manager)):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    result = await import_staff({"rows": rows}, current_user)
    return result
