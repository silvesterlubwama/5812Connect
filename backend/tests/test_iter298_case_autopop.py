"""Iter 298 — Auto-populate case Family/Education/Medical from review forms.

Everything runs inside a single asyncio.run so we share deps.db's motor
client (which is bound to the first event loop it sees).
"""
import os
import sys
import uuid
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, "/app/backend")


async def _seed(db):
    child_id = f"ch_test_{uuid.uuid4().hex[:8]}"
    case_id = f"sc_test_{uuid.uuid4().hex[:8]}"
    await db.children.insert_one({
        "id": child_id, "name": "Auto Pop Child", "location_id": "loc_test",
        "date_of_birth": "2015-01-01",
    })
    await db.social_cases.insert_one({
        "id": case_id, "subject_id": child_id, "subject_kind": "child",
        "subject_name": "Auto Pop Child", "status": "active",
        "category": "welfare_support", "risk_level": "low",
        "location_id": "loc_test",
        "family": {}, "education": {}, "medical": {},
    })
    return child_id, case_id


async def _cleanup(db, child_id, case_id):
    await db.children.delete_one({"id": child_id})
    await db.social_cases.delete_one({"id": case_id})


async def _welfare_case(db, _apply):
    child_id, case_id = await _seed(db)
    try:
        fields = {
            "guardians": ["Aunt Mary", "Grandmother Sarah"],
            "siblings": 3,
            "household_income": "casual labour, ~200k UGX/month",
            "family_notes": "Single-guardian household.",
            "caregiver_name": "Aunt Mary",
            "caregiver_relationship": "aunt",
            "village_parish": "Kyebando",
            "district": "Kampala",
        }
        await _apply(child_id, "welfare_visit",
                    {"review_date": "2026-02-10"}, fields, "rev_abc123")
        case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
        fam = case["family"]
        assert fam["guardians"] == ["Aunt Mary", "Grandmother Sarah"]
        assert fam["siblings"] == 3
        assert fam["primary_caregiver"] == "Aunt Mary"
        assert fam["village_parish"] == "Kyebando"
        srcs = fam["_field_sources"]
        for k in ("guardians", "siblings", "household_income", "notes",
                  "primary_caregiver", "village_parish", "district"):
            assert srcs[k]["review_id"] == "rev_abc123", f"missing source for {k}"
            assert srcs[k]["kind"] == "welfare_visit"
        assert len(fam["_change_log"]) == 1
        assert "guardians" in fam["_change_log"][0]["changed"]
        assert fam["_last_source_review_id"] == "rev_abc123"
    finally:
        await _cleanup(db, child_id, case_id)


async def _school_case(db, _apply):
    child_id, case_id = await _seed(db)
    try:
        await db.social_cases.update_one(
            {"id": case_id},
            {"$set": {"education": {"grade": "P3", "school_name": "Old School"}}},
        )
        fields = {
            "class_grade": "P4",
            "school": "New Academy",
            "term": "T1 2026",
            "teacher_name": "Ms. Nakato",
            "attendance_discipline": {"attendance_pct": 88.5, "discipline": "good"},
            "academic_performance": {"overall": "improving", "position_in_class": "12/40"},
        }
        await _apply(child_id, "school_progress",
                    {"review_date": "2026-02-11"}, fields, "rev_sch456")
        case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
        edu = case["education"]
        assert edu["grade"] == "P4"
        assert edu["school_name"] == "New Academy"
        assert edu["attendance_pct"] == 88.5
        log = edu["_change_log"]
        assert len(log) == 1
        changes = {c["field"]: (c["from"], c["to"]) for c in log[0]["changes"]}
        assert changes["grade"] == ("P3", "P4")
        assert changes["school_name"] == ("Old School", "New Academy")
    finally:
        await _cleanup(db, child_id, case_id)


async def _medical_case(db, _apply):
    child_id, case_id = await _seed(db)
    try:
        fields = {
            "medical_history": {
                "asthma": {"present": True},
                "sickle_cell": {"present": True},
                "other": {"specify": "seasonal hay fever"},
            },
            "known_allergies": "peanuts, penicillin",
            "current_medication": "salbutamol inhaler PRN",
            "nutritional_status": "fair",
            "diagnosis": "Mild persistent asthma; sickle-cell trait.",
            "practitioner": {"facility": "St. Mary's Clinic"},
        }
        await _apply(child_id, "medical_exam",
                    {"review_date": "2026-02-12"}, fields, "rev_med789")
        case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
        med = case["medical"]
        assert "asthma" in med["conditions"]
        assert "sickle_cell" in med["conditions"]
        assert "seasonal hay fever" in med["conditions"]
        assert med["allergies"] == ["peanuts", "penicillin"]
        assert med["nutritional_status"] == "fair"
        assert med["primary_doctor"] == "St. Mary's Clinic"
        assert med["_field_sources"]["conditions"]["review_id"] == "rev_med789"
    finally:
        await _cleanup(db, child_id, case_id)


async def _idempotent_case(db, _apply):
    child_id, case_id = await _seed(db)
    try:
        fields = {"siblings": 2, "household_income": "casual"}
        await _apply(child_id, "welfare_visit", {"review_date": "2026-02-10"}, fields, "rev_1")
        await _apply(child_id, "welfare_visit", {"review_date": "2026-02-15"}, fields, "rev_2")
        case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
        fam = case["family"]
        assert fam["_field_sources"]["siblings"]["review_id"] == "rev_2"
        assert fam["_last_source_review_id"] == "rev_2"
        assert len(fam["_change_log"]) == 2
        assert fam["siblings"] == 2
    finally:
        await _cleanup(db, child_id, case_id)


def test_iter298_case_autopop_all_scenarios():
    """Single test drives all four scenarios in one event loop so deps.db's
    motor client stays valid across the whole run (pytest-asyncio not
    configured in this project — this pattern matches test_iter293 etc.)."""
    async def _run():
        # Force a fresh motor client bound to THIS loop so co-running with
        # other iter tests that use deps.db doesn't hit "Event loop is closed".
        import deps
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(deps.MONGO_URL if hasattr(deps, "MONGO_URL") else os.environ["MONGO_URL"])
        deps.db = client[os.environ["DB_NAME"]]
        db = deps.db
        from routers.social_review_forms.child_sync import _apply_review_to_case
        await _welfare_case(db, _apply_review_to_case)
        await _school_case(db, _apply_review_to_case)
        await _medical_case(db, _apply_review_to_case)
        await _idempotent_case(db, _apply_review_to_case)
    asyncio.run(_run())
