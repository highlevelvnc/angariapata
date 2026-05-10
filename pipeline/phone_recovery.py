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


# ── Sprint I · raw_data deep scan ────────────────────────────────────

def raw_data_deep_scan() -> dict:
    """
    Sprint I · scan FULL raw_data JSON (not just truncated description) for
    phone patterns. The Lead.description field is capped at 2000 chars but
    the original scraper response may have the phone further down.
    """
    stats = {"checked": 0, "recovered": 0, "by_source": {}}
    with get_db() as db:
        # Get leads with no real phone, joined with their raw_listing
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
            # Find matching raw_listing via URL
            try:
                src_list = json.loads(lead.sources_json or "[]")
                url = src_list[0].get("url", "") if src_list else ""
            except Exception:
                url = ""
            if not url:
                continue

            raw = (
                db.query(RawListing)
                .filter(RawListing.url == url)
                .first()
            )
            if not raw or not raw.raw_data:
                continue

            phones = (
                _extract_real_phones_from_text(raw.raw_data) +
                _extract_wame_phones(raw.raw_data)
            )
            if phones:
                lead.contact_phone = phones[0]
                lead.phone_type = classify_phone_type(phones[0][4:])
                lead.contact_source = (lead.contact_source or "") + " + raw_deep"
                stats["recovered"] += 1
                src = lead.discovery_source or "?"
                stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
        db.commit()
    log.info(
        "[recovery.raw_deep] checked={c} recovered={r} by_source={b}",
        c=stats["checked"], r=stats["recovered"], b=stats["by_source"],
    )
    return stats


# ── Sprint K · cross-portal fuzzy title match ────────────────────────

def fuzzy_cross_portal_match() -> dict:
    """
    Sprint K · for each lead with relay phone, look for SIBLING listing on
    OTHER portal with similar title + price + zone + tipologia. If sibling
    has real phone, inherit.

    More aggressive than fingerprint match — catches near-duplicates that
    fail the strict fingerprint hash.
    """
    from difflib import SequenceMatcher

    def title_sim(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower()[:80], b.lower()[:80]).ratio()

    stats = {"checked": 0, "recovered": 0, "by_source": {}}
    with get_db() as db:
        # Bad leads (need recovery)
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

        # Pre-load good leads (with real phone) indexed by zone+typology
        good_leads = (
            db.query(Lead)
            .filter(
                Lead.archived == False,
                Lead.phone_type.in_(("mobile", "landline")),
            )
            .all()
        )
        good_by_key = {}
        for g in good_leads:
            key = ((g.zone or "")[:30], (g.typology or "")[:5])
            good_by_key.setdefault(key, []).append(g)

        for lead in bad_leads:
            key = ((lead.zone or "")[:30], (lead.typology or "")[:5])
            candidates = good_by_key.get(key, [])
            if not candidates:
                continue

            # Filter by price proximity (±10%) + title similarity ≥0.7
            for c in candidates:
                if c.discovery_source == lead.discovery_source:
                    continue
                # Price check (allow ±10%)
                if lead.price and c.price:
                    delta = abs(c.price - lead.price) / max(lead.price, 1)
                    if delta > 0.10:
                        continue
                # Title similarity check
                if title_sim(lead.title, c.title) < 0.6:
                    continue
                # Match found
                lead.contact_phone = c.contact_phone
                lead.phone_type    = c.phone_type
                if not lead.contact_name and c.contact_name:
                    lead.contact_name = c.contact_name
                lead.contact_source = (lead.contact_source or "") + f" + fuzzy_cross({c.discovery_source})"
                stats["recovered"] += 1
                src = lead.discovery_source or "?"
                stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
                break
        db.commit()
    log.info(
        "[recovery.fuzzy] checked={c} recovered={r} by_source={b}",
        c=stats["checked"], r=stats["recovered"], b=stats["by_source"],
    )
    return stats


# ── Sprint J · Detail page re-fetch (httpx, no Playwright) ───────────

def detail_page_rescan(limit: int = 300) -> dict:
    """
    Sprint J · for leads with relay phone, re-fetch the listing detail
    page via httpx (no browser) and aggressively scan the FULL HTML for
    real phones. Sometimes phones are buried in:
      - JSON-LD <script> blocks
      - <meta property="og:phone">
      - inline JS (window.__INITIAL_STATE__)
      - structured data attributes (itemprop="telephone")

    httpx-only = 100x faster than Playwright reveal. Volume-friendly.
    """
    import httpx as _httpx
    stats = {"checked": 0, "fetched": 0, "recovered": 0, "by_source": {}, "errors": 0}

    with get_db() as db:
        bad_leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .filter(or_(
                Lead.phone_type.in_(("relay", "unknown", "invalid")),
                Lead.phone_type.is_(None),
            ))
            .order_by(Lead.score.desc().nullslast())
            .limit(limit)
            .all()
        )
        stats["checked"] = len(bad_leads)
        if not bad_leads:
            return stats

        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
        with _httpx.Client(headers={"User-Agent": ua}, timeout=12, follow_redirects=True) as client:
            for lead in bad_leads:
                try:
                    src_list = json.loads(lead.sources_json or "[]")
                    url = src_list[0].get("url", "") if src_list else ""
                except Exception:
                    url = ""
                if not url:
                    continue
                try:
                    r = client.get(url)
                    if r.status_code != 200:
                        continue
                    stats["fetched"] += 1
                    # Aggressive scan: full HTML + extract real phones
                    phones = _extract_real_phones_from_text(r.text)
                    phones += _extract_wame_phones(r.text)
                    # Also check for itemprop/JSON-LD telephone fields
                    for m in re.finditer(r'"telephone"\s*:\s*"\+?(\d[\d\s\-]{8,15})"', r.text):
                        digits = re.sub(r"\D", "", m.group(1))
                        if digits.startswith("351"):
                            digits = digits[3:]
                        if len(digits) == 9 and classify_phone_type(digits) in ("mobile", "landline"):
                            phones.append("+351" + digits)
                    if phones:
                        # Dedup keep order
                        phones = list(dict.fromkeys(phones))
                        lead.contact_phone = phones[0]
                        lead.phone_type    = classify_phone_type(phones[0][4:])
                        lead.contact_source = (lead.contact_source or "") + " + detail_rescan"
                        stats["recovered"] += 1
                        src = lead.discovery_source or "?"
                        stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
                except Exception:
                    stats["errors"] += 1
        db.commit()
    log.info(
        "[recovery.detail] checked={c} fetched={f} recovered={r} errors={e}",
        c=stats["checked"], f=stats["fetched"], r=stats["recovered"], e=stats["errors"],
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
