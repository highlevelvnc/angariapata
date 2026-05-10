"""
eGO Real Estate CRM sync.

Pushes HOT/WARM leads from the Patabrava database into eGO Real Estate
as new contacts/leads, so the agency commercial team works inside their
existing CRM workflow instead of bouncing between tools.

eGO Real Estate API reference:
    https://docs.egorealestate.com   (partners program)

Authentication
--------------
The agency provides an API key + tenant ID once the partner activation
is approved. Set them as environment variables before running sync:

    export EGO_API_KEY="..."
    export EGO_TENANT_ID="..."        # Pata Brava tenant identifier
    export EGO_API_BASE="https://services.egorealestate.com/api/v2"

Operation modes
---------------
* dry-run (default)   — fetches what *would* be pushed, no side-effects
* push-new            — sends only leads not yet seen in eGO (deduped by phone)
* push-update         — pushes new + refreshes stage on existing matches

Field mapping
-------------
    Lead.contact_name      → eGO contact.name
    Lead.contact_phone     → eGO contact.phones[0]
    Lead.contact_email     → eGO contact.emails[0]
    Lead.title + zone      → eGO lead.subject
    Lead.score             → eGO lead.priority (HOT=urgent, WARM=high, COLD=normal)
    Lead.url (sources)     → eGO contact.notes (link back)
    Lead.first_seen_at     → eGO contact.created_at

Status: SCAFFOLD READY · activates 24-48h after Pata Brava authorises API key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional

from utils.logger import get_logger

log = get_logger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EgoConfig:
    api_base: str
    api_key:  str
    tenant:   str
    timeout:  float = 12.0
    dry_run:  bool = True

    @classmethod
    def from_env(cls) -> "EgoConfig":
        return cls(
            api_base = os.getenv("EGO_API_BASE", "https://services.egorealestate.com/api/v2"),
            api_key  = os.getenv("EGO_API_KEY", ""),
            tenant   = os.getenv("EGO_TENANT_ID", ""),
            timeout  = float(os.getenv("EGO_TIMEOUT", "12")),
            dry_run  = os.getenv("EGO_DRY_RUN", "1") == "1",
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.tenant)


# ── Field mapping ─────────────────────────────────────────────────────────────

_PRIORITY_MAP = {
    "HOT":  "urgent",
    "WARM": "high",
    "COLD": "normal",
}


def _lead_to_ego_payload(lead) -> dict:
    """Translate our Lead row into eGO contact+lead payload."""
    sources = []
    try:
        import json
        sources = json.loads(lead.sources_json or "[]")
    except Exception:
        sources = []

    listing_url = sources[0]["url"] if sources else ""
    note_lines = [
        f"Origem: {lead.discovery_source or '—'}",
        f"Score: {lead.score or 0}/100  ({lead.score_label or '—'})",
        f"Tipologia: {lead.typology or '—'}  ·  Área: {lead.area_m2 or '—'} m²",
        f"Preço pedido: {lead.price or '—'} €",
    ]
    if listing_url:
        note_lines.append(f"Anúncio: {listing_url}")

    return {
        "tenant": "{tenant}",       # filled in by client
        "contact": {
            "name":   lead.contact_name or "",
            "phones": [lead.contact_phone] if lead.contact_phone else [],
            "emails": [lead.contact_email] if lead.contact_email else [],
            "source": "patabrava-leadgen",
            "tags":   _build_tags(lead),
        },
        "lead": {
            "subject":  f"{lead.typology or 'Imóvel'} em {lead.zone or 'Lisboa'}",
            "priority": _PRIORITY_MAP.get((lead.score_label or "COLD").upper(), "normal"),
            "stage":    "novo",
            "value":    float(lead.price or 0),
            "owner_type": lead.owner_type or "unknown",
            "notes":    "\n".join(note_lines),
        },
    }


def _build_tags(lead) -> list[str]:
    """Tags the eGO contact gets so the agency can filter inside their CRM."""
    tags: list[str] = ["patabrava-leadgen"]
    if lead.score_label:
        tags.append(lead.score_label.lower())
    if getattr(lead, "is_owner", False):
        tags.append("proprietario-directo")
    if lead.zone:
        tags.append(f"zona:{lead.zone.split(',')[0].strip().lower().replace(' ', '-')}")
    if lead.price and lead.price >= 500_000:
        tags.append("luxury-500k+")
    return tags


# ── Sync engine (skeleton) ────────────────────────────────────────────────────

class EgoSyncer:
    """
    Pushes leads to eGO Real Estate. Operates in dry-run by default;
    flip ``EGO_DRY_RUN=0`` once Pata Brava authorises the API key.
    """

    def __init__(self, config: Optional[EgoConfig] = None):
        self.config = config or EgoConfig.from_env()

    def sync_leads(self, leads: Iterable, mode: str = "push-new") -> dict:
        if not self.config.is_configured:
            log.warning(
                "[ego_sync] not configured — set EGO_API_KEY and EGO_TENANT_ID. "
                "Running in skeleton mode (no requests sent)."
            )
            return self._skeleton_run(leads, mode)

        if self.config.dry_run:
            log.info("[ego_sync] DRY-RUN — payloads built but not sent to eGO.")
            return self._dry_run(leads)

        return self._live_push(leads, mode)

    # ── Internal modes ────────────────────────────────────────────────────────

    def _skeleton_run(self, leads: Iterable, mode: str) -> dict:
        n = 0
        for lead in leads:
            payload = _lead_to_ego_payload(lead)
            log.debug("[ego_sync] would POST contact: {p}", p=payload["contact"]["name"])
            n += 1
        return {"mode": mode, "considered": n, "pushed": 0, "skeleton": True}

    def _dry_run(self, leads: Iterable) -> dict:
        n = 0
        for lead in leads:
            _lead_to_ego_payload(lead)
            n += 1
        return {"mode": "dry-run", "considered": n, "pushed": 0}

    def _live_push(self, leads: Iterable, mode: str) -> dict:
        """
        Real eGO API push.

        Activates once Pata Brava provides credentials. The endpoint is
        ``POST {api_base}/leads`` for new lead+contact combo, and
        ``PATCH {api_base}/leads/{id}`` for status updates.

        Until activation this method intentionally raises so we never
        accidentally send unauthorised requests.
        """
        raise NotImplementedError(
            "Live push pending Pata Brava activation. "
            "Set EGO_DRY_RUN=0 only after the agency authorises the API key."
        )


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def cli_sync(score_label: str = "HOT", limit: int = 100) -> dict:
    """
    Quick CLI sync used by ``python main.py ego-sync``.
    Pushes the top ``limit`` leads of the given score label.
    """
    from storage.database import get_db
    from storage.models import Lead

    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(Lead.score_label == score_label, Lead.archived == False)
            .order_by(Lead.score.desc())
            .limit(limit)
            .all()
        )
        log.info("[ego_sync] fetched {n} leads for sync (score_label={l})", n=len(leads), l=score_label)
        return EgoSyncer().sync_leads(leads, mode="push-new")
