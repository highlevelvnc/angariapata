"""
Sprint Phone Recovery · Recuperar phones REAIS de leads com relay/proxy.

Após o quality_filter classificar correctamente, descobrimos que 558 OLX
leads têm phones relay (90X/95X/97X/etc) ou unknown — não chegam ao dono.

Estratégias para extrair o telemóvel REAL desses leads:

  A. description_phone_scan  — regex sobre title+description do raw_data
                              (vendedores colam o phone para bypassar relay)
  B. wa_me_link_extract       — extrai phones de links wa.me na descrição
  C. olx_aggressive_reveal    — re-visita OLX detail pages com Playwright
                              (click reveal + wait + parse) — heaviest
  D. cross_portal_inherit     — mesmo imóvel em outro portal com phone real?
                              herda esse phone via fingerprint match

Cada estratégia:
  - Lê leads candidatos da DB (relay/unknown/no_phone)
  - Tenta extrair phone real
  - VALIDA contra ANACOM 2024 (mobile 91/92/93/96, landline 21-29)
  - Persiste apenas se phone_type vira mobile/landline genuíno
  - Append "+ phone_recovery_X" ao contact_source para tracing

Idempotente — pode correr várias vezes sem efeitos colaterais.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy import or_

from storage.database import get_db
from storage.models   import Lead, RawListing
from utils.logger     import get_logger
from utils.phone      import validate_pt_phone, classify_phone_type

log = get_logger(__name__)


# ── Phone regex (PT) ─────────────────────────────────────────────────
# Permissive: looks for any sequence of 9 digits (with optional separators)
# starting with 2 or 9. Filtered downstream via classify_phone_type.
# Optional +351/00351 country code prefix.
_PHONE_RE = re.compile(
    r"(?<![\d+])"                                    # not preceded by digit/+
    r"(?:\+?351\s*[-.\s]?)?"                          # optional country code
    r"([29](?:[\s.\-]*\d){8})"                        # 2 or 9 followed by 8 digits, separators allowed
    r"(?!\d)"                                          # not followed by another digit
)
_WAME_RE = re.compile(r"wa\.me/(?:\+?351)?(\d{9})")


def _extract_real_phones_from_text(text: str) -> list[str]:
    """Return canonical (+351XXXXXXXXX) phones found in free text that are
    REAL PT mobile/landline (not relay). Validation via classify_phone_type."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _PHONE_RE.finditer(text):
        # Strip all non-digits from match
        digits = re.sub(r"\D", "", m.group(1))
        # Must be exactly 9 digits PT national
        if len(digits) != 9:
            continue
        if digits[0] not in ("2", "9"):
            continue
        pt = classify_phone_type(digits)
        if pt in ("mobile", "landline"):
            canonical = "+351" + digits
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
    return out


