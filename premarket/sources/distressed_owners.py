"""
Distressed Owner Signal · INTERNAL premarket source.

Derives premarket signals from our OWN database without scraping anything
external. The hypothesis: an owner who exhibits any of these patterns is
significantly more motivated to sell than a fresh listing, and deserves to
appear in the premarket panel alongside building permits / LinkedIn signals.

Three sub-signals:

  1. distressed_stale (score 75)
     A listing that has been on the market for ≥120 days. The seller has
     already absorbed market feedback that the price/positioning is wrong
     but hasn't relisted with a different agency. These are gold for direct
     owner-to-buyer deals.

  2. distressed_cross_portal (score 65)
     Same phone number appears in 3+ distinct portals (OLX + Imovirtual +
     Sapo + …). The owner is paying for visibility across the market because
     they NEED to sell. Stronger than 2 portals (where it could be cross-
     posting via mediator).

  3. distressed_portfolio (score 55)
     Same phone is responsible for 3+ active listings. Could be an investor
     unwinding a portfolio or a multi-property owner under financial stress.
     Stops at 4+ (then it's a flipper, not a real owner).

Zero scrape cost. Runs offline against the existing Lead table. Output is
the same PremktSignalData container the other sources use, so it slots
into the existing premarket pipeline without changes downstream.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func

from premarket.signals import PremktSignalData
from storage.database import get_db
from storage.models import Lead
from utils.logger import get_logger

log = get_logger(__name__)


# ── Thresholds ───────────────────────────────────────────────────────────────

_STALE_DAYS_THRESHOLD       = 120
_CROSS_PORTAL_MIN_PORTALS   = 3
_PORTFOLIO_MIN              = 3
_PORTFOLIO_MAX              = 4   # 4+ stops being a real owner (flipper)


def _short_zone(zone: Optional[str]) -> Optional[str]:
    if not zone:
        return None
    return zone.split(",")[0].strip() or None


# ── Builders ──────────────────────────────────────────────────────────────────

def _build_stale_signal(lead: Lead) -> PremktSignalData:
    return PremktSignalData(
        signal_type="distressed_stale",
        source="internal_db",
        signal_text=(
            f"Listing {lead.days_on_market}d no mercado · "
            f"{(lead.title or '')[:80]}"
        ),
        location_raw=lead.zone,
        zone=_short_zone(lead.zone),
        name=lead.contact_name,
        url=None,
        extra={
            "lead_id":         lead.id,
            "phone":           lead.contact_phone,
            "days_on_market":  lead.days_on_market,
            "price":           lead.price,
            "discovery_source": lead.discovery_source,
        },
    )


def _build_cross_portal_signal(phone: str, count: int, leads: list[Lead]) -> PremktSignalData:
    """Single signal aggregating the cross-portal owner."""
    head = leads[0]
    portals = sorted({(L.discovery_source or "").lower() for L in leads if L.discovery_source})
    return PremktSignalData(
        signal_type="distressed_cross_portal",
        source="internal_db",
        signal_text=(
            f"Mesmo telefone em {count} portais ({'+'.join(portals)}) · "
            f"{(head.title or '')[:60]}"
        ),
        location_raw=head.zone,
        zone=_short_zone(head.zone),
        name=head.contact_name,
        url=None,
        extra={
            "phone":           phone,
            "portals":         list(portals),
            "lead_ids":        [L.id for L in leads],
            "price_range":     [
                min((L.price or 0) for L in leads),
                max((L.price or 0) for L in leads),
            ],
        },
    )


def _build_portfolio_signal(phone: str, leads: list[Lead]) -> PremktSignalData:
    head = leads[0]
    total_value = sum((L.price or 0) for L in leads)
    return PremktSignalData(
        signal_type="distressed_portfolio",
        source="internal_db",
        signal_text=(
            f"Vendedor com {len(leads)} listings activos · "
            f"portfolio €{total_value:,.0f}".replace(",", " ")
        ),
        location_raw=head.zone,
        zone=_short_zone(head.zone),
        name=head.contact_name,
        url=None,
        extra={
            "phone":           phone,
            "lead_ids":        [L.id for L in leads],
            "portfolio_value": total_value,
        },
    )


# ── Public interface ─────────────────────────────────────────────────────────

class DistressedOwnersSource:
    """
    Internal-DB premarket source. No network, no auth, no API calls.

    Usage:
        source  = DistressedOwnersSource()
        signals = source.fetch(zones=["Lisboa", "Cascais"])
    """

    def fetch(self, zones: list[str] | None = None) -> list[PremktSignalData]:
        signals: list[PremktSignalData] = []

        with get_db() as db:
            base_q = db.query(Lead).filter(Lead.archived == False)  # noqa: E712
            if zones:
                # Match by zone short-name prefix
                from sqlalchemy import or_
                base_q = base_q.filter(or_(*[
                    Lead.zone.ilike(f"{z}%") for z in zones
                ]))

            # ── 1. Stale listings (120+ days) ──────────────────────────────
            stale = base_q.filter(
                Lead.days_on_market >= _STALE_DAYS_THRESHOLD,
                Lead.contact_phone.isnot(None),
                Lead.contact_phone != "",
            ).all()
            for L in stale:
                signals.append(_build_stale_signal(L))
            log.info(
                "[distressed_owners] {n} stale listings (≥{d}d)",
                n=len(stale), d=_STALE_DAYS_THRESHOLD,
            )

            # ── 2. Cross-portal owners (same phone, 3+ portals) ────────────
            phone_groups = (
                db.query(
                    Lead.contact_phone,
                    func.count(func.distinct(Lead.discovery_source)).label("portal_count"),
                )
                .filter(
                    Lead.archived == False,                          # noqa: E712
                    Lead.contact_phone.isnot(None),
                    Lead.contact_phone != "",
                    Lead.discovery_source.isnot(None),
                )
                .group_by(Lead.contact_phone)
                .having(func.count(func.distinct(Lead.discovery_source)) >= _CROSS_PORTAL_MIN_PORTALS)
                .all()
            )
            xp_count = 0
            for phone, n_portals in phone_groups:
                leads = db.query(Lead).filter(
                    Lead.contact_phone == phone, Lead.archived == False,  # noqa: E712
                ).all()
                if zones and not any(
                    (L.zone or "").lower().startswith(z.lower()) for L in leads for z in zones
                ):
                    continue
                signals.append(_build_cross_portal_signal(phone, n_portals, leads))
                xp_count += 1
            log.info(
                "[distressed_owners] {n} cross-portal owners (≥{p} portals)",
                n=xp_count, p=_CROSS_PORTAL_MIN_PORTALS,
            )

            # ── 3. Multi-property owners (3-4 active listings) ─────────────
            portfolio_groups = (
                db.query(Lead.contact_phone, func.count(Lead.id).label("n_listings"))
                .filter(
                    Lead.archived == False,                          # noqa: E712
                    Lead.contact_phone.isnot(None),
                    Lead.contact_phone != "",
                )
                .group_by(Lead.contact_phone)
                .having(func.count(Lead.id).between(_PORTFOLIO_MIN, _PORTFOLIO_MAX))
                .all()
            )
            pf_count = 0
            for phone, n in portfolio_groups:
                leads = db.query(Lead).filter(
                    Lead.contact_phone == phone, Lead.archived == False,  # noqa: E712
                ).all()
                if zones and not any(
                    (L.zone or "").lower().startswith(z.lower()) for L in leads for z in zones
                ):
                    continue
                signals.append(_build_portfolio_signal(phone, leads))
                pf_count += 1
            log.info(
                "[distressed_owners] {n} portfolio owners ({lo}-{hi} listings)",
                n=pf_count, lo=_PORTFOLIO_MIN, hi=_PORTFOLIO_MAX,
            )

        log.info(
            "[distressed_owners] total signals built: {n}",
            n=len(signals),
        )
        return signals
