"""
Sprint Engine WW · Owner CRM profile aggregator.

For each lead, aggregate all OTHER listings sharing the same phone (the
"real owner" behind multiple posts). Surfaces a single-glance view of
the seller's portfolio:

    listings_count = 3
    zones          = {"Cascais", "Sintra"}
    typologies     = {"Moradia", "T3"}
    price_range    = (450_000, 1_200_000)
    portfolio_value = 1_950_000
    oldest_listing  = 2026-04-12
    relisting_signal = True / False

This is a READ-ONLY aggregation — no DB writes. Used in the commercial
export to add an "Owner Profile" column.

Excluded by design: phones already flagged as flippers (4+ listings).
Those are agencies, not real owners. We only profile owners with 1-3
listings (genuine multi-property owners).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from storage.database import get_db
from storage.models   import Lead


@dataclass
class OwnerProfile:
    listings_count: int = 1
    zones: list[str] = field(default_factory=list)
    typologies: list[str] = field(default_factory=list)
    price_min: float = 0.0
    price_max: float = 0.0
    portfolio_value: float = 0.0
    oldest_listing: Optional[datetime] = None
    is_multi_property: bool = False  # owner has >1 active listing
    # Sprint Cross-Portal 2026-05: which portals the same phone shows up in.
    # A phone appearing in OLX + Imovirtual is a stronger owner-identity
    # signal than appearing once in either.
    portals: list[str] = field(default_factory=list)
    cross_portal: bool = False


def get_profile(lead: Lead, max_listings: int = 3) -> OwnerProfile:
    """
    Build profile for a single lead by aggregating siblings via phone match.
    Caller should NOT call this for flagged flippers (already excluded by
    quality_filter); we still cap at max_listings as defence.
    """
    if not lead.contact_phone:
        return OwnerProfile()

    with get_db() as db:
        siblings = (
            db.query(Lead)
            .filter(
                Lead.contact_phone == lead.contact_phone,
                Lead.archived == False,                  # noqa: E712
            )
            .all()
        )
    if len(siblings) > max_listings:
        # Flipper that escaped the filter — only profile self
        siblings = [s for s in siblings if s.id == lead.id]

    p = OwnerProfile(listings_count=len(siblings))
    prices    = [s.price       for s in siblings if s.price]
    zones     = [s.zone.split(",")[0].strip() for s in siblings if s.zone]
    typolog   = [s.typology    for s in siblings if s.typology]
    seen_at   = [s.first_seen_at for s in siblings if s.first_seen_at]

    p.zones          = sorted(set(z for z in zones if z))
    p.typologies     = sorted(set(t for t in typolog if t))
    p.price_min      = min(prices) if prices else 0
    p.price_max      = max(prices) if prices else 0
    p.portfolio_value = sum(prices) if prices else 0
    p.oldest_listing = min(seen_at) if seen_at else None
    p.is_multi_property = len(siblings) >= 2
    # Cross-portal identity: same phone across distinct portals
    portals = sorted({(s.discovery_source or "").lower() for s in siblings
                      if s.discovery_source})
    p.portals = [pt for pt in portals if pt]
    p.cross_portal = len(p.portals) >= 2
    return p


def format_profile_summary(p: OwnerProfile) -> str:
    """Compact one-line summary for XLSX cell or HTML tooltip."""
    if p.listings_count <= 1:
        # Even a single-listing owner can carry cross-portal signal if the
        # same phone shows up only once but in multiple portals (rare).
        if p.cross_portal:
            return "Único · 🔗 " + "+".join(p.portals)
        return "Único listing"
    parts = [f"{p.listings_count} listings"]
    if p.cross_portal:
        parts.append("🔗 " + "+".join(p.portals[:3]))
    if p.zones:
        parts.append("·".join(p.zones[:2]))
    if p.typologies:
        parts.append("/".join(p.typologies[:2]))
    if p.portfolio_value:
        parts.append(f"€{p.portfolio_value:,.0f}".replace(",", " "))
    return " · ".join(parts)
