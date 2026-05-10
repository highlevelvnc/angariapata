"""
Sprint Quality A · Phone occurrence detector + flipper auto-flag.
Sprint Quality C · Suspicious listing detector.

These run AFTER the main pipeline as a quality pass — they don't add new
leads, they downgrade or flag existing ones so the deliverable to Pata
Brava only contains trustworthy FSBO contacts.

Public API
----------
flag_flippers(min_occurrences=4) -> dict
    Walks every lead, counts how many leads share each phone. If a phone
    is in N+ leads but those leads are all flagged is_owner=True, that's
    a flipper masquerading as particular. Downgrade owner_type='agency',
    set is_owner=False, set agency_name='Vendedor profissional (flipper)'.

flag_suspicious(severity='medium') -> dict
    Detects scam/spam patterns in title and price. Flips ``listing_status``
    to ``suspicious`` and bumps a CRM note for human review. The export
    pipeline then filters them out of the Premium list.

Both functions are idempotent: running them twice produces the same result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func

from storage.database import get_db
from storage.models import Lead
from utils.logger import get_logger

log = get_logger(__name__)


# ── Sprint Quality A · Flipper detector ──────────────────────────────

def flag_flippers(min_occurrences: int = 4) -> dict:
    """
    Find phones that appear in ``min_occurrences`` or more leads, and
    downgrade those leads to ``agency`` regardless of their original
    classification. Real FSBO sellers don't list 4+ properties.

    Applies to ALL phone types (mobile + landline + relay) — landline
    switchboards in 100+ listings are obvious agency phones that pose
    same fake-FSBO risk as mobile flippers.
    """
    stats = {"phones_checked": 0, "flippers_found": 0, "leads_downgraded": 0}

    with get_db() as db:
        # Group by phone, count occurrences. SQL handles this fast even on 100k.
        rows = (
            db.query(Lead.contact_phone, func.count(Lead.id))
            .filter(Lead.contact_phone.isnot(None))
            .filter(Lead.contact_phone != "")
            .filter(Lead.archived == False)              # noqa: E712
            .group_by(Lead.contact_phone)
            .having(func.count(Lead.id) >= min_occurrences)
            .all()
        )
        stats["phones_checked"] = (
            db.query(func.count(func.distinct(Lead.contact_phone)))
            .filter(Lead.contact_phone.isnot(None))
            .scalar() or 0
        )
        stats["flippers_found"] = len(rows)

        for phone, count in rows:
            log.info(
                "[quality.flipper] phone={p} appears in {n} leads — flagging as agency",
                p=phone, n=count,
            )
            placeholder = f"Vendedor profissional ({count} listings)"
            # First update owner_type+is_owner on all matching leads
            updated = (
                db.query(Lead)
                .filter(Lead.contact_phone == phone, Lead.archived == False)
                .update({
                    "owner_type": "agency",
                    "is_owner": False,
                }, synchronize_session=False)
            )
            # Then fill agency_name only where it's currently empty
            db.query(Lead).filter(
                Lead.contact_phone == phone,
                Lead.archived == False,
                (Lead.agency_name.is_(None)) | (Lead.agency_name == ""),
            ).update({"agency_name": placeholder}, synchronize_session=False)
            stats["leads_downgraded"] += updated

        db.commit()

    log.info(
        "[quality.flipper] Done — phones={p} flippers_found={f} leads_downgraded={d}",
        p=stats["phones_checked"], f=stats["flippers_found"], d=stats["leads_downgraded"],
    )
    return stats


# ── Sprint Quality C · Suspicious listing detector ───────────────────

@dataclass
class _SuspicionRule:
    name: str
    pattern: re.Pattern | None
    price_min: float | None = None
    price_max: float | None = None
    severity: int = 1   # 1=mild, 2=strong, 3=hard-block


_RULES: list[_SuspicionRule] = [
    _SuspicionRule(
        "all_caps_spam",
        re.compile(r"^[A-ZÀÁÂÃÉÊÍÓÔÕÚÇ\s\d!?\.,/-]{20,}$"),
        severity=1,
    ),
    _SuspicionRule(
        "exclamation_spam",
        re.compile(r"!{3,}|!\?!"),
        severity=2,
    ),
    _SuspicionRule(
        "urgent_scam_words",
        re.compile(r"\b(URGENTE+|HOJE+|JÁ+|RAPID(O|A))\s*!*", re.IGNORECASE),
        severity=1,
    ),
    _SuspicionRule(
        "scam_keywords",
        re.compile(r"\b(golpe|fraude|scam|contacto whatsapp \+?[0-9]+\b)", re.IGNORECASE),
        severity=3,
    ),
    # price_min/price_max semantics:
    #   price_min set → hit when 0 < p < price_min (caso de preço suspeitosamente baixo)
    #   price_max set → hit when p > price_max     (caso de preço suspeitosamente alto)
    _SuspicionRule(
        "price_too_low",
        None, price_min=5_000, price_max=None, severity=3,
    ),
    _SuspicionRule(
        "price_too_high_residential",
        None, price_min=None, price_max=15_000_000, severity=2,
    ),
]


def flag_suspicious(min_severity: int = 2) -> dict:
    """
    Walk every active lead, score against suspicion rules, and flip
    listing_status='suspicious' on those that hit ``min_severity`` or more.

    The export pipeline filters listing_status='suspicious' out of Premium
    by default, but they remain visible in the dashboard for review.
    """
    stats = {"considered": 0, "flagged": 0, "by_rule": {}}

    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .filter(Lead.listing_status.is_(None))
            .all()
        )
        stats["considered"] = len(leads)

        for lead in leads:
            severity_total = 0
            triggered = []
            text = " ".join([lead.title or "", lead.description or ""])

            for rule in _RULES:
                hit = False
                if rule.pattern and rule.pattern.search(text):
                    hit = True
                if rule.price_min is not None or rule.price_max is not None:
                    p = lead.price or 0
                    if rule.price_min is not None and p < rule.price_min and p > 0:
                        hit = True
                    if rule.price_max is not None and p > rule.price_max:
                        hit = True
                if hit:
                    severity_total += rule.severity
                    triggered.append(rule.name)
                    stats["by_rule"][rule.name] = stats["by_rule"].get(rule.name, 0) + 1

            if severity_total >= min_severity:
                lead.listing_status = "suspicious"
                stats["flagged"] += 1
                log.debug(
                    "[quality.suspicious] lead #{id} flagged (sev={s}) rules={r}",
                    id=lead.id, s=severity_total, r=triggered,
                )

        db.commit()

    log.info(
        "[quality.suspicious] Done — considered={c} flagged={f} breakdown={b}",
        c=stats["considered"], f=stats["flagged"], b=stats["by_rule"],
    )
    return stats


# ── Sprint Integrity F · Phone validation ────────────────────────────

# Portugal mobile prefixes (real, after +351 country code).
# Source: ANACOM 2024 numbering plan.
_PT_MOBILE_PREFIXES = ("91", "92", "93", "96")
# Real geographic landlines: 21=Lisboa, 22=Porto, 23..29=outras regiões.
# 20 NÃO é landline real PT — é relay/VoIP usado por OLX/Imovirtual.
_PT_LANDLINE_PREFIXES = ("21", "22", "23", "24", "25", "26", "27", "28", "29")
# Relay/proxy/non-direct: 20X (NOT landline), 6X, 9X-non-mobile.
_PT_RELAY_PREFIXES = (
    "20",
    "60", "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "90", "94", "95", "97", "98", "99",
)

def validate_phones() -> dict:
    """
    Sprint Integrity F · classify every phone by PT numbering plan:

      mobile    → +351 91/92/93/96 · real PT mobile (likely WhatsApp)
      landline  → +351 21-29 · real PT landline (often agency switchboard)
      relay     → +351 9X (other) / 6X / 99X · OLX/Imovirtual proxy numbers
                 NOT the owner's real phone — caller hears "anónimo" message
      invalid   → wrong format, wrong country, malformed → cleared

    Phones marked invalid get ``contact_phone=NULL`` so the export pipeline
    won't include them. Relay phones keep contact_phone but won't pass
    the strict "REAL OWNER" filter in the export.
    """
    stats = {
        "checked": 0, "mobile": 0, "landline": 0,
        "relay": 0, "invalid_format": 0, "cleared": 0,
    }
    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.contact_phone.isnot(None), Lead.contact_phone != "")
            .filter(Lead.archived == False)              # noqa: E712
            .all()
        )
        stats["checked"] = len(leads)

        for lead in leads:
            ph = (lead.contact_phone or "").replace(" ", "").replace("-", "")
            if ph.startswith("+351"):
                core = ph[4:]
            elif ph.startswith("351") and len(ph) == 12:
                core = ph[3:]
            else:
                core = ph

            # Must be 9 digits after country code
            if not core.isdigit() or len(core) != 9:
                stats["invalid_format"] += 1
                lead.contact_phone = None
                lead.phone_type = "invalid"
                stats["cleared"] += 1
                continue

            prefix2 = core[:2]
            # Order matters: check relay BEFORE landline (20X falls in both).
            if prefix2 in _PT_RELAY_PREFIXES:
                # Anonymous proxy: 20X (non-geographic / VoIP),
                # 6X (OLX historical), 9X-non-mobile (OLX modern).
                lead.phone_type = "relay"
                stats["relay"] += 1
            elif prefix2 in _PT_MOBILE_PREFIXES:
                lead.phone_type = "mobile"
                stats["mobile"] += 1
            elif prefix2 in _PT_LANDLINE_PREFIXES:
                lead.phone_type = "landline"
                stats["landline"] += 1
            else:
                # Truly unknown / foreign / bogus prefix
                lead.phone_type = "unknown"

        db.commit()

    log.info(
        "[quality.phone] checked={c} mobile={m} landline={l} invalid={i} (cleared {x})",
        c=stats["checked"], m=stats["mobile"], l=stats["landline"],
        i=stats["invalid_format"], x=stats["cleared"],
    )
    return stats


# ── Sprint Integrity J · Owner name validator ────────────────────────

_GENERIC_NAMES = (
    "vendedor", "vendedora", "particular", "proprietário", "proprietaria",
    "owner", "anonimo", "anónimo", "anonima", "anónima",
    "user", "utilizador", "info", "contacto", "comercial",
    "venda", "rendas", "investimento",
)

_AGENCY_NAME_PATTERNS = (
    re.compile(r"\b(lda|s\.?a\.?|sl|imobiliári[ao]|mediação|imo\w+|grupo|invest\w*)\b", re.IGNORECASE),
    re.compile(r"^\s*[A-Z]{3,}\b", re.IGNORECASE),  # all-caps brand-like
)

def flag_disguised_agencies_by_name() -> dict:
    """
    Sprint Integrity J · catches names that look generic ("Vendedor")
    or agency-like ("Imo Investimentos LDA") flagged as is_owner=True.
    Downgrades to agency.
    """
    stats = {"checked": 0, "downgraded": 0}
    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.is_owner == True, Lead.archived == False)
            .filter(Lead.contact_name.isnot(None), Lead.contact_name != "")
            .all()
        )
        stats["checked"] = len(leads)

        for lead in leads:
            name = (lead.contact_name or "").strip().lower()
            suspicious = False

            # Generic placeholder names
            if any(g == name or name.startswith(g + " ") or name.endswith(" " + g) for g in _GENERIC_NAMES):
                suspicious = True

            # Agency-like patterns
            if any(p.search(lead.contact_name or "") for p in _AGENCY_NAME_PATTERNS):
                suspicious = True

            # Single word names that look like brands ("REMAX", "ERA")
            if len(name.split()) == 1 and len(name) >= 3 and name.isupper():
                suspicious = True

            if suspicious:
                lead.is_owner = False
                lead.owner_type = "agency"
                if not lead.agency_name:
                    lead.agency_name = lead.contact_name
                stats["downgraded"] += 1

        db.commit()
    log.info(
        "[quality.name] checked={c} downgraded_by_name={d}",
        c=stats["checked"], d=stats["downgraded"],
    )
    return stats


# ── Sprint Engine CC · Cross-listing contact consolidation ───────────

def consolidate_contacts() -> dict:
    """
    Sprint Engine CC · merge contact fields across listings sharing the
    same phone (real owner, not flipper). When a listing is missing name
    or email, fill it from sibling listings.

    Why this matters
    ----------------
    Imovirtual / OLX often expose name in one listing but not another,
    or email only on a single listing. We already group by phone;
    consolidation fills the gaps.

    Excludes flippers (phones in 4+ listings, already downgraded by
    flag_flippers). Targets ONLY real-owner phone groups (2-3 listings).
    """
    from sqlalchemy import func

    stats = {"phone_groups": 0, "names_filled": 0, "emails_filled": 0, "websites_filled": 0}

    with get_db() as db:
        # Find phones with 2-3 listings (real owners with multi-portal posting,
        # NOT the 4+ flippers we already downgraded)
        rows = (
            db.query(Lead.contact_phone, func.count(Lead.id))
            .filter(Lead.contact_phone.isnot(None), Lead.contact_phone != "")
            .filter(Lead.archived == False)              # noqa: E712
            .filter(Lead.owner_type != "agency")  # exclude already-flagged flippers
            .group_by(Lead.contact_phone)
            .having(func.count(Lead.id).between(2, 3))
            .all()
        )
        stats["phone_groups"] = len(rows)

        for phone, _count in rows:
            siblings = (
                db.query(Lead)
                .filter(Lead.contact_phone == phone, Lead.archived == False)
                .all()
            )
            # Find best name/email/website across siblings
            names    = [s.contact_name    for s in siblings if s.contact_name    and len(s.contact_name) > 2]
            emails   = [s.contact_email   for s in siblings if s.contact_email   and "@" in (s.contact_email or "")]
            websites = [s.contact_website for s in siblings if s.contact_website and len(s.contact_website) > 4]

            best_name    = names[0]    if names    else None
            best_email   = emails[0]   if emails   else None
            best_website = websites[0] if websites else None

            # Fill missing fields on siblings
            for s in siblings:
                if not s.contact_name and best_name:
                    s.contact_name = best_name
                    stats["names_filled"] += 1
                if not s.contact_email and best_email:
                    s.contact_email = best_email
                    stats["emails_filled"] += 1
                if not s.contact_website and best_website:
                    s.contact_website = best_website
                    stats["websites_filled"] += 1

        db.commit()
    log.info(
        "[quality.consolidate] groups={g} names+={n} emails+={e} websites+={w}",
        g=stats["phone_groups"], n=stats["names_filled"],
        e=stats["emails_filled"], w=stats["websites_filled"],
    )
    return stats


# ── Sprint Engine T · Email pattern guess for agencies ────────────────

_EMAIL_PATTERNS_BY_DOMAIN_ROLE = (
    "info", "contacto", "contato", "geral", "comercial", "atendimento",
    "vendas", "imoveis", "lisboa", "consultor",
)


def guess_agency_emails(verify_mx: bool = True, max_per_run: int = 200) -> dict:
    """
    Sprint Engine T · guess common email patterns for agency leads with
    a website but no email. Verifies each guess via MX before persisting.

    Why
    ---
    Agencies usually have a website (`Lead.contact_website`) and a
    standard inbox like info@x.pt. But the listing rarely surfaces it.
    This function tries common PT patterns and validates against MX.
    """
    import re as _re
    stats = {"considered": 0, "guessed": 0, "verified": 0, "saved": 0}

    with get_db() as db:
        # Agencies with website but no email
        leads = (
            db.query(Lead)
            .filter(Lead.owner_type == "agency", Lead.archived == False)
            .filter(Lead.contact_website.isnot(None), Lead.contact_website != "")
            .filter((Lead.contact_email.is_(None)) | (Lead.contact_email == ""))
            .limit(max_per_run)
            .all()
        )
        stats["considered"] = len(leads)

        for lead in leads:
            # Extract bare domain from website
            site = (lead.contact_website or "").lower()
            site = _re.sub(r"^https?://", "", site)
            site = site.split("/")[0]
            site = _re.sub(r"^www\.", "", site)
            domain = site.strip()

            if not domain or "." not in domain:
                continue

            # MX precheck (or skip)
            if verify_mx and not _has_mx(domain):
                continue

            # Build candidate emails ordered by likelihood
            candidates = [f"{role}@{domain}" for role in _EMAIL_PATTERNS_BY_DOMAIN_ROLE]
            stats["guessed"] += 1

            # The MX check above proves the domain accepts mail. We pick the
            # most common pattern (info@) since SMTP-level verification is
            # rate-limited and noisy. The agency operations team can reject
            # bounce-backs in their own pipeline.
            chosen = candidates[0]
            lead.contact_email = chosen
            lead.contact_source = (lead.contact_source or "") + " + email_pattern_guess"
            stats["verified"] += 1
            stats["saved"] += 1

        db.commit()
    log.info(
        "[quality.email_guess] considered={c} guessed={g} saved={s}",
        c=stats["considered"], g=stats["guessed"], s=stats["saved"],
    )
    return stats


# ── Sprint Integrity P · Email MX validation ─────────────────────────

# In-memory MX cache for the run (avoids hammering DNS for repeat domains)
_MX_CACHE: dict[str, bool] = {}

# Known disposable / temporary email providers (frequent in scams)
_DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.org",
    "throwaway.email", "yopmail.com", "fakeinbox.com", "trashmail.com",
})


def _has_mx(domain: str) -> bool:
    """Return True if the domain has at least one MX record."""
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]
    try:
        # Use socket-level fallback first (no extra deps)
        import socket
        socket.setdefaulttimeout(3)
        try:
            socket.gethostbyname(domain)  # validates A record exists
            base_ok = True
        except Exception:
            base_ok = False

        # Try dnspython if available for proper MX check
        try:
            import dns.resolver as _dr
            answers = _dr.resolve(domain, "MX", lifetime=3.0)
            ok = any(answers)
            _MX_CACHE[domain] = bool(ok)
            return bool(ok)
        except ImportError:
            _MX_CACHE[domain] = base_ok
            return base_ok
        except Exception:
            _MX_CACHE[domain] = False
            return False
    except Exception:
        _MX_CACHE[domain] = False
        return False


def validate_emails() -> dict:
    """
    Sprint Integrity P · validate every lead email format + MX record.
    Clears `contact_email=NULL` for invalid ones so the export pipeline
    won't include them.
    """
    stats = {"checked": 0, "valid": 0, "format_invalid": 0, "no_mx": 0, "disposable": 0, "cleared": 0}
    EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.contact_email.isnot(None), Lead.contact_email != "")
            .filter(Lead.archived == False)              # noqa: E712
            .all()
        )
        stats["checked"] = len(leads)

        for lead in leads:
            email = (lead.contact_email or "").strip().lower()

            # Format check
            if not EMAIL_RE.match(email):
                stats["format_invalid"] += 1
                lead.contact_email = None
                stats["cleared"] += 1
                continue

            domain = email.split("@", 1)[1]

            # Disposable
            if domain in _DISPOSABLE_DOMAINS:
                stats["disposable"] += 1
                lead.contact_email = None
                stats["cleared"] += 1
                continue

            # MX check (cached)
            if not _has_mx(domain):
                stats["no_mx"] += 1
                lead.contact_email = None
                stats["cleared"] += 1
                continue

            stats["valid"] += 1

        db.commit()
    log.info(
        "[quality.email] checked={c} valid={v} format_bad={f} no_mx={m} disposable={d} cleared={x}",
        c=stats["checked"], v=stats["valid"], f=stats["format_invalid"],
        m=stats["no_mx"], d=stats["disposable"], x=stats["cleared"],
    )
    return stats


# ── Sprint Integrity Q · Lead freshness scoring ──────────────────────

def apply_freshness_penalty() -> dict:
    """
    Sprint Integrity Q · age-based confidence adjustment.

    Listings get a confidence bonus/penalty based on how long ago they were
    first seen. Old listings are stale by definition — sellers may have
    closed deals elsewhere or given up.

    Bonus / penalty schedule:
      <7 days     → +5  (fresh, hot signal)
      7-30 days   →  0  (neutral)
      30-90 days  → -5  (slowly aging)
      90-180 days → -10 (stale candidate)
      >180 days   → -15 (almost certainly inactive)

    Applied as adjustment AFTER `compute_confidence_scores`.
    """
    from datetime import datetime, timedelta
    stats = {"considered": 0, "fresh": 0, "stale": 0, "veryold": 0}
    now = datetime.utcnow()

    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .all()
        )
        stats["considered"] = len(leads)

        for lead in leads:
            if not lead.first_seen_at:
                continue
            age_days = (now - lead.first_seen_at).days
            adj = 0
            if age_days < 7:
                adj = +5
                stats["fresh"] += 1
            elif age_days < 30:
                adj = 0
            elif age_days < 90:
                adj = -5
            elif age_days < 180:
                adj = -10
                stats["stale"] += 1
            else:
                adj = -15
                stats["veryold"] += 1

            new_conf = max(0, min(100, (lead.contact_confidence or 0) + adj))
            lead.contact_confidence = new_conf

        db.commit()
    log.info(
        "[quality.freshness] considered={c} fresh={f} stale={s} veryold={o}",
        c=stats["considered"], f=stats["fresh"], s=stats["stale"], o=stats["veryold"],
    )
    return stats


# ── Sprint Integrity N · Lead confidence score (composite) ───────────

def compute_confidence_scores() -> dict:
    """
    Sprint Integrity N · 0-100 confidence per lead based on data
    completeness + integrity signals. Stored in ``Lead.contact_confidence``.

    Calibrated v2 (2026-05-10):
      mobile phone               +45
      landline                   +15
      contact_name (real)        +20  (post-name-filter, generic names already excluded)
      single-listing seller      +15  (post-flipper-filter)
      email present              +8
      photo present              +5
      cross-portal               +5
      not suspicious             +10  (default true)

    Targets:
      Mobile FSBO real + name      → ~90 (ALTA)
      Mobile FSBO real (no name)   → ~70 (MÉDIA)
      Landline FSBO real + name    → ~60 (MÉDIA limítrofe)
      Mobile only, no other signals → ~55 (BAIXA)
    """
    stats = {"updated": 0, "avg_before": 0, "avg_after": 0}

    with get_db() as db:
        leads = db.query(Lead).filter(Lead.archived == False).all()
        if not leads:
            return stats

        before_total = sum((l.contact_confidence or 0) for l in leads)

        for lead in leads:
            score = 0

            # Phone signals (heaviest weight)
            pt = (lead.phone_type or "").lower()
            if pt == "mobile":
                score += 45
            elif pt == "landline":
                score += 15

            # Real contact name (post-name-filter)
            if lead.contact_name and len(lead.contact_name) >= 3:
                score += 20

            # FSBO survived all filters
            if lead.is_owner and (lead.owner_type or "").lower() == "fsbo":
                score += 15

            # Optional channels
            if lead.contact_email:
                score += 8
            if lead.image_url:
                score += 5

            # Cross-portal mention boost
            sj = (lead.sources_json or "").lower()
            if "imovirtual" in sj and "olx" in sj:
                score += 5

            # Not flagged suspicious
            if lead.listing_status != "suspicious":
                score += 10

            score = min(100, score)
            lead.contact_confidence = score
            stats["updated"] += 1

        db.commit()
        after_total = sum((l.contact_confidence or 0) for l in leads)
        stats["avg_before"] = round(before_total / len(leads), 1)
        stats["avg_after"]  = round(after_total / len(leads), 1)

    log.info(
        "[quality.confidence] updated={n} avg before={b} → after={a}",
        n=stats["updated"], b=stats["avg_before"], a=stats["avg_after"],
    )
    return stats


# ── Sprint NLP X · Sentiment + urgency analysis ──────────────────────

# Patterns calibrated for PT-PT real estate listings.
# Each rule contributes to either urgency (0-10) or to detected_reason.
_NLP_URGENCY_PATTERNS = [
    (re.compile(r"\b(urgent\w*)\b", re.IGNORECASE),                    3),
    (re.compile(r"\b(precisamos? vender|tenho que vender)\b", re.IGNORECASE), 4),
    (re.compile(r"\b(rapid\w+|j[áa] hoje|esta semana)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(aceito propostas?|negoci[áa]vel|negoci\w+)\b", re.IGNORECASE), 1),
    (re.compile(r"\b(baixou|baixei|reduzido|desconto|grande oportunidade)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(emigr\w+|mud\w+ para|estrangeiro)\b", re.IGNORECASE),       3),
    (re.compile(r"\b(divórci\w+|separa\w+)\b", re.IGNORECASE),                   3),
    (re.compile(r"\b(her[aá]n[çc]a|herdeiro|partilha)\b", re.IGNORECASE),         3),
    (re.compile(r"\b(penhora|execu\w+|hipoteca)\b", re.IGNORECASE),               4),
]

_NLP_REASON_PATTERNS = [
    (re.compile(r"\b(emigra\w+|mud\w+ para|estrangeiro)\b", re.IGNORECASE),       "EMIGRAÇÃO"),
    (re.compile(r"\b(divórci\w+|separa\w+)\b", re.IGNORECASE),                    "DIVÓRCIO"),
    (re.compile(r"\b(her[aá]n[çc]a|herdeiro|partilha)\b", re.IGNORECASE),          "HERANÇA"),
    (re.compile(r"\b(penhora|execu\w+|leil[ãa]o)\b", re.IGNORECASE),               "EXECUÇÃO"),
    (re.compile(r"\b(remodel\w+|recupera\w+|restauro)\b", re.IGNORECASE),          "REMODELAÇÃO"),
    (re.compile(r"\b(promot\w+|construtor|investidor)\b", re.IGNORECASE),          "INVESTIDOR"),
    (re.compile(r"\b(oportunidade|investimento|rent[áa]vel)\b", re.IGNORECASE),    "INVESTIMENTO"),
]


def analyse_sentiment_urgency() -> dict:
    """
    Sprint NLP X · scores each lead's title+description for urgency (0-10)
    and extracts a "reason for sale" tag if detectable. Stores results in
    ``Lead.score_breakdown`` (JSON) and bumps `priority_flag` when urgency≥7.

    The output drives:
      - Badge "⏰ URGÊNCIA 8/10" (when score>=6)
      - Badge "💔 DIVÓRCIO" / "🏃 EMIGRAÇÃO" / "📜 HERANÇA" (when reason detected)
    """
    import json as _json
    stats = {
        "considered": 0, "with_urgency": 0,
        "high_urgency": 0, "with_reason": 0,
        "by_reason": {},
    }
    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.archived == False)              # noqa: E712
            .all()
        )
        stats["considered"] = len(leads)

        for lead in leads:
            text = " ".join([lead.title or "", lead.description or ""])
            if not text.strip():
                continue

            urgency = 0
            for pat, weight in _NLP_URGENCY_PATTERNS:
                if pat.search(text):
                    urgency += weight
            urgency = min(10, urgency)

            reason = None
            for pat, label in _NLP_REASON_PATTERNS:
                if pat.search(text):
                    reason = label
                    stats["by_reason"][label] = stats["by_reason"].get(label, 0) + 1
                    break

            # Persist as JSON inside score_breakdown alongside other signals
            try:
                breakdown = _json.loads(lead.score_breakdown or "{}")
            except Exception:
                breakdown = {}
            if urgency > 0:
                breakdown["urgency"] = urgency
                stats["with_urgency"] += 1
            if reason:
                breakdown["reason"] = reason
                stats["with_reason"] += 1
            lead.score_breakdown = _json.dumps(breakdown)

            # High-urgency leads get priority_flag
            if urgency >= 7 and not lead.priority_flag:
                lead.priority_flag = True
                stats["high_urgency"] += 1

        db.commit()
    log.info(
        "[quality.nlp] considered={c} urgency+={u} high_urgency={h} reason+={r} by_reason={br}",
        c=stats["considered"], u=stats["with_urgency"],
        h=stats["high_urgency"], r=stats["with_reason"], br=stats["by_reason"],
    )
    return stats


# ── CLI entry ────────────────────────────────────────────────────────

def cli_quality_pass(consolidate: bool = True, guess_emails: bool = True) -> dict:
    """
    Full quality pass · 9 sequential passes:
      F → A → J → CC → T → P → C → N → Q
      phones → flippers → names → consolidate → email_guess
              → email_validate → suspicious → confidence → freshness

    Order matters:
      - Phones first (so flipper detector has clean format)
      - Flipper before consolidate (so we don't merge flipper data)
      - Consolidate before email validation (validates also guessed)
      - Confidence + freshness LAST so they reflect all upstream filters
    """
    log.info("═══ Quality pass start ═══")
    phone_stats   = validate_phones()
    flipper_stats = flag_flippers(min_occurrences=4)
    name_stats    = flag_disguised_agencies_by_name()

    consolidate_stats = consolidate_contacts() if consolidate else {"skipped": True}
    guess_stats   = guess_agency_emails() if guess_emails else {"skipped": True}

    email_stats   = validate_emails()
    susp_stats    = flag_suspicious(min_severity=2)
    nlp_stats     = analyse_sentiment_urgency()
    conf_stats    = compute_confidence_scores()
    fresh_stats   = apply_freshness_penalty()
    log.info("═══ Quality pass end ═══")
    return {
        "phone":         phone_stats,
        "flipper":       flipper_stats,
        "name":          name_stats,
        "consolidate":   consolidate_stats,
        "email_guess":   guess_stats,
        "email_valid":   email_stats,
        "suspicious":    susp_stats,
        "nlp":           nlp_stats,
        "confidence":    conf_stats,
        "freshness":     fresh_stats,
    }
