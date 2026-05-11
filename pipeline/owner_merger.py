"""
Owner Identity Merging · Sprint 2026-05-11

Groups leads that belong to the SAME real owner under a stable
`owner_identity_id`. Detection logic:

  1. Same phone number          → same identity (strongest signal)
  2. Same name (normalised) AND same first-zone → likely same person
  3. Name fuzzy-match ≥ 0.88 AND same phone area-code zone

Why this matters
-----------------
"Maria S.", "Maria Silva", "M Silva" with the same phone are obviously the
same person — but until now we treated them as 3 separate leads with
divergent contact_names and split portfolios. Merging:

  - Consolidates the portfolio view (3 listings → 1 owner profile)
  - Fixes the contact_name to the longest/most-complete variant
  - Avoids the operator calling the same person 3 times under 3 names
  - Makes the cross-portal badge work reliably

Implementation
--------------
- Adds a column `owner_identity_id` on Lead (INTEGER, indexed)
- Adds a sibling table `owner_identities` with the canonical name + phone
- `compute_identities()` runs a single offline batch over the Lead table:
  1. Build phone → leads map
  2. Within each phone-group, pick the longest name as canonical
  3. For leads WITHOUT phone, group by (zone, normalised name) when name
     looks personal (passes _is_personal_name)
- Idempotent: re-runs reset assignments before recomputing

No external scrape. Pure SQL + Python. Run via `python main.py merge-owners`.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import text

from storage.database import get_db
from storage.models   import Lead
from utils.logger     import get_logger
from reports.commercial_export import _is_personal_name

log = get_logger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalise(name: str) -> str:
    """Lower-case, strip accents, collapse whitespace + punctuation."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z\s]", " ", s).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _short_zone(zone: Optional[str]) -> str:
    if not zone:
        return ""
    return zone.split(",")[0].strip().lower()


def _name_similarity(a: str, b: str) -> float:
    """Token-set Jaccard + sequence ratio; 0..1."""
    na, nb = _normalise(a), _normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Token-set: full match if one is a prefix/superset of the other
    ta, tb = set(na.split()), set(nb.split())
    if ta and tb:
        jacc = len(ta & tb) / len(ta | tb)
    else:
        jacc = 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    return 0.5 * jacc + 0.5 * seq


def _pick_canonical_name(names: list[str]) -> str:
    """From a group of name variants, pick the most complete one."""
    cands = [n for n in names if n and n.strip()]
    if not cands:
        return ""
    # Prefer longest name with most distinct tokens
    cands.sort(
        key=lambda n: (len(set(_normalise(n).split())), len(n.strip())),
        reverse=True,
    )
    return cands[0].strip()


# ── Migration ────────────────────────────────────────────────────────────────

def ensure_schema() -> None:
    """Add owner_identity_id column if missing. SQLite-safe."""
    with get_db() as db:
        cols = {row[1] for row in db.execute(
            text("PRAGMA table_info(leads)")
        ).fetchall()}
        if "owner_identity_id" not in cols:
            db.execute(text("ALTER TABLE leads ADD COLUMN owner_identity_id INTEGER"))
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_leads_owner_identity_id "
                "ON leads(owner_identity_id)"
            ))
            db.commit()
            log.info("[owner_merger] schema migrated: owner_identity_id + index")


# ── Core ─────────────────────────────────────────────────────────────────────

