"""
Lead Card PDF Generator · Sprint 2026-05-11

Produces a polished 1-page A4 PDF per Tier A/B lead that Susana can
forward to interested buyers/sellers. Layout:

    ┌─────────────────────────────────────────┐
    │  PATA BRAVA · LEAD DOSSIER  | RANK #12  │  ← header
    ├─────────────────────────────────────────┤
    │ ┌─ photo or placeholder ────────────┐    │
    │ │                                   │    │
    │ │                                   │    │
    │ └───────────────────────────────────┘    │
    │                                          │
    │  TIPOLOGIA · ZONA                        │
    │  PREÇO                  COMISSÃO EST.    │
    │                                          │
    │  ── briefing multi-linha ──              │
    │                                          │
    │  Opening WhatsApp:                       │
    │  "Olá Maria, sou da Pata Brava…"         │
    │                                          │
    │  ┌────┐                                  │
    │  │ QR │  ←  manda WhatsApp directo       │
    │  └────┘                                  │
    │                                          │
    │  URL · score · contacto                  │  ← footer
    └─────────────────────────────────────────┘

Output:  data/lead_cards/lead_<id>.pdf

Pure offline — no extra API calls (image_url is fetched once and cached
on disk under data/photos/). For leads without image_url, a tasteful
placeholder block is rendered using the typology + zone as text.
"""
from __future__ import annotations

import io
import os
import re
import urllib.request
from pathlib import Path
from typing import Optional

import qrcode
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image as RLImage, Paragraph, SimpleDocTemplate,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from PIL import Image as PILImage

from storage.database import get_db
from storage.models import Lead
from utils.logger import get_logger
from reports.commercial_export import (
    _classify_owner_tier, _personalised_whatsapp, _short_zone,
    _motivation_badges,
)
from pipeline.precall_briefing import build_briefing

log = get_logger(__name__)


# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).resolve().parent.parent
CARDS_DIR  = ROOT / "data" / "lead_cards"
PHOTOS_DIR = ROOT / "data" / "photos"
CARDS_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


# ── Brand colors (Pata Brava luxury) ──────────────────────────────────────────

GOLD     = HexColor("#ddc269")
INK      = HexColor("#0a0908")
BONE     = HexColor("#f7f1de")
BONE_DIM = HexColor("#c5bea3")
RULE     = HexColor("#3a342a")
CRIMSON  = HexColor("#c62828")


# ── Photo handling ────────────────────────────────────────────────────────────

def _local_photo_path(lead: Lead) -> Optional[Path]:
    """Return on-disk path for the lead's hero image; download if missing."""
    if not lead.image_url:
        return None
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(lead.id))
    candidates = [
        PHOTOS_DIR / f"{safe_id}.jpg",
        PHOTOS_DIR / f"{safe_id}.jpeg",
        PHOTOS_DIR / f"{safe_id}.png",
        PHOTOS_DIR / f"{safe_id}.webp",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 200:
            return c
    target = PHOTOS_DIR / f"{safe_id}.jpg"
    try:
        req = urllib.request.Request(
            lead.image_url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; ARM Mac OS X) AppleWebKit/605.1.15"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        if len(data) < 200:
            return None
        # Normalise via PIL — strip EXIF, convert to JPG, cap dimensions
        img = PILImage.open(io.BytesIO(data))
        img = img.convert("RGB")
        img.thumbnail((1400, 900))
        img.save(target, "JPEG", quality=82)
        return target
    except Exception as e:
        log.debug("[lead_card] photo fetch failed lead={id} err={e}",
                  id=lead.id, e=e)
        return None


def _qr_png(text: str, size_px: int = 220) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=1,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size_px, size_px))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Layout ────────────────────────────────────────────────────────────────────

def _fmt_price(p: Optional[float]) -> str:
    if not p:
        return "—"
    return f"€ {int(p):,}".replace(",", " ")


def _draw_header(c: canvas.Canvas, lead: Lead, rank: Optional[int]) -> None:
    W, H = A4
    margin = 14 * mm
    y = H - margin
    # Top bar
    c.setFillColor(INK)
    c.rect(0, y - 4 * mm, W, 10 * mm, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, "PATA BRAVA · LEAD DOSSIER")
    c.setFillColor(BONE)
    c.setFont("Helvetica", 8)
    rk = f"RANK #{rank}" if rank else f"LEAD #{lead.id}"
    c.drawRightString(W - margin, y, rk)


