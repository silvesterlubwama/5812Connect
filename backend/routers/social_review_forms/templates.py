"""Blank printable-template PDF endpoint.

HTML templates live in /app/backend/templates/social_reviews/{kind}.html so
staff or admins can tweak wording without touching Python. Re-read on every
request — no caching — so edits are picked up without a restart.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from deps import db, require_staff, logger

from ._common import VALID_KINDS, TEMPLATES_DIR

router = APIRouter(prefix="/api/social-work/reviews", tags=["social_work_reviews"])


def _load_template(kind: str) -> str:
    """Read a template file. Re-reads on every request so admins can edit the
    HTML in-place without restarting."""
    path = TEMPLATES_DIR / f"{kind}.html"
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Template {kind}.html missing on server")
    return path.read_text(encoding="utf-8")


@router.get("/templates/{kind}.pdf")
async def download_blank_template(kind: str, current_user: dict = Depends(require_staff)):
    """Generate a printable blank template PDF. Branding pulled from system_settings."""
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail="kind must be school_progress or welfare_visit")
    org_name = "58:12 Global"
    try:
        settings = await db.system_settings.find_one({"id": "settings"}, {"_id": 0, "branding": 1, "org": 1})
        if settings:
            b = settings.get("branding") or {}
            o = settings.get("org") or {}
            org_name = b.get("app_name") or o.get("name") or org_name
    except Exception:
        pass
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    html = _load_template(kind).replace("{{ORG_NAME}}", org_name).replace("{{TODAY}}", today)
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        filename = "school-progress-review-blank.pdf" if kind == "school_progress" else "welfare-visit-blank.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.warning(f"PDF generation failed, returning HTML: {e}")
        return Response(content=html.encode(), media_type="text/html")
