"""Seed endpoints — dev/setup data population. Extracted from server.py."""
from fastapi import APIRouter
from datetime import datetime, timezone
from deps import db, hash_password
import uuid

router = APIRouter(prefix="/api", tags=["seed"])


@router.post("/seed")
async def seed_data():
    existing_admin = await db.users.find_one({"email": "admin@5812global.org"})
    if not existing_admin:
        admin = {
            "id": str(uuid.uuid4()), "name": "Admin User", "email": "admin@5812global.org",
            "phone": "+256 800 5812", "password_hash": hash_password("Admin@1234"),
            "role": "admin", "status": "active", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(admin)

    member_count = await db.members.count_documents({})
    if member_count == 0:
        members = [
            {"id": "mem_001", "name": "Alice Namukasa", "email": "alice@example.com", "phone": "+256 700 123456", "national_id": "CM900001000XXXX", "role": "Member", "status": "active", "join_date": "2024-01-15", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_002", "name": "Brian Ssekitto", "email": "brian@example.com", "phone": "+256 752 234567", "national_id": "CM850002000XXXX", "role": "Staff", "status": "active", "join_date": "2023-06-10", "group": "Leadership", "gender": "male", "pin": "1234", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_003", "name": "Catherine Nakato", "email": "catherine@example.com", "phone": "+256 781 345678", "national_id": "CM920003000XXXX", "role": "Member", "status": "active", "join_date": "2024-03-20", "group": "Women", "gender": "female", "pin": "5678", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_004", "name": "David Kiggundu", "email": "david@example.com", "phone": "+256 706 456789", "national_id": "CM880004000XXXX", "role": "Volunteer", "status": "active", "join_date": "2023-11-05", "group": "Volunteers", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_005", "name": "Esther Namirembe", "email": "esther@example.com", "phone": "+256 773 567890", "national_id": "CM950005000XXXX", "role": "Member", "status": "inactive", "join_date": "2022-08-30", "group": "Youth", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_006", "name": "Francis Tumwesigye", "email": "francis@example.com", "phone": "+256 712 678901", "national_id": "CM780006000XXXX", "role": "Leader", "status": "active", "join_date": "2021-05-12", "group": "Leadership", "gender": "male", "is_donor": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_007", "name": "Grace Akello", "email": "grace@example.com", "phone": "+256 756 789012", "national_id": "CM960007000XXXX", "role": "Member", "status": "active", "join_date": "2024-07-01", "group": "Youth", "gender": "female", "is_parent": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_008", "name": "Henry Wasswa", "email": "henry@example.com", "phone": "+256 701 890123", "national_id": "CM820008000XXXX", "role": "Staff", "status": "active", "join_date": "2023-01-18", "group": "Admin", "gender": "male", "pin": "9012", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_009", "name": "Irene Nabatanzi", "email": "irene@example.com", "phone": "+256 784 901234", "national_id": "CM990009000XXXX", "role": "Member", "status": "active", "join_date": "2025-01-10", "group": "Women", "gender": "female", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "mem_010", "name": "Joseph Muwanguzi", "email": "joseph@example.com", "phone": "+256 715 012345", "national_id": "CM870010000XXXX", "role": "Volunteer", "status": "inactive", "join_date": "2022-04-22", "group": "Volunteers", "gender": "male", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.members.insert_many(members)

    event_count = await db.events.count_documents({})
    if event_count == 0:
        events = [
            {"id": "evt_001", "title": "Sunday Service", "type": "service", "status": "upcoming", "date": "2026-04-06", "time": "09:00", "end_time": "11:30", "location": "58:12 Global Centre", "capacity": 300, "registered": 212, "description": "Weekly Sunday worship service.", "is_public": True, "is_free": True, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_002", "title": "Youth Leadership Summit", "type": "conference", "status": "upcoming", "date": "2026-04-12", "time": "10:00", "end_time": "17:00", "location": "Kampala Conference Hall", "capacity": 100, "registered": 87, "description": "Annual leadership development summit.", "is_public": True, "is_free": False, "price": 25000, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_003", "title": "Community Outreach", "type": "community", "status": "upcoming", "date": "2026-04-19", "time": "08:00", "end_time": "14:00", "location": "Nakawa Market Area", "capacity": 50, "registered": 34, "description": "Community service outreach.", "is_public": False, "is_free": True, "visibility": "internal", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_004", "title": "Women in Faith Conference", "type": "conference", "status": "upcoming", "date": "2026-04-26", "time": "09:00", "end_time": "16:00", "location": "58:12 Global Centre", "capacity": 150, "registered": 102, "description": "Annual conference empowering women.", "is_public": True, "is_free": False, "price": 15000, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_005", "title": "Staff Meeting", "type": "meeting", "status": "upcoming", "date": "2026-04-02", "time": "14:00", "end_time": "16:00", "location": "Admin Block", "capacity": 20, "registered": 15, "description": "Monthly all-staff meeting.", "is_public": False, "is_free": True, "visibility": "internal", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_006", "title": "Easter Sunday Service", "type": "service", "status": "completed", "date": "2026-03-31", "time": "07:00", "end_time": "11:00", "location": "58:12 Global Centre", "capacity": 500, "registered": 487, "description": "Easter Sunday special service.", "is_public": True, "is_free": True, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "evt_007", "title": "QR Test Event", "type": "meeting", "status": "upcoming", "date": "2026-04-01", "time": "10:00", "end_time": "12:00", "location": "Tech Lab", "capacity": 100, "registered": 11, "description": "Event for testing QR code check-in.", "is_public": True, "is_free": True, "visibility": "external", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.events.insert_many(events)

    task_count = await db.tasks.count_documents({})
    if task_count == 0:
        tasks = [
            {"id": "task_001", "title": "Prepare Easter sermon notes", "description": "Compile sermon notes", "status": "done", "priority": "high", "assignee": "Brian Ssekitto", "due_date": "2026-03-30", "tags": ["sermon"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_002", "title": "Send membership renewal reminders", "description": "Email members expiring in April", "status": "in-progress", "priority": "high", "assignee": "Henry Wasswa", "due_date": "2026-04-05", "tags": ["membership"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_003", "title": "Set up Youth Summit registration", "description": "Configure online registration", "status": "in-progress", "priority": "medium", "assignee": "Alice Namukasa", "due_date": "2026-04-08", "tags": ["events"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_004", "title": "Update website event listings", "description": "Add April events to website", "status": "todo", "priority": "medium", "assignee": "Grace Akello", "due_date": "2026-04-10", "tags": ["website"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_005", "title": "Volunteer coordination for outreach", "description": "Assign volunteers to stations", "status": "todo", "priority": "high", "assignee": "David Kiggundu", "due_date": "2026-04-15", "tags": ["volunteers"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_006", "title": "Purchase office supplies", "description": "Order printer cartridges and stationery", "status": "todo", "priority": "low", "assignee": "Irene Nabatanzi", "due_date": "2026-04-20", "tags": ["admin"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_007", "title": "Finalize Women Conference speakers", "description": "Confirm all 5 speakers", "status": "in-progress", "priority": "high", "assignee": "Catherine Nakato", "due_date": "2026-04-12", "tags": ["events"], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "task_008", "title": "Monthly financial report", "description": "Compile March financial report", "status": "done", "priority": "high", "assignee": "Francis Tumwesigye", "due_date": "2026-04-05", "tags": ["finance"], "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.tasks.insert_many(tasks)

    venue_count = await db.venues.count_documents({})
    if venue_count == 0:
        venues = [
            {"id": "ven_001", "name": "Main Auditorium", "capacity": 500, "type": "auditorium", "available": True, "hourly_rate": None, "description": "Main worship hall with full AV system.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_002", "name": "Conference Room A", "capacity": 40, "type": "conference", "available": True, "hourly_rate": 20000, "description": "Small conference room with projector.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_003", "name": "Youth Hall", "capacity": 150, "type": "hall", "available": False, "hourly_rate": 50000, "description": "Large multipurpose hall.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ven_004", "name": "Prayer Garden", "capacity": 30, "type": "outdoor", "available": True, "hourly_rate": None, "description": "Peaceful outdoor garden space.", "location_id": "loc_001", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.venues.insert_many(venues)

    checkin_count = await db.checkins.count_documents({})
    if checkin_count == 0:
        checkins = [
            {"id": "ci_001", "member_id": "mem_001", "member_name": "Alice Namukasa", "type": "member", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "qr", "check_in_time": "2026-03-31T08:45:00Z", "source": "kiosk"},
            {"id": "ci_002", "member_id": "mem_002", "member_name": "Brian Ssekitto", "type": "staff", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "manual", "check_in_time": "2026-03-31T07:30:00Z", "source": "manual"},
            {"id": "ci_003", "member_id": None, "member_name": "Visitor - John Doe", "type": "visitor", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "manual", "check_in_time": "2026-03-31T09:05:00Z", "source": "kiosk"},
            {"id": "ci_004", "member_id": "mem_003", "member_name": "Catherine Nakato", "type": "member", "event_id": "evt_006", "event_name": "Easter Sunday Service", "method": "id", "check_in_time": "2026-03-31T09:10:00Z", "source": "kiosk"},
        ]
        await db.checkins.insert_many(checkins)

    return {"message": "Database seeded successfully", "admin_email": "admin@5812global.org", "admin_password": "Admin@1234"}


@router.post("/seed-extended")
async def seed_extended():
    product_count = await db.products.count_documents({})
    if product_count == 0:
        products = [
            {"id": "prod_001", "name": "4 Week Broiler Chicken", "price": 10000, "currency": "UGX", "stock": 198, "category": "Farm", "reorder_level": 20, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_002", "name": "Coffee", "price": 20000, "currency": "UGX", "stock": 0, "category": "Beverages", "reorder_level": 10, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_003", "name": "Eggs (Tray)", "price": 10000, "currency": "UGX", "stock": 0, "category": "Farm", "reorder_level": 15, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_004", "name": "Local Chicken", "price": 40000, "currency": "UGX", "stock": 20, "category": "Farm", "reorder_level": 5, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_005", "name": "2 Month Old Chicken", "price": 20000, "currency": "UGX", "stock": 20, "category": "Farm", "reorder_level": 10, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "prod_006", "name": "Tea T-Shirt", "price": 25000, "currency": "UGX", "stock": 100, "category": "Merchandise", "reorder_level": 15, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.products.insert_many(products)
    family_count = await db.families.count_documents({})
    if family_count == 0:
        families = [
            {"id": "fam_001", "family_name": "Nakato Family", "primary_contact_name": "Sarah Nakato", "primary_contact_email": "parent1@example.com", "primary_contact_phone": "+256 700 111001", "address": "Kampala", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "fam_002", "family_name": "Ssekitto Family", "primary_contact_name": "James Ssekitto", "primary_contact_email": "james@example.com", "primary_contact_phone": "+256 700 222002", "address": "Entebbe", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "fam_003", "family_name": "Kiggundu Family", "primary_contact_name": "Mary Kiggundu", "primary_contact_email": "mary@example.com", "primary_contact_phone": "+256 700 333003", "address": "Jinja", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.families.insert_many(families)
    child_count = await db.children.count_documents({})
    if child_count == 0:
        children = [
            {"id": "chd_001", "name": "Emma Nakato", "date_of_birth": "2016-03-15", "gender": "female", "family_id": "fam_001", "class_group": "Primary 4", "medical_notes": "Nut allergy - carry epipen", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_002", "name": "Daniel Nakato", "date_of_birth": "2018-07-22", "gender": "male", "family_id": "fam_001", "class_group": "Primary 2", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_003", "name": "Peter Ssekitto", "date_of_birth": "2015-11-08", "gender": "male", "family_id": "fam_002", "class_group": "Primary 5", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "chd_004", "name": "Grace Kiggundu", "date_of_birth": "2019-04-30", "gender": "female", "family_id": "fam_003", "class_group": "Nursery", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.children.insert_many(children)
    donation_count = await db.donations.count_documents({})
    if donation_count == 0:
        donations = [
            {"id": "don_001", "donor_name": "Alice Namukasa", "amount": 50000, "currency": "UGX", "type": "tithe", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_002", "donor_name": "Brian Ssekitto", "amount": 30000, "currency": "UGX", "type": "offering", "date": "2026-04-01", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_003", "donor_name": "Anonymous", "amount": 100000, "currency": "UGX", "type": "donation", "date": "2026-04-06", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "don_004", "donor_name": "Francis Tumwesigye", "amount": 75000, "currency": "UGX", "type": "tithe", "date": "2026-03-25", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.donations.insert_many(donations)
    expense_count = await db.expenses.count_documents({})
    if expense_count == 0:
        expenses = [
            {"id": "exp_001", "title": "Electricity Bill", "amount": 85000, "currency": "UGX", "category": "utilities", "date": "2026-04-02", "status": "approved", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "exp_002", "title": "Caretaker Salary", "amount": 150000, "currency": "UGX", "category": "salaries", "date": "2026-04-01", "status": "approved", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "exp_003", "title": "Office Supplies", "amount": 25000, "currency": "UGX", "category": "supplies", "date": "2026-03-28", "status": "pending", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.expenses.insert_many(expenses)
    return {"message": "Extended seed data added"}


@router.post("/seed-locations")
async def seed_locations_and_notifications():
    loc_count = await db.locations.count_documents({})
    if loc_count == 0:
        locations = [
            {"id": "loc_001", "name": "58:12 Global (Central)", "code": "MAIN", "type": "main", "parent_id": None, "address": "Plot 12, Kampala Road, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "Admin User", "contact_phone": "+256 800 5812", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Administration", "Finance", "Operations"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_002", "name": "Entebbe Campus", "code": "ETB", "type": "campus", "parent_id": "loc_001", "address": "15 Airport Road, Entebbe", "country": "Uganda", "currency": "UGX", "contact_name": "Francis Tumwesigye", "contact_phone": "+256 712 678901", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Youth", "Education"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_003", "name": "Jinja Campus", "code": "JNJ", "type": "campus", "parent_id": "loc_001", "address": "8 Owen Falls Road, Jinja", "country": "Uganda", "currency": "UGX", "contact_name": "Grace Akello", "contact_phone": "+256 756 789012", "active": True, "member_count": 0, "is_venue": False, "is_bookable": False, "is_restricted": False, "departments": ["Community", "Sports"], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "loc_004", "name": "Kampala East", "code": "KPE", "type": "sub-location", "parent_id": "loc_001", "address": "Nakawa Division, Kampala", "country": "Uganda", "currency": "UGX", "contact_name": "David Kiggundu", "contact_phone": "+256 706 456789", "active": True, "member_count": 0, "is_venue": True, "is_bookable": True, "is_restricted": False, "departments": [], "staff_ids": [], "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.locations.insert_many(locations)
    notif_count = await db.notifications.count_documents({})
    if notif_count == 0:
        notifications = [
            {"id": "notif_001", "title": "New Member Approval", "message": "3 new member registrations are pending approval.", "type": "warning", "target_role": "admin", "link": "/members", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "notif_002", "title": "Low Stock Alert", "message": "Coffee and Eggs (Tray) are out of stock. Please reorder.", "type": "error", "target_role": None, "link": "/sales", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "notif_003", "title": "Event Reminder", "message": "Youth Leadership Summit is in 5 days. 13 spots remaining.", "type": "info", "target_role": None, "link": "/events", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "notif_004", "title": "Tasks Overdue", "message": "2 high priority tasks are past due. Review task board.", "type": "warning", "target_role": None, "link": "/tasks", "read_by": [], "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.notifications.insert_many(notifications)
    return {"message": "Locations and notifications seeded"}


@router.post("/seed-all")
async def seed_all_data():
    seeded = []
    if await db.outreach_programs.count_documents({}) == 0:
        programs = [
            {"id": "op_001", "name": "Community Health Drive", "description": "Free medical check-ups and health education in Kampala slums.", "category": "health", "status": "active", "location": "Katwe, Kampala", "start_date": "2026-01-15", "target": 500, "sessions_count": 3, "total_reached": 142, "is_recurring": True, "recurrence_pattern": "saturday", "recurrence_day": 2, "recurrence_time": "09:00", "recurrence_end_time": "14:00", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "op_002", "name": "School Outreach Program", "description": "Bible studies and character formation in local schools.", "category": "education", "status": "active", "location": "Entebbe Municipality", "start_date": "2025-09-01", "target": 200, "sessions_count": 8, "total_reached": 316, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "op_003", "name": "Widows & Orphans Support", "description": "Monthly food distribution and counselling for vulnerable families.", "category": "welfare", "status": "active", "location": "Multiple Locations", "start_date": "2025-06-01", "target": 100, "sessions_count": 5, "total_reached": 89, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.outreach_programs.insert_many(programs)
        sessions = [
            {"id": "os_001", "program_id": "op_001", "date": "2026-03-10", "time": "09:00", "location": "Katwe Health Centre", "attendees": 47, "notes": "Distributed 47 medicine packs.", "led_by": "Dr. Auma Florence", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "os_002", "program_id": "op_002", "date": "2026-03-14", "time": "14:00", "location": "Entebbe Primary School", "attendees": 85, "notes": "Session on integrity and purpose.", "led_by": "Pastor Amos", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.outreach_sessions.insert_many(sessions)
        seeded.append("outreach")
    if await db.resources.count_documents({}) == 0:
        resources = [
            {"id": "res_001", "name": "Main Auditorium", "type": "auditorium", "capacity": 400, "description": "Main worship hall with stage, PA system, and projectors.", "location_id": "loc_001", "hourly_rate": 50000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "res_002", "name": "Conference Room A", "type": "conference", "capacity": 30, "description": "Air-conditioned with whiteboard and AV equipment.", "location_id": "loc_001", "hourly_rate": 20000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "res_003", "name": "Youth Hall", "type": "hall", "capacity": 150, "description": "Multi-purpose hall for youth programs and events.", "location_id": "loc_001", "hourly_rate": 30000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "res_004", "name": "PA System (Mobile)", "type": "equipment", "capacity": None, "description": "Portable PA system with 2 wireless microphones.", "location_id": "loc_001", "hourly_rate": 15000, "available": True, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.resources.insert_many(resources)
        seeded.append("resources")
    if await db.announcements.count_documents({}) == 0:
        announcements = [
            {"id": "ann_001", "title": "Welcome to March 2026!", "content": "This month we launch our Community Health Drive.", "type": "general", "target_role": None, "pinned": True, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "ann_002", "title": "Staff Meeting - This Friday", "content": "Mandatory all-staff meeting this Friday at 3 PM.", "type": "urgent", "target_role": "admin", "pinned": False, "author_name": "System Administrator", "author_role": "admin", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.announcements.insert_many(announcements)
        seeded.append("announcements")
    if await db.badges.count_documents({}) == 0:
        badges = [
            {"id": "bdg_001", "name": "Faithful Servant", "description": "Awarded for 1+ year of consistent volunteering.", "color": "#f59e0b", "icon": "star", "criteria": "12+ months active service", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_002", "name": "Prayer Warrior", "description": "Regular participant in prayer meetings.", "color": "#6366f1", "icon": "heart", "criteria": "30+ prayer sessions attended", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "bdg_003", "name": "Outreach Champion", "description": "Led or participated in 5+ outreach sessions.", "color": "#10b981", "icon": "award", "criteria": "5+ outreach sessions", "issued_count": 0, "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.badges.insert_many(badges)
        seeded.append("badges")
    return {"seeded": seeded, "message": "Seed complete"}
