"""
Sprint NLP Y · Phone OCR from listing images.

Some sellers hide their phone inside the listing image to defeat naïve
scrapers. This module downloads the first image of every lead missing a
phone, runs Tesseract OCR over it, and extracts any PT phone numbers
found.

Setup (one-time)
----------------
    brew install tesseract       # macOS
    pip3 install pytesseract pillow

Status guard: if tesseract is not installed, the module loads cleanly but
``ocr_extract_phones()`` returns immediately with ``"unavailable"`` flag.
This keeps the import surface stable so smoke tests pass.

Usage
-----
    from utils.phone_ocr import ocr_sweep_missing_phones
    stats = ocr_sweep_missing_phones(limit=200)

CLI
---
    python3 main.py phone-ocr-sweep --limit 200
"""
from __future__ import annotations

import re
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)


# ── PT phone regex (E.164 + national, with optional spacing) ─────────
_PT_PHONE_RE = re.compile(
    r"(?:\+?351[\s.-]?)?(\d{2,3})[\s.-]?(\d{3})[\s.-]?(\d{3})"
)


def _is_tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        # Try to invoke tesseract — checks the binary is also installed
        from pytesseract.pytesseract import get_tesseract_version
        get_tesseract_version()
        return True
    except Exception:
        return False


def extract_phones_from_image(url: str, timeout: float = 8.0) -> list[str]:
    """Return list of canonical PT phones (E.164) found in the image at URL.

    Returns ``[]`` if tesseract isn't available, the image can't be fetched,
    or no phone-shaped strings are detected. Never raises.
    """
    if not _is_tesseract_available():
        return []
    if not url or not url.startswith(("http://", "https://")):
        return []

    try:
        import io
        import httpx
        from PIL import Image
        import pytesseract

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(url)
        if r.status_code != 200 or len(r.content) < 1024:
            return []

        img = Image.open(io.BytesIO(r.content))
        text = pytesseract.image_to_string(img, lang="por+eng")

        phones = []
        for m in _PT_PHONE_RE.finditer(text):
            digits = "".join(m.groups())
            # PT mobile must be 9 digits and start with 9
            if len(digits) == 9 and digits[0] == "9":
                phones.append("+351" + digits)
            elif len(digits) == 11 and digits.startswith("351"):
                phones.append("+" + digits)
        # Dedup, keep order
        seen = set()
        out = []
        for p in phones:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out
    except Exception as e:
        log.debug("[phone_ocr] image fetch/OCR failed for {u}: {e}", u=url, e=e)
        return []


# ── Sweep · find leads missing phone, OCR their first image ──────────

def ocr_sweep_missing_phones(limit: int = 200) -> dict:
    """
    Walk leads with image_url but no contact_phone. OCR the image. Persist
    any extracted phone with phone_type='unknown' (downstream validate_phones
    will classify it as mobile/landline).

    Idempotent. Skips leads already processed (have phone or no image).
    """
    stats = {
        "considered": 0, "ocr_attempted": 0, "phones_found": 0,
        "phones_saved": 0, "tesseract_available": _is_tesseract_available(),
    }
    if not stats["tesseract_available"]:
        log.warning(
            "[phone_ocr] Tesseract not installed. "
            "Run: brew install tesseract && pip install pytesseract pillow"
        )
        return stats

    from storage.database import get_db
    from storage.models   import Lead

    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .filter((Lead.contact_phone.is_(None)) | (Lead.contact_phone == ""))
            .filter(Lead.image_url.isnot(None), Lead.image_url != "")
            .limit(limit)
            .all()
        )
        stats["considered"] = len(leads)

        for lead in leads:
            phones = extract_phones_from_image(lead.image_url)
            stats["ocr_attempted"] += 1
            if phones:
                stats["phones_found"] += len(phones)
                # Pick first; validate_phones() will refine phone_type
                lead.contact_phone = phones[0]
                lead.phone_type    = "unknown"
                lead.contact_source = (lead.contact_source or "") + " + image_ocr"
                stats["phones_saved"] += 1
                log.info(
                    "[phone_ocr] lead #{id} phone OCR'd: {p}",
                    id=lead.id, p=phones[0],
                )

        db.commit()
    log.info(
        "[phone_ocr] considered={c} ocr={o} found={f} saved={s}",
        c=stats["considered"], o=stats["ocr_attempted"],
        f=stats["phones_found"], s=stats["phones_saved"],
    )
    return stats