def _extract_wame_phones(text: str) -> list[str]:
    """Extract real PT phones from wa.me links."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _WAME_RE.finditer(text):
        digits = m.group(1)
        if len(digits) != 9 or not digits.isdigit():
            continue
        pt = classify_phone_type(digits)
        if pt in ("mobile", "landline"):
            canonical = "+351" + digits
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
    return out


# ── Sprint A · Description scan ──────────────────────────────────────

def description_phone_scan() -> dict:
    """
    Sweep every lead with relay/unknown phone. Scan title + description for
    REAL PT phone patterns. Replace contact_phone with the recovered number.
    """
    stats = {"checked": 0, "recovered": 0, "by_source": {}}
    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .filter(or_(
                Lead.phone_type == "relay",
                Lead.phone_type == "unknown",
                Lead.phone_type == "invalid",
                Lead.phone_type.is_(None),
                Lead.contact_phone.is_(None),
                Lead.contact_phone == "",
            ))
            .all()
        )
        stats["checked"] = len(leads)
        for lead in leads:
            text = " ".join([lead.title or "", lead.description or ""])
            phones = _extract_real_phones_from_text(text)
            if phones:
                lead.contact_phone = phones[0]
                lead.phone_type = classify_phone_type(phones[0][4:])
                lead.contact_source = (lead.contact_source or "") + " + desc_scan"
                stats["recovered"] += 1
                src = lead.discovery_source or "?"
                stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
        db.commit()
    log.info(
        "[recovery.desc] checked={c} recovered={r} by_source={b}",
        c=stats["checked"], r=stats["recovered"], b=stats["by_source"],
    )
    return stats


# ── Sprint B · wa.me link extract ────────────────────────────────────

def wame_link_extract() -> dict:
    """
    Look for wa.me/+351XXXXXXXXX links inside title/description/raw_data
    of leads with relay or no phone. Extract the embedded mobile number.
    """
    stats = {"checked": 0, "recovered": 0, "by_source": {}}
    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .filter(or_(
                Lead.phone_type.in_(("relay", "unknown", "invalid")),
                Lead.phone_type.is_(None),
                Lead.contact_phone.is_(None),
                Lead.contact_phone == "",
            ))
            .all()
        )
        stats["checked"] = len(leads)
        for lead in leads:
            text = " ".join([lead.title or "", lead.description or ""])
            phones = _extract_wame_phones(text)
            if not phones:
                # Also probe the raw_data JSON if available
                raw = (
                    db.query(RawListing)
                    .filter(RawListing.url == (
                        json.loads(lead.sources_json or "[]")[0].get("url", "")
                        if lead.sources_json and lead.sources_json != "[]" else ""
                    ))
                    .first()
                )
                if raw and raw.raw_data:
                    phones = _extract_wame_phones(raw.raw_data)
            if phones:
                lead.contact_phone = phones[0]
                lead.phone_type = classify_phone_type(phones[0][4:])
                lead.contact_source = (lead.contact_source or "") + " + wa_me"
                stats["recovered"] += 1
                src = lead.discovery_source or "?"
                stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
        db.commit()
    log.info(
        "[recovery.wame] checked={c} recovered={r} by_source={b}",
        c=stats["checked"], r=stats["recovered"], b=stats["by_source"],
    )
    return stats


# ── Sprint D · Cross-portal phone inherit ──────────────────────────

def cross_portal_inherit() -> dict:
    """
    For each lead with relay/no phone, look for SIBLINGS sharing the same
    fingerprint on a different portal. If a sibling has a real phone,
    inherit it.
    """
    stats = {"checked": 0, "recovered": 0, "by_source": {}}
    with get_db() as db:
        # Leads needing recovery
        bad_leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .filter(or_(
                Lead.phone_type.in_(("relay", "unknown", "invalid")),
                Lead.phone_type.is_(None),
            ))
            .all()
        )
        stats["checked"] = len(bad_leads)
        for lead in bad_leads:
            if not lead.fingerprint:
                continue
            siblings = (
                db.query(Lead)
                .filter(
                    Lead.fingerprint == lead.fingerprint,
                    Lead.id != lead.id,
                    Lead.archived == False,
                    Lead.phone_type.in_(("mobile", "landline")),
                )
                .all()
            )
            if siblings:
                # Pick best sibling (mobile > landline)
                siblings.sort(key=lambda s: 0 if s.phone_type == "mobile" else 1)
                sib = siblings[0]
                lead.contact_phone = sib.contact_phone
                lead.phone_type    = sib.phone_type
                if not lead.contact_name and sib.contact_name:
                    lead.contact_name = sib.contact_name
                if not lead.contact_email and sib.contact_email:
                    lead.contact_email = sib.contact_email
                lead.contact_source = (lead.contact_source or "") + f" + cross_portal({sib.discovery_source})"
                stats["recovered"] += 1
                src = lead.discovery_source or "?"
                stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
        db.commit()
    log.info(
        "[recovery.cross] checked={c} recovered={r} by_source={b}",
        c=stats["checked"], r=stats["recovered"], b=stats["by_source"],
    )
    return stats


# ── Sprint C · OLX aggressive Playwright reveal (heaviest) ───────────

def olx_aggressive_reveal(limit: int = 200) -> dict:
    """
    For OLX leads still with relay/unknown phone, re-visit detail page
    via Playwright stealth, click "Mostrar telefone", wait, extract.

    This is the heaviest recovery method. Limit per run avoids long sweeps.
    """
    stats = {"checked": 0, "playwright_attempts": 0, "recovered": 0,
             "no_button_found": 0, "still_relay": 0, "errors": 0}
    try:
        from scrapers.base import PlaywrightPhoneRevealer
    except Exception as e:
        log.warning("[recovery.olx] PlaywrightPhoneRevealer unavailable: {e}", e=e)
        return stats

    from scrapers.olx import _PHONE_BTN_SELECTORS, _CONSENT_SELECTORS
    from config.settings import settings as _settings

    with get_db() as db:
        candidates = (
            db.query(Lead)
            .filter(
                Lead.archived == False,                  # noqa: E712
                Lead.discovery_source == "olx",
                or_(
                    Lead.phone_type.in_(("relay", "unknown", "invalid")),
                    Lead.phone_type.is_(None),
                    Lead.contact_phone.is_(None),
                    Lead.contact_phone == "",
                ),
            )
            .order_by(Lead.score.desc().nullslast())
            .limit(limit)
            .all()
        )
        stats["checked"] = len(candidates)
        if not candidates:
            return stats

        # Build URL list
        urls = []
        url_to_lead = {}
        for lead in candidates:
            try:
                src = json.loads(lead.sources_json or "[]")
                u = src[0].get("url") if src else None
            except Exception:
                u = None
            if u:
                urls.append(u)
                url_to_lead[u] = lead

        log.info("[recovery.olx] launching Playwright reveal for {n} URLs", n=len(urls))
        revealer = PlaywrightPhoneRevealer(
            phone_btn_selectors=_PHONE_BTN_SELECTORS,
            consent_selectors=_CONSENT_SELECTORS,
            headless=_settings.headless_browser,
        )
        try:
            reveals = revealer.reveal_batch(urls)
        except Exception as e:
            log.error("[recovery.olx] reveal_batch failed: {e}", e=e)
            stats["errors"] = len(urls)
            return stats

        stats["playwright_attempts"] = len(reveals)
        for url, revealed in reveals.items():
            lead = url_to_lead.get(url)
            if not lead:
                continue
            if not revealed:
                stats["no_button_found"] += 1
                continue
            pt = classify_phone_type(revealed.replace("+351", "").replace(" ", "")[:9])
            if pt in ("mobile", "landline"):
                lead.contact_phone = revealed if revealed.startswith("+") else "+351" + revealed
                lead.phone_type = pt
                lead.contact_source = (lead.contact_source or "") + " + olx_aggressive"
                stats["recovered"] += 1
            else:
                stats["still_relay"] += 1
        db.commit()

    log.info(
        "[recovery.olx] checked={c} attempts={a} recovered={r} no_btn={n} still_relay={s}",
        c=stats["checked"], a=stats["playwright_attempts"],
        r=stats["recovered"], n=stats["no_button_found"], s=stats["still_relay"],
    )
    return stats


# ── CLI orchestrator ─────────────────────────────────────────────────

def cli_recovery_full(include_aggressive: bool = False, olx_limit: int = 200) -> dict:
    """Run all recovery sprints in priority order (lightest first)."""
    log.info("═══ Phone recovery start ═══")
    a = description_phone_scan()
    b = wame_link_extract()
    d = cross_portal_inherit()
    result = {"description": a, "wa_me": b, "cross_portal": d}
    if include_aggressive:
        c = olx_aggressive_reveal(limit=olx_limit)
        result["olx_aggressive"] = c
    log.info("═══ Phone recovery end ═══")
    return result
