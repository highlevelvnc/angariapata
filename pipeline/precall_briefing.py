"""
Sprint Pre-call Briefing · per-lead dossier for the agent before calling.

Aggregates everything we already know about a lead into a single multi-line
string the operator (Susana) can read in <30s before dialing:

    Portfolio · {N} listings | zonas | tipologias | €X total
    Tempo · {N} dias no mercado · primeiro listing {date}
    Motivação · {urgência keywords} · {price delta}
    Premarket · {licença obras / renovação / mudança} (se houver match)
    Comissão estimada · €{X} a 5%
    Opening · "{linha de abertura personalizada}"

Used in the commercial XLSX (column "Briefing") and the dashboard top-10
panel. Read-only — never writes to the DB.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import or_

from storage.database import get_db
from storage.models   import Lead, PremktSignal


COMMISSION_RATE = 0.05  # Patabrava luxury default

_URGENCY_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\burgente\b|\burgência\b", re.I),              "urgência"),
    (re.compile(r"\bherança\b|\bherdeiro\b|\bpartilha\b", re.I), "herança/partilha"),
    (re.compile(r"\bdivórcio\b|\bseparação\b", re.I),            "divórcio"),
    (re.compile(r"\bemigr\w+\b", re.I),                          "vai emigrar"),
    (re.compile(r"\bpenhora\b|\bexecutiv\w+\b", re.I),           "execução hipotecária"),
    (re.compile(r"\bnegociáv\w+\b|\bnegoci[áa]\w*\b", re.I),     "negociável"),
    (re.compile(r"sem comissão|direto do dono|proprietário vende", re.I),
                                                                  "directo do dono"),
    (re.compile(r"\bpreciso vender\b|\bprecisa vender\b", re.I), "necessidade de vender"),
    (re.compile(r"\bremodelar\b|\brecuperar\b", re.I),           "imóvel para remodelar"),
]


def _short_zone(zone: str | None) -> str:
    if not zone:
        return ""
    return zone.split(",")[0].strip()


def _first_name(name: str | None) -> str:
    if not name:
        return ""
    parts = name.strip().split()
    if not parts:
        return ""
    candidate = parts[0]
    # Reject usernames / handles like "manuelfavila555" or "user_42"
    if any(ch.isdigit() for ch in candidate) or "_" in candidate:
        return ""
    return candidate.title()


def _detect_urgency(lead: Lead) -> list[str]:
    text = f"{lead.title or ''} {lead.description or ''}"
    found = []
    seen: set[str] = set()
    for pat, label in _URGENCY_KEYWORDS:
        if pat.search(text) and label not in seen:
            found.append(label)
            seen.add(label)
    return found


def _premarket_match(lead: Lead) -> Optional[PremktSignal]:
    """
    Best-effort match between a lead and any premarket signal — by name match
    when contact_name is set, falling back to zone-only when name is missing.

    Returns the highest-scoring matching signal, or None.
    """
    name = (lead.contact_name or "").strip()
    zone = _short_zone(lead.zone)
    # Only match when we have a strong name signal (≥2 tokens) OR a name+zone
    # pair. A bare first name like "Maria" has too many false positives.
    name_tokens = [t for t in name.split() if len(t) >= 2]
    if len(name_tokens) < 2 and not zone:
        return None

    with get_db() as db:
        q = db.query(PremktSignal).filter(PremktSignal.promoted == False)  # noqa: E712
        if len(name_tokens) >= 2:
            q = q.filter(PremktSignal.name.ilike(f"%{name}%"))
            if zone:
                q = q.filter(PremktSignal.zone.ilike(f"%{zone}%"))
        else:
            # Name too weak — require zone match AND limit to higher-score signals
            q = q.filter(PremktSignal.zone.ilike(f"%{zone}%"))
            q = q.filter(PremktSignal.signal_score >= 70)
        q = q.order_by(PremktSignal.signal_score.desc()).limit(1)
        return q.first()


_PREMKT_LABELS = {
    "building_permit":         "licença de obras emitida",
    "renovation_ad_homeowner": "anúncio de obras (proprietário)",
    "renovation_ad_generic":   "anúncio de obras",
    "contractor_search_post":  "procura de empreiteiro",
    "linkedin_city_change":    "mudança de cidade (LinkedIn)",
    "linkedin_job_change":     "mudança profissional (LinkedIn)",
}


def _opening_line(
    lead: Lead,
    portfolio_count: int,
    urgency: list[str],
    premkt: Optional[PremktSignal],
) -> str:
    """
    Build a single-sentence opening line for the call.
    PT-PT, polite, mentions the strongest signal we have.
    """
    fn = _first_name(lead.contact_name) or "Boa tarde"
    zone = _short_zone(lead.zone) or "Lisboa"
    typ = (lead.typology or "").strip()
    # "Desconhecido" / "—" leak in from upstream defaults — treat as missing
    if typ.lower() in ("desconhecido", "unknown", "—", "-", ""):
        typ = ""
    subj = (typ + " em " + zone) if typ else f"o seu imóvel em {zone}"

    if urgency:
        hook = f"vi que mencionou {urgency[0]}"
    elif premkt:
        lbl = _PREMKT_LABELS.get(premkt.signal_type, premkt.signal_type)
        hook = f"vi sinais de {lbl} na sua zona"
    elif portfolio_count >= 2:
        hook = f"vi que tem {portfolio_count} imóveis listados"
    elif lead.days_on_market and lead.days_on_market >= 60:
        hook = f"reparei que o anúncio está há {lead.days_on_market} dias online"
    elif (lead.price_delta_pct or 0) >= 10:
        hook = f"o preço está {lead.price_delta_pct:.0f}% abaixo do benchmark da zona"
    else:
        hook = "estou a contactar proprietários directos da sua zona"

    if (lead.lead_type or "").lower() == "frbo":
        action = "ajudar a colocar mais depressa"
    else:
        action = "fazer uma proposta concreta da Pata Brava"

    return f"{fn}, sou da Pata Brava — {hook} sobre {subj}. Posso {action}?"


def build_briefing(lead: Lead) -> dict:
    """
    Build the full briefing for one lead.

    Returns a dict with structured fields plus a `text` rendering ready to
    paste into XLSX cells / dashboard tooltips.
    """
    from pipeline.owner_profile import get_profile

    profile  = get_profile(lead)
    urgency  = _detect_urgency(lead)
    premkt   = _premarket_match(lead)
    dom      = lead.days_on_market or 0
    price    = lead.price or 0
    commission = int(price * COMMISSION_RATE) if price else 0

    opening = _opening_line(lead, profile.listings_count, urgency, premkt)

    lines: list[str] = []

    # Portfolio
    if profile.listings_count >= 2:
        zones = "·".join(profile.zones[:2]) if profile.zones else "—"
        typs  = "/".join(profile.typologies[:2]) if profile.typologies else "—"
        port_v = f"€{profile.portfolio_value:,.0f}".replace(",", " ") if profile.portfolio_value else "—"
        lines.append(f"📊 Portfólio: {profile.listings_count} listings · {zones} · {typs} · {port_v}")
    else:
        lines.append("📊 Portfólio: único listing")

    # Time on market
    if dom >= 90:
        lines.append(f"⏳ Tempo: {dom} dias no mercado (frio — alavancagem para negociação)")
    elif dom >= 45:
        lines.append(f"⏳ Tempo: {dom} dias listado")
    elif dom > 0:
        lines.append(f"⏳ Tempo: {dom} dias listado (recente)")
    else:
        lines.append("⏳ Tempo: anúncio recente")

    # Motivation
    motiv_bits = list(urgency)
    if (lead.price_delta_pct or 0) >= 10:
        motiv_bits.append(f"{lead.price_delta_pct:.0f}% abaixo do benchmark")
    if motiv_bits:
        lines.append("🔥 Motivação: " + " · ".join(motiv_bits))
    else:
        lines.append("🔥 Motivação: sem sinais claros — explorar na chamada")

    # Premarket
    if premkt:
        lbl = _PREMKT_LABELS.get(premkt.signal_type, premkt.signal_type)
        lines.append(f"📡 Premarket: {lbl} (score {premkt.signal_score})")

    # Commission estimate
    if commission:
        com_fmt = f"€{commission:,.0f}".replace(",", " ")
        price_fmt = f"€{int(price):,.0f}".replace(",", " ")
        lines.append(f"💰 Comissão estimada: {com_fmt} (5% sobre {price_fmt})")
    else:
        lines.append("💰 Comissão estimada: preço não disponível")

    # Opening
    lines.append(f"🎯 Opening: \"{opening}\"")

    return {
        "text":            "\n".join(lines),
        "opening":         opening,
        "commission_eur":  commission,
        "urgency":         urgency,
        "portfolio_count": profile.listings_count,
        "premarket_type":  premkt.signal_type if premkt else None,
    }


def build_briefing_text(lead: Lead) -> str:
    """Convenience wrapper returning only the textual rendering."""
    try:
        return build_briefing(lead)["text"]
    except Exception:
        return ""