def _draw_photo_block(c: canvas.Canvas, lead: Lead, x: float, y: float,
                      w: float, h: float) -> None:
    """Draw the hero image or a tasteful placeholder."""
    path = _local_photo_path(lead)
    if path:
        try:
            c.drawImage(str(path), x, y, w, h, preserveAspectRatio=True,
                        anchor='c', mask='auto')
            # Subtle gold rule under photo
            c.setStrokeColor(GOLD)
            c.setLineWidth(0.8)
            c.line(x, y, x + w, y)
            return
        except Exception:
            pass
    # Placeholder
    c.setFillColor(HexColor("#1a1814"))
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 22)
    typ = (lead.typology or lead.property_type or "Imóvel").upper()
    zone = _short_zone(lead.zone) or "Portugal"
    c.drawCentredString(x + w / 2, y + h / 2 + 10, typ)
    c.setFont("Helvetica", 12)
    c.setFillColor(BONE_DIM)
    c.drawCentredString(x + w / 2, y + h / 2 - 14, zone)


def _draw_facts(c: canvas.Canvas, lead: Lead, brief: dict, x: float, y: float,
                w: float) -> float:
    """Draw the typology/zone/price/commission row. Returns the new y."""
    zone = _short_zone(lead.zone) or "—"
    typ = lead.typology or lead.property_type or "—"
    commission = brief.get("commission_eur", 0)

    c.setFont("Helvetica", 8)
    c.setFillColor(BONE_DIM)
    c.drawString(x, y, "TIPOLOGIA · ZONA")
    c.drawString(x + w / 2, y, "PREÇO  ·  COMISSÃO ESTIMADA")
    y -= 12

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(BONE)
    c.drawString(x, y, f"{typ} em {zone}")
    c.setFillColor(GOLD)
    price_str = _fmt_price(lead.price)
    com_str = f"€ {int(commission):,}".replace(",", " ") if commission else "—"
    c.drawString(x + w / 2, y, f"{price_str}   ·   {com_str}")
    y -= 14
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(x, y, x + w, y)
    return y - 14


def _draw_briefing(c: canvas.Canvas, brief: dict, x: float, y: float,
                   w: float) -> float:
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GOLD)
    c.drawString(x, y, "DOSSIER")
    y -= 13
    c.setFont("Helvetica", 9.5)
    c.setFillColor(BONE)
    text_obj = c.beginText(x, y)
    text_obj.setLeading(13.5)
    for line in (brief.get("text") or "").splitlines():
        text_obj.textLine(line)
        y -= 13.5
    c.drawText(text_obj)
    return y - 6


def _draw_opening_and_qr(c: canvas.Canvas, lead: Lead, brief: dict,
                         x: float, y: float, w: float) -> float:
    opening = brief.get("opening") or ""
    _, wa_link = _personalised_whatsapp(lead)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GOLD)
    c.drawString(x, y, "OPENING WHATSAPP")
    y -= 13

    # Opening text wraps as paragraph
    styles = getSampleStyleSheet()
    p_style = ParagraphStyle(
        "opening", parent=styles["Normal"],
        fontName="Helvetica-Oblique", fontSize=10.5,
        textColor=BONE, leading=14, alignment=TA_LEFT,
    )
    qr_size_px = 90
    qr_size_pt = qr_size_px * 0.75  # px → pt conversion ~

    text_width = w - qr_size_pt - 12
    para = Paragraph(f"&ldquo;{opening}&rdquo;", p_style)
    pw, ph = para.wrap(text_width, 200)
    para.drawOn(c, x, y - ph)

    # QR
    if wa_link:
        try:
            qr_bytes = _qr_png(wa_link, size_px=qr_size_px)
            qr_buf = io.BytesIO(qr_bytes)
            from reportlab.lib.utils import ImageReader
            img = ImageReader(qr_buf)
            c.drawImage(img, x + w - qr_size_pt, y - qr_size_pt,
                        qr_size_pt, qr_size_pt, mask="auto")
            c.setFont("Helvetica", 7)
            c.setFillColor(BONE_DIM)
            c.drawCentredString(
                x + w - qr_size_pt / 2, y - qr_size_pt - 8,
                "scan → WhatsApp",
            )
        except Exception as e:
            log.debug("[lead_card] QR fail lead={id}: {e}", id=lead.id, e=e)

    return min(y - ph, y - qr_size_pt) - 14


