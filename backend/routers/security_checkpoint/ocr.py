"""OCR endpoints + shared Gemini pipeline.

Two surfaces:
  - `/api/security/checkpoint/ocr-id` (security device session) — defined here.
  - `/api/ocr/id` (staff Bearer auth) — defined in __init__.py using the same helper.
"""
from fastapi import HTTPException, UploadFile
from typing import Optional
import uuid

# Optional language hint → injected into the OCR system prompt so the model knows
# what script to expect (Arabic, Cyrillic, CJK, etc.). Defaults to English/Latin.
_OCR_LANG_HINTS = {
    "en": "English / Latin script",
    "fr": "French / Latin script",
    "es": "Spanish / Latin script",
    "pt": "Portuguese / Latin script",
    "sw": "Swahili / Latin script",
    "lg": "Luganda / Latin script",
    "ar": "Arabic script (right-to-left)",
    "ru": "Cyrillic / Russian script",
    "uk": "Cyrillic / Ukrainian script",
    "zh": "Simplified Chinese (Hanzi)",
    "ja": "Japanese (Kanji + Kana)",
    "ko": "Korean (Hangul)",
    "th": "Thai script",
    "hi": "Devanagari / Hindi script",
    "am": "Amharic / Ge'ez script",
}


async def _ocr_id_image(image: UploadFile, language: Optional[str], session_id_for_log: str) -> dict:
    """Shared OCR pipeline. Used by both /security/checkpoint/ocr-id (device session)
    and the staff-auth wrapper at /ocr/id (admin auth).
    Returns {name, date_of_birth, id_number, raw_text, confidence, language_hint}."""
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 8MB")
    mime = (image.content_type or "").lower()
    if mime not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        if data[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            raise HTTPException(status_code=400, detail="Image must be JPEG, PNG, or WEBP")
    import os as _os
    import json as _json
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix="." + mime.split("/")[-1])
    try:
        with _os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"OCR unavailable: {e}")
        api_key = _os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="OCR not configured (no LLM key)")
        lang_hint = _OCR_LANG_HINTS.get((language or "en").strip().lower(), "")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"ocr_{session_id_for_log}_{uuid.uuid4().hex[:6]}",
            system_message=(
                "You are an OCR assistant for government-issued ID cards (passports, national IDs, drivers licenses). "
                f"{f'The document is most likely in {lang_hint}. ' if lang_hint else ''}"
                "Transliterate non-Latin names into Latin script if the latin transliteration is printed on the document, "
                "otherwise return the name in its original script.\n"
                "Extract ONLY the following fields and return STRICT JSON — no prose, no markdown:\n"
                "{\"name\": str, \"date_of_birth\": \"YYYY-MM-DD\" or empty, \"id_number\": str, \"raw_text\": str (everything legible), \"confidence\": \"high\"|\"medium\"|\"low\"}\n"
                "If a field is unreadable or absent, return empty string for that field."
            ),
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(
            text=(
                "Extract the holder's full name, date of birth, and primary ID/document number from this ID card. "
                "Return strict JSON as instructed. If the image is not an ID card, set confidence='low' and all fields empty."
            ),
            file_contents=[FileContentWithMimeType(file_path=tmp_path, mime_type=mime)],
        )
        raw = await chat.send_message(msg)
        s = (raw or "").strip()
        if s.startswith("```"):
            s = s.strip("`")
            if s.lower().startswith("json"):
                s = s[4:].strip()
        first = s.find("{")
        last = s.rfind("}")
        if first >= 0 and last > first:
            s = s[first:last + 1]
        try:
            parsed = _json.loads(s)
        except Exception:
            parsed = {"name": "", "date_of_birth": "", "id_number": "", "raw_text": (raw or "")[:500], "confidence": "low"}
        out = {
            "name": str(parsed.get("name") or "").strip()[:120],
            "date_of_birth": str(parsed.get("date_of_birth") or "").strip()[:10],
            "id_number": str(parsed.get("id_number") or "").strip()[:60],
            "raw_text": str(parsed.get("raw_text") or "")[:2000],
            "confidence": str(parsed.get("confidence") or "low").lower() if parsed.get("confidence") else "low",
            "language_hint": (language or "en").lower(),
        }
        if out["confidence"] not in {"high", "medium", "low"}:
            out["confidence"] = "low"
        return out
    finally:
        try:
            _os.remove(tmp_path)
        except Exception:
            pass
