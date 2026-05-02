"""I18N translations + webcal feed. Extracted from server.py."""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from starlette.responses import Response
from deps import db

router = APIRouter(prefix="/api", tags=["i18n"])


TRANSLATIONS = {
    "en": {"dashboard": "Dashboard", "people": "People", "events": "Events", "calendar": "Calendar", "tasks": "Tasks", "checkins": "Check-Ins", "outreach": "Outreach", "communications": "Communications", "resources": "Resources", "access": "Access Control", "financial": "Financial", "sales": "Sales & Products", "analytics": "Analytics", "reports": "Reports", "settings": "Settings", "logout": "Logout", "search": "Search", "save": "Save", "cancel": "Cancel", "delete": "Delete", "edit": "Edit", "add": "Add", "close": "Close", "welcome": "Welcome", "members": "Members", "volunteers": "Volunteers", "shifts": "Shifts", "templates": "Email Templates"},
    "fr": {"dashboard": "Tableau de bord", "people": "Personnes", "events": "Evenements", "calendar": "Calendrier", "tasks": "Taches", "checkins": "Enregistrements", "outreach": "Sensibilisation", "communications": "Communications", "resources": "Ressources", "access": "Controle d'acces", "financial": "Finances", "sales": "Ventes et Produits", "analytics": "Analyses", "reports": "Rapports", "settings": "Parametres", "logout": "Deconnexion", "search": "Rechercher", "save": "Enregistrer", "cancel": "Annuler", "delete": "Supprimer", "edit": "Modifier", "add": "Ajouter", "close": "Fermer", "welcome": "Bienvenue", "members": "Membres", "volunteers": "Benevoles", "shifts": "Quarts", "templates": "Modeles d'email"},
    "sw": {"dashboard": "Dashibodi", "people": "Watu", "events": "Matukio", "calendar": "Kalenda", "tasks": "Kazi", "checkins": "Kuingia", "outreach": "Kufikia", "communications": "Mawasiliano", "resources": "Rasilimali", "access": "Udhibiti wa Ufikiaji", "financial": "Fedha", "sales": "Mauzo na Bidhaa", "analytics": "Uchambuzi", "reports": "Ripoti", "settings": "Mipangilio", "logout": "Ondoka", "search": "Tafuta", "save": "Hifadhi", "cancel": "Ghairi", "delete": "Futa", "edit": "Hariri", "add": "Ongeza", "close": "Funga", "welcome": "Karibu", "members": "Wanachama", "volunteers": "Watu wa kujitolea", "shifts": "Zamu", "templates": "Violezo vya barua pepe"},
    "lg": {"dashboard": "Dashiboodi", "people": "Abantu", "events": "Ebikozesebwa", "calendar": "Kalenda", "tasks": "Emirimu", "checkins": "Okwingira", "outreach": "Okubuulira", "communications": "Amawulire", "resources": "Ebyetaagisa", "access": "Okufuna Emikisa", "financial": "Ensimbi", "sales": "Okutunda", "analytics": "Okusengejja", "reports": "Lipoota", "settings": "Entegeka", "logout": "Fuluma", "search": "Noonya", "save": "Tereka", "cancel": "Sazaamu", "delete": "Sangula", "edit": "Kyusa", "add": "Gatta", "close": "Ggalawo", "welcome": "Tukusanyukidde", "members": "Bameemba", "volunteers": "Abayizi", "shifts": "Emirembe", "templates": "Ekifaananyi"},
    "th": {"dashboard": "แดชบอร์ด", "people": "ผู้คน", "events": "กิจกรรม", "calendar": "ปฏิทิน", "tasks": "งาน", "checkins": "เช็คอิน", "outreach": "การเผยแพร่", "communications": "การสื่อสาร", "resources": "ทรัพยากร", "access": "การควบคุมการเข้าถึง", "financial": "การเงิน", "sales": "การขายและสินค้า", "analytics": "การวิเคราะห์", "reports": "รายงาน", "settings": "การตั้งค่า", "logout": "ออกจากระบบ", "search": "ค้นหา", "save": "บันทึก", "cancel": "ยกเลิก", "delete": "ลบ", "edit": "แก้ไข", "add": "เพิ่ม", "close": "ปิด", "welcome": "ยินดีต้อนรับ", "members": "สมาชิก", "volunteers": "อาสาสมัคร", "shifts": "กะ", "templates": "เทมเพลตอีเมล"},
}


@router.get("/i18n/{lang}")
async def get_translations(lang: str = "en"):
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"])


@router.get("/i18n")
async def get_all_translations():
    return {
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "fr", "name": "Francais"},
            {"code": "sw", "name": "Kiswahili"},
            {"code": "lg", "name": "Luganda"},
            {"code": "th", "name": "ไทย (Thai)"},
        ],
        "translations": TRANSLATIONS,
    }


@router.get("/webcal/{user_id}.ics")
async def webcal_feed(user_id: str):
    """Public webcal feed URL for a user's events."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "location_id": 1})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    query = {"$or": [{"is_public": True}, {"created_by": user_id}]}
    if user.get("location_id"):
        query["$or"].append({"location_id": user["location_id"]})
    events = await db.events.find(query, {"_id": 0}).sort("date", 1).to_list(200)
    ical = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//58:12 Global Connect//CRM//EN\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n"
    for ev in events:
        date_str = (ev.get("date") or "").replace("-", "")
        time_str = (ev.get("time") or "0000").replace(":", "")
        dtstart = f"{date_str}T{time_str}00" if time_str else date_str
        ical += f"BEGIN:VEVENT\r\nUID:{ev['id']}@5812global\r\nDTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\nDTSTART:{dtstart}\r\nSUMMARY:{ev.get('title','')}\r\nDESCRIPTION:{ev.get('description','')}\r\nLOCATION:{ev.get('location','')}\r\nEND:VEVENT\r\n"
    ical += "END:VCALENDAR\r\n"
    return Response(
        content=ical,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=5812global-events.ics"}
    )
