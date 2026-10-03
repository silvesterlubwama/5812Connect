"""Auto-translation for text your staff typed (iter379).

The static JSON files can only cover the app's own labels. Event titles,
notices and lesson plans are written by people, so they are translated on
demand by Claude and then CACHED in Mongo — the same notice is never paid for
twice, and a cache hit is a single indexed lookup.

The language files cover: Luganda (lg), Kiswahili (sw), Español (es), Thai
(th), Kreyòl Ayisyen (ht), Français (fr). English is the source and never
round-trips through the model.
"""
import hashlib
import logging
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from deps import db, get_current_user

load_dotenv("/app/backend/.env")
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/translate", tags=["i18n"])

LANGUAGE_NAMES = {
    "lg": "Luganda", "sw": "Kiswahili", "es": "Spanish", "th": "Thai",
    "ht": "Haitian Creole", "fr": "French", "en": "English",
}
MAX_BATCH = 40
MAX_CHARS = 600


def _key(text: str, lang: str) -> str:
    return hashlib.sha256(f"{lang}|{text}".encode()).hexdigest()[:32]


@router.post("")
async def translate_batch(data: dict, current_user: dict = Depends(get_current_user)) -> dict:
    """`{texts: [...], lang: "lg"}` → `{translations: {source: translated}}`.

    Cached strings come back immediately; only the unseen ones reach the model.
    If the model is unavailable the ENGLISH text is returned unchanged — a
    screen must never go blank because a translation failed.
    """
    lang = (data.get("lang") or "").strip().lower()
    texts = [t.strip() for t in (data.get("texts") or []) if isinstance(t, str) and t.strip()]
    texts = list(dict.fromkeys(texts))[:MAX_BATCH]
    if not texts:
        return {"translations": {}, "lang": lang}
    if lang in ("", "en"):
        return {"translations": {t: t for t in texts}, "lang": "en"}
    if lang not in LANGUAGE_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    out: dict = {}
    missing = []
    cached = await db.translation_cache.find(
        {"key": {"$in": [_key(t, lang) for t in texts]}}, {"_id": 0}).to_list(MAX_BATCH)
    by_key = {c["key"]: c.get("translated") or "" for c in cached}
    for t in texts:
        hit = by_key.get(_key(t, lang))
        if hit:
            out[t] = hit
        else:
            missing.append(t)

    if missing:
        try:
            fresh = await _ask_model(missing, lang)
        except Exception as e:                       # never break the screen
            logger.warning(f"auto-translate unavailable ({lang}): {e}")
            fresh = {}
            # Falling back to English is silent by design, so leave a trace
            # somebody can actually find (surfaced on /cache-stats).
            await db.translation_cache.update_one(
                {"key": "__last_error__"},
                {"$set": {"key": "__last_error__", "lang": lang, "error": str(e)[:300],
                          "at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        now = datetime.now(timezone.utc).isoformat()
        for src, translated in fresh.items():
            out[src] = translated
            await db.translation_cache.update_one(
                {"key": _key(src, lang)},
                {"$set": {"key": _key(src, lang), "lang": lang, "source": src,
                          "translated": translated, "created_at": now}},
                upsert=True)
        for src in missing:
            out.setdefault(src, src)                 # fall back to English

    return {"translations": out, "lang": lang,
            "from_cache": len(texts) - len(missing), "translated": len(missing)}


async def _ask_model(texts: list, lang: str) -> dict:
    """One call for the whole batch, one line back per string."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    key = os.environ["EMERGENT_LLM_KEY"]
    language = LANGUAGE_NAMES[lang]
    chat = LlmChat(
        api_key=key,
        session_id=f"translate-{lang}",
        system_message=(
            f"You translate short interface strings from English into {language} for a "
            "community organisation's admin app in Uganda. Reply with ONLY the translations, "
            "one per line, in the same order as the input, numbered exactly as given. "
            "Keep names, places, dates, numbers and currency codes unchanged. Never add "
            "commentary. If a string is already in the target language, repeat it unchanged."
        ),
    ).with_model("anthropic", "claude-sonnet-5-5")

    numbered = "\n".join(f"{i + 1}. {t[:MAX_CHARS]}" for i, t in enumerate(texts))
    reply = await chat.send_message(UserMessage(text=numbered))

    lines = [ln.strip() for ln in str(reply).splitlines() if ln.strip()]
    result = {}
    for i, src in enumerate(texts):
        line = lines[i] if i < len(lines) else ""
        line = re.sub(r"^\s*\d{1,3}\s*[.)\-:]\s*", "", line)   # drop the "1." we asked for
        if line:
            result[src] = line
    return result


@router.get("/cache-stats")
async def cache_stats(current_user: dict = Depends(get_current_user)) -> dict:
    """How much has been translated already, per language."""
    out = {}
    for lang in LANGUAGE_NAMES:
        if lang == "en":
            continue
        out[lang] = await db.translation_cache.count_documents({"lang": lang})
    err = await db.translation_cache.find_one({"key": "__last_error__"}, {"_id": 0})
    return {"cached": out, "total": sum(out.values()),
            "last_error": {k: err[k] for k in ("lang", "error", "at")} if err else None}