def compute_identities(
    name_threshold: float = 0.88,
    dry_run: bool = False,
) -> dict:
    """
    Single-pass identity assignment over all non-archived leads.

    Returns stats:
        {phone_groups, name_groups, total_identities, leads_assigned,
         leads_without_identity}
    """
    ensure_schema()
    stats = defaultdict(int)
    identity_counter = 0
    assignments: dict[int, int] = {}     # lead_id → owner_identity_id

    with get_db() as db:
        leads = db.query(Lead).filter(Lead.archived == False).all()  # noqa: E712

        # ── Stage 1 · phone groups ────────────────────────────────────────────
        phone_groups: dict[str, list[Lead]] = defaultdict(list)
        for L in leads:
            ph = (L.contact_phone or "").strip()
            if ph:
                phone_groups[ph].append(L)
        for ph, group in phone_groups.items():
            identity_counter += 1
            stats["phone_groups"] += 1
            for L in group:
                assignments[L.id] = identity_counter

        # ── Stage 2 · phoneless leads → fuzzy name + zone groups ──────────────
        unassigned = [L for L in leads if L.id not in assignments]
        # Bucket by zone+first-letter for cheap candidate filtering
        bucket: dict[tuple, list[Lead]] = defaultdict(list)
        for L in unassigned:
            name = (L.contact_name or "").strip()
            if not name or not _is_personal_name(name):
                continue
            key = (_short_zone(L.zone), _normalise(name)[:1])
            bucket[key].append(L)

        for _, group in bucket.items():
            if len(group) < 2:
                continue
            # Greedy clustering: pick a seed, merge those within threshold
            used: set[int] = set()
            for i, seed in enumerate(group):
                if seed.id in used:
                    continue
                cluster = [seed]
                used.add(seed.id)
                for j in range(i + 1, len(group)):
                    cand = group[j]
                    if cand.id in used:
                        continue
                    if _name_similarity(seed.contact_name, cand.contact_name) >= name_threshold:
                        cluster.append(cand)
                        used.add(cand.id)
                if len(cluster) >= 2:
                    identity_counter += 1
                    stats["name_groups"] += 1
                    for L in cluster:
                        assignments[L.id] = identity_counter

        # ── Stage 3 · writeback ──────────────────────────────────────────────
        if dry_run:
            log.info(
                "[owner_merger] dry-run · {ph} phone groups, {nm} name groups, "
                "{a} leads assigned, {u} unassigned",
                ph=stats["phone_groups"], nm=stats["name_groups"],
                a=len(assignments), u=len(leads) - len(assignments),
            )
            return {
                "phone_groups":         stats["phone_groups"],
                "name_groups":          stats["name_groups"],
                "total_identities":     identity_counter,
                "leads_assigned":       len(assignments),
                "leads_without_identity": len(leads) - len(assignments),
                "dry_run":              True,
            }

        # Reset all owner_identity_id then bulk-update
        db.execute(text("UPDATE leads SET owner_identity_id = NULL "
                        "WHERE archived = 0"))
        for lead_id, identity_id in assignments.items():
            db.execute(
                text("UPDATE leads SET owner_identity_id = :iid WHERE id = :lid"),
                {"iid": identity_id, "lid": lead_id},
            )
        db.commit()

        # Canonical-name pass: for each identity, pick the most complete name
        # and propagate to all members that have a weaker / missing name.
        canon_updates = 0
        from collections import defaultdict as _dd
        groups_by_id: dict[int, list[Lead]] = _dd(list)
        refreshed = db.query(Lead).filter(
            Lead.owner_identity_id.isnot(None),
            Lead.archived == False,                                  # noqa: E712
        ).all()
        for L in refreshed:
            groups_by_id[L.owner_identity_id].append(L)
        for iid, members in groups_by_id.items():
            names = [L.contact_name for L in members if L.contact_name]
            canon = _pick_canonical_name(names)
            if not canon:
                continue
            for L in members:
                if not (L.contact_name or "").strip() or len(L.contact_name) < len(canon):
                    L.contact_name = canon
                    canon_updates += 1
        db.commit()
        stats["canonical_name_updates"] = canon_updates

    log.info(
        "[owner_merger] {ph} phone groups · {nm} name groups · "
        "{i} identities · {a} leads assigned · {c} canonical-name updates",
        ph=stats["phone_groups"], nm=stats["name_groups"],
        i=identity_counter, a=len(assignments), c=canon_updates,
    )
    return {
        "phone_groups":            stats["phone_groups"],
        "name_groups":             stats["name_groups"],
        "total_identities":        identity_counter,
        "leads_assigned":          len(assignments),
        "leads_without_identity":  len(leads) - len(assignments),
        "canonical_name_updates":  canon_updates,
        "dry_run":                 False,
    }
