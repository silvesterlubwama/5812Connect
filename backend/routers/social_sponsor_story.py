"""Sponsor story generator (iter350).

One click turns a child's social-work file into a warm, sponsor-ready story a
fundraiser can send to a potential or existing sponsor. Written by Claude
Sonnet 4.6 through the Emergent universal key, from structured case data plus
anything the social worker adds by hand (favourite colours, living situation…).

Safeguarding rules are baked into the system prompt: no surnames, no addresses,
no school names, no medical diagnoses, nothing that could identify or endanger
the child.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from deps import db, require_staff, _audit, logger, require_social_work_view

load_dotenv()

router = APIRouter(prefix="/api/social-work", tags=["social-work"], dependencies=[Depends(require_social_work_view)])

STORY_MODEL = ("anthropic", "claude-sonnet-4-6")

SYSTEM_PROMPT = (
    "You write short, dignified sponsorship stories for a child-welfare "
    "organisation in Uganda. You are given the facts held in a child's social-work "
    "file. Write in warm, concrete, present-tense prose that helps a sponsor feel "
    "connected to a real person.\n\n"
    "Hard rules:\n"
    "- Never invent facts. Use only what you are given; if something is missing, "
    "leave it out rather than guessing.\n"
    "- Use the child's FIRST NAME only. Never a surname.\n"
    "- Never include an address, village, school name, clinic name, medical "
    "diagnosis, HIV status, or anything that could identify or endanger the child.\n"
    "- No pity language, no 'poor child', no saviour framing. Respectful and hopeful.\n"
    "- Do not promise outcomes or quote money amounts.\n"
    "- Plain text only: no markdown, no headings, no bullet points, no emoji."
)

LENGTHS = {
    "short": "2 short paragraphs, about 90 words total.",
    "medium": "3 paragraphs, about 170 words total.",
    "long": "4 paragraphs, about 260 words total.",
}

TONES = {
    "warm": "Warm and personal, as if introducing a friend.",
    "hopeful": "Hopeful and forward-looking, focused on what is possible next.",
    "formal": "Composed and factual, suitable for an institutional donor.",
}

SUPPORT_LABELS = {
    "school_fees": "school fees", "school_materials": "school materials",
    "uniform": "a school uniform", "food": "food support", "medical": "health care",
    "housing": "safe housing", "clothing": "clothing", "counselling": "counselling",
    "transport": "transport", "hygiene": "hygiene items",
    "vocational_training": "vocational training", "legal": "legal support",
    "spiritual": "spiritual care", "other": "other support",
}


def _age_from_dob(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        born = datetime.fromisoformat(str(dob)[:10]).date()
    except Exception:
        return None
    today = datetime.now(timezone.utc).date()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _first_name(full: str) -> str:
    return (full or "").strip().split(" ")[0] or "This child"


async def _gather_facts(case: dict, inputs: dict) -> str:
    """Flatten everything we know into a compact fact sheet for the model."""
    subject_id = case.get("subject_id")
    child = {}
    if subject_id:
        coll = db.children if (case.get("subject_kind") or "child") == "child" else db.members
        child = await coll.find_one({"id": subject_id}, {"_id": 0}) or {}

    dob = child.get("date_of_birth") or case.get("subject_dob")
    age = _age_from_dob(dob)
    education = case.get("education") or {}
    family = case.get("family") or {}
    goals = case.get("goals") or []

    reviews = await db.social_review_forms.find(
        {"child_id": subject_id}, {"_id": 0, "kind": 1, "review_date": 1, "overall_assessment": 1, "action_plan": 1},
    ).sort("review_date", -1).to_list(4) if subject_id else []

    lines = [f"First name: {_first_name(case.get('subject_name'))}"]
    if age is not None:
        lines.append(f"Age: {age}")
    if dob:
        lines.append(f"Birthday (month/day only may be mentioned): {str(dob)[5:10]}")
    if child.get("gender"):
        lines.append(f"Gender: {child['gender']}")
    if education.get("grade"):
        lines.append(f"School grade/class: {education['grade']}")
    if education.get("academic_performance"):
        lines.append(f"How school is going: {education['academic_performance']}")
    if education.get("extracurricular"):
        lines.append(f"Activities enjoyed: {', '.join(map(str, education['extracurricular']))}")
    if family.get("primary_caregiver") or family.get("caregiver_relationship"):
        lines.append(f"Cared for by: {family.get('caregiver_relationship') or family.get('primary_caregiver')}")
    if family.get("siblings"):
        lines.append(f"Siblings: {family['siblings']}")
    if case.get("summary"):
        lines.append(f"Case worker summary: {case['summary']}")
    needed = [SUPPORT_LABELS.get(s, s) for s in (case.get("support_needed") or [])]
    given = [SUPPORT_LABELS.get(s, s) for s in (case.get("support_given") or [])]
    if needed:
        lines.append(f"Support still needed: {', '.join(needed)}")
    if given:
        lines.append(f"Support already provided: {', '.join(given)}")
    for g in goals[:3]:
        if isinstance(g, dict) and g.get("goal"):
            lines.append(f"Goal being worked on: {g['goal']}")
    for r in reviews:
        note = r.get("overall_assessment") or r.get("action_plan")
        if note:
            lines.append(f"From the {str(r.get('kind') or 'review').replace('_', ' ')} on {str(r.get('review_date'))[:10]}: {note}")

    # Hand-typed colour / living-situation detail from the social worker.
    for key, label in (
        ("favourite_colour", "Favourite colour"),
        ("favourite_subject", "Favourite school subject"),
        ("favourite_food", "Favourite food"),
        ("dream", "What they want to be one day"),
        ("living_situation", "Living situation"),
        ("personality", "Personality"),
        ("extra", "Other notes from the social worker"),
    ):
        val = (inputs.get(key) or "").strip() if isinstance(inputs, dict) else ""
        if val:
            lines.append(f"{label}: {val[:400]}")
    return "\n".join(lines)


@router.post("/cases/{case_id}/sponsor-story")
async def generate_sponsor_story(case_id: str, data: dict = None, current_user: dict = Depends(require_staff)):
    """Generate a sponsor-ready story for a case. Body (all optional):
    { tone: 'warm'|'hopeful'|'formal', length: 'short'|'medium'|'long',
      inputs: { favourite_colour, favourite_subject, favourite_food, dream,
                living_situation, personality, extra } }
    Returns { story, model, generated_at }. Also saved on the case as
    `sponsor_story` so it survives a page reload and can be edited by hand.
    """
    data = data or {}
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI key not configured — add EMERGENT_LLM_KEY to the backend environment")

    tone = TONES.get((data.get("tone") or "warm").lower(), TONES["warm"])
    length = LENGTHS.get((data.get("length") or "medium").lower(), LENGTHS["medium"])
    facts = await _gather_facts(case, data.get("inputs") or {})

    prompt = (
        f"Write a sponsorship story from this file.\n\nTone: {tone}\nLength: {length}\n\n"
        f"FACTS ON FILE:\n{facts}\n\n"
        "Write only the story text."
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
        chat = LlmChat(
            api_key=api_key,
            session_id=f"sponsor_story_{case_id}_{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT,
        ).with_model(*STORY_MODEL)
        chunks = []
        async for ev in chat.stream_message(UserMessage(text=prompt)):
            if isinstance(ev, TextDelta):
                chunks.append(ev.content)
            elif isinstance(ev, StreamDone):
                break
        story = "".join(chunks).strip()
    except Exception as e:
        logger.error(f"sponsor story generation failed for {case_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Story generation failed: {e}")

    if not story:
        raise HTTPException(status_code=502, detail="The model returned an empty story — try again")

    now = datetime.now(timezone.utc).isoformat()
    await db.social_cases.update_one({"id": case_id}, {"$set": {
        "sponsor_story": story,
        "sponsor_story_generated_at": now,
        "sponsor_story_generated_by": current_user["id"],
        "sponsor_story_generated_by_name": current_user.get("name", ""),
        "sponsor_story_model": STORY_MODEL[1],
        "sponsor_story_inputs": data.get("inputs") or {},
    }})
    await _audit(current_user["id"], "generate", "sponsor_story", case_id, {"model": STORY_MODEL[1]})
    return {"story": story, "model": STORY_MODEL[1], "generated_at": now}


@router.put("/cases/{case_id}/sponsor-story")
async def save_sponsor_story(case_id: str, data: dict, current_user: dict = Depends(require_staff)):
    """Save a hand-edited sponsor story (the fundraiser always has the last word)."""
    story = (data.get("story") or "").strip()
    if len(story) > 8000:
        raise HTTPException(status_code=400, detail="Story is too long")
    case = await db.social_cases.find_one({"id": case_id}, {"_id": 0, "id": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await db.social_cases.update_one({"id": case_id}, {"$set": {
        "sponsor_story": story,
        "sponsor_story_edited_at": datetime.now(timezone.utc).isoformat(),
        "sponsor_story_edited_by_name": current_user.get("name", ""),
    }})
    return {"story": story}