def _draw_footer(c: canvas.Canvas, lead: Lead) -> None:
    W, H = A4
    margin = 14 * mm
    y = 18 * mm
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(margin, y + 14, W - margin, y + 14)

    c.setFont("Helvetica", 8)
    c.setFillColor(BONE_DIM)
    tier = _classify_owner_tier(lead)
    score = lead.score or 0
    src = (lead.discovery_source or "").upper()
    contact = f"{lead.contact_name or '—'}  ·  {lead.contact_phone or '—'}"
    c.drawString(margin, y + 2, contact)
    c.drawRightString(W - margin, y + 2,
                      f"TIER {tier}  ·  SCORE {score}  ·  {src}")

    # URL bottom line
    url = ""
    try:
        import json as _json
        sources = _json.loads(lead.sources_json or "[]")
        if sources and isinstance(sources, list):
            first = sources[0]
            if isinstance(first, dict):
                url = first.get("url", "")
    except Exception:
        pass
    if not url and hasattr(lead, "url"):
        url = getattr(lead, "url", "") or ""
    if url:
        c.setFont("Helvetica", 7)
        c.drawString(margin, y - 10, url[:130])


# ── Public ────────────────────────────────────────────────────────────────────

def generate_card(lead: Lead, rank: Optional[int] = None,
                  out_dir: Path = CARDS_DIR) -> Path:
    """Render one lead to a single-page A4 PDF. Returns the output path."""
    out_path = out_dir / f"lead_{lead.id:05d}.pdf"
    c = canvas.Canvas(str(out_path), pagesize=A4)

    W, H = A4
    margin = 14 * mm
    content_w = W - 2 * margin

    # Background
    c.setFillColor(INK)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    _draw_header(c, lead, rank)

    # Photo block — top half of content area
    photo_h = 95 * mm
    photo_y = H - 14 * mm - 12 * mm - photo_h
    _draw_photo_block(c, lead, margin, photo_y, content_w, photo_h)

    # Build briefing once
    try:
        brief = build_briefing(lead)
    except Exception as e:
        log.debug("[lead_card] brief fail lead={id}: {e}", id=lead.id, e=e)
        brief = {"text": "", "opening": "", "commission_eur": 0}

    y = photo_y - 14
    y = _draw_facts(c, lead, brief, margin, y, content_w)
    y = _draw_briefing(c, brief, margin, y, content_w)
    _draw_opening_and_qr(c, lead, brief, margin, y, content_w)

    _draw_footer(c, lead)

    c.showPage()
    c.save()
    return out_path


def generate_top_cards(limit: int = 20,
                       tier_filter: tuple = ("A", "B")) -> list[Path]:
    """Generate cards for the top-N Tier A/B leads, ordered by score+price."""
    with get_db() as db:
        leads = (db.query(Lead)
                 .filter(
                     Lead.archived == False,                      # noqa: E712
                     Lead.contact_phone.isnot(None),
                     Lead.contact_phone != "",
                     Lead.phone_type == "mobile",
                     Lead.price.isnot(None),
                     Lead.price > 0,
                     Lead.zone.isnot(None),
                 )
                 .order_by(Lead.score.desc(), Lead.price.desc())
                 .limit(limit * 5)   # fetch more, filter to Tier A/B in Python
                 .all())

    selected: list[tuple[int, Lead]] = []
    seen_phones: set[str] = set()
    for L in leads:
        t = _classify_owner_tier(L)
        if t not in tier_filter:
            continue
        if L.contact_phone in seen_phones:
            continue
        seen_phones.add(L.contact_phone)
        selected.append((len(selected) + 1, L))
        if len(selected) >= limit:
            break

    paths: list[Path] = []
    for rank, lead in selected:
        try:
            p = generate_card(lead, rank=rank)
            paths.append(p)
            log.info("[lead_card] generated rank={r} lead={id} → {p}",
                     r=rank, id=lead.id, p=p.name)
        except Exception as e:
            log.warning("[lead_card] failed lead={id}: {e}", id=lead.id, e=e)
    return paths
