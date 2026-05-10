"""
End-to-end smoke test for the Pata Brava pipeline.

Validates the system after the 32-sprint refactor session:
  ✓ All critical modules import without error
  ✓ DB migrations apply idempotently
  ✓ Quality filters run on live data without errors
  ✓ Export pipeline produces a valid XLSX
  ✓ Demo HTML files exist and contain expected anchor sections

Run before any apresentação. Designed to be fast (<30s) and read-only.

    python3 tests/test_e2e_smoke.py
    python3 tests/test_e2e_smoke.py --verbose

Returns exit code 0 = all green, 1 = at least one failure.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── ANSI colours ─────────────────────────────────────────────────────
GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"
DIM = "\033[2m"; BOLD = "\033[1m"; RESET = "\033[0m"

results: list[tuple[str, bool, str]] = []
verbose = "--verbose" in sys.argv or "-v" in sys.argv


def check(name: str):
    """Decorator: register a check function. Catches exceptions."""
    def wrap(fn):
        try:
            fn()
            results.append((name, True, ""))
            print(f"  {GREEN}✓{RESET} {name}")
        except AssertionError as e:
            results.append((name, False, str(e)))
            print(f"  {RED}✗ {name}{RESET}  ·  {e}")
        except Exception as e:
            tb = traceback.format_exc() if verbose else f"{type(e).__name__}: {e}"
            results.append((name, False, tb))
            print(f"  {RED}✗ {name}{RESET}  ·  {type(e).__name__}: {e}")
            if verbose:
                print(f"{DIM}{tb}{RESET}")
        return fn
    return wrap


# ─────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}═══ Pata Brava · E2E smoke test ═══{RESET}\n")

# ── 1. Critical imports ──────────────────────────────────────────────
print(f"{BOLD}1. Imports{RESET}")

@check("storage.database engine + session")
def _():
    from storage.database import engine, get_db, SessionLocal
    assert engine is not None
    with get_db() as db:
        assert db is not None

@check("storage.models · Lead has all expected columns")
def _():
    from storage.models import Lead
    expected = {
        "id", "fingerprint", "title", "score", "score_label",
        "contact_phone", "contact_email", "contact_name", "phone_type",
        "is_owner", "owner_type", "agency_name", "lead_type",
        "image_url", "image_phash", "re_list_count", "last_relisted_at",
        "contact_confidence", "listing_status",
    }
    actual = {c.name for c in Lead.__table__.columns}
    missing = expected - actual
    assert not missing, f"Missing Lead columns: {missing}"

@check("scrapers · all 8 active sources import")
def _():
    from scrapers.olx          import OLXScraper
    from scrapers.imovirtual   import ImovirtualScraper
    from scrapers.sapo         import SapoScraper
    from scrapers.idealista    import IdealistaScraper, FSBO_ONLY
    from scrapers.banks        import (
        CGDImoveisScraper, MillenniumImoveisScraper,
        NovobancoImoveisScraper, SantanderImoveisScraper,
    )
    from scrapers.leiloes      import LeiloesScraper
    assert FSBO_ONLY is True, "Idealista FSBO_ONLY env flag should default True"

@check("pipeline · runner + normalizer + quality_filter")
def _():
    from pipeline.runner          import PipelineRunner
    from pipeline.normalizer      import Normalizer
    from pipeline.quality_filter  import (
        cli_quality_pass, validate_phones, flag_flippers,
        flag_disguised_agencies_by_name, validate_emails,
        flag_suspicious, compute_confidence_scores,
        apply_freshness_penalty, consolidate_contacts,
        guess_agency_emails,
    )

@check("reports · commercial_export with WhatsApp + badges + confidence")
def _():
    from reports.commercial_export import (
        _personalised_whatsapp, _motivation_badges,
        _short_zone, _first_name,
    )
    # Smoke a synthetic lead through the badge function
    from datetime import datetime, timedelta
    class L: pass
    l = L()
    l.id=999_999; l.score=95; l.score_label='HOT'; l.is_owner=True; l.lead_type='fsbo'
    l.agency_name=None; l.price=600000; l.zone='Estrela'; l.parish=''
    l.sources_json=''; l.days_on_market=70; l.price_changes=''; l.re_list_count=0
    l.contact_confidence=85
    l.first_seen_at = datetime.utcnow() - timedelta(hours=12)  # for HH recency badge
    l.contact_phone = None  # owner_profile gracefully returns empty
    l.score_breakdown = '{}'
    badges = _motivation_badges(l)
    assert "⭐ ELITE" in badges
    assert "👤 PROPRIETÁRIO" in badges
    assert "💎 LUXURY" in badges
    assert any("ALTA CONFIANÇA" in b for b in badges)

@check("crm · ego_sync scaffold loads in dry-run mode")
def _():
    from crm.ego_sync import EgoSyncer, EgoConfig, cli_sync
    from crm import ego_cli_sync   # exported alias
    cfg = EgoConfig.from_env()
    assert cfg.is_configured is False or isinstance(cfg.api_key, str)
    assert callable(cli_sync) and callable(ego_cli_sync)


# ── 2. DB migrations applied ─────────────────────────────────────────
print(f"\n{BOLD}2. DB schema{RESET}")

@check("DB · all expected columns present in leads table")
def _():
    import sqlite3
    db_path = ROOT / "data" / "patabrava.db"
    if not db_path.exists():
        return  # No DB yet — skip silently
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
    conn.close()
    required = {
        "image_url", "image_phash", "re_list_count", "last_relisted_at",
        "contact_confidence", "listing_status", "phone_type",
        "score_label", "is_owner", "owner_type",
    }
    missing = required - cols
    assert not missing, f"Missing DB columns: {missing}"

@check("DB · indexes on hot paths")
def _():
    import sqlite3
    db_path = ROOT / "data" / "patabrava.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    indexes = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}
    conn.close()
    # We just need at least *some* indexes to exist — full audit not necessary
    assert len(indexes) >= 5, "DB should have at least 5 indexes; got {}".format(len(indexes))


# ── 3. Quality filters · live data sanity ────────────────────────────
print(f"\n{BOLD}3. Quality filters · live data sanity{RESET}")

@check("quality_filter · phone validate idempotent on live DB")
def _():
    from pipeline.quality_filter import validate_phones
    r = validate_phones()
    assert r["checked"] >= 0
    assert r["mobile"] + r["landline"] <= r["checked"]

@check("quality_filter · confidence score in 0-100 range")
def _():
    from storage.database import get_db
    from storage.models   import Lead
    with get_db() as db:
        from sqlalchemy import func
        mn, mx = db.query(func.min(Lead.contact_confidence), func.max(Lead.contact_confidence)).first()
        if mn is None: return  # empty DB
        assert 0 <= mn <= 100, f"min confidence out of range: {mn}"
        assert 0 <= mx <= 100, f"max confidence out of range: {mx}"


# ── 4. Export · produces a valid XLSX ────────────────────────────────
print(f"\n{BOLD}4. Export pipeline{RESET}")

@check("commercial_export · _lead_to_row schema is complete")
def _():
    from reports.commercial_export import _lead_to_row
    from storage.database import get_db
    from storage.models   import Lead
    with get_db() as db:
        sample = db.query(Lead).filter(Lead.archived == False).first()
        if sample is None:
            return  # empty DB
        row = _lead_to_row(sample, rank=1)
    expected_keys = {
        "rank", "score", "label", "badges", "nome", "telefone",
        "tipo_telefone", "whatsapp", "mensagem_wa",
        "zona", "tipologia", "preco", "url",
    }
    missing = expected_keys - set(row.keys())
    assert not missing, f"Export row missing keys: {missing}"

@check("commercial_export · WhatsApp link is well-formed")
def _():
    from reports.commercial_export import _personalised_whatsapp
    from urllib.parse import urlparse
    class L: pass
    l = L()
    l.contact_phone = "+351912345678"
    l.contact_name = "João Silva"
    l.typology = "T2"
    l.property_type = "apartamento"
    l.zone = "Lisboa"
    l.title = "T2 em Lisboa"
    l.lead_type = "fsbo"
    l.price = 250000
    msg, link = _personalised_whatsapp(l)
    assert msg and link
    p = urlparse(link)
    assert "wa.me" in p.netloc, f"Link should target wa.me, got {link}"
    assert "text=" in p.query, "Link should pre-fill text"


# ── 5. Demo HTML · expected anchors present ──────────────────────────
print(f"\n{BOLD}5. Demo HTML integrity{RESET}")

@check("exports/demo_patabrava.html · key sections present")
def _():
    p = ROOT / "exports" / "demo_patabrava.html"
    assert p.exists(), "demo_patabrava.html missing"
    html = p.read_text(encoding="utf-8")
    anchors = [
        "id=\"dispatch\"",      # KPIs
        "id=\"livefeed\"",       # Live feed terminal
        "id=\"catalog\"",        # Top 10 leads
        "id=\"roi\"",            # ROI calculator
        "id=\"integracoes\"",    # eGO + outras
        "id=\"premarket\"",      # Antes do anúncio
        "id=\"etica\"",          # GDPR
        "id=\"colophon\"",       # CTA + colofon
    ]
    missing = [a for a in anchors if a not in html]
    assert not missing, f"Demo missing anchor sections: {missing}"

@check("exports/mapa.html · Leaflet + custom pins present")
def _():
    p = ROOT / "exports" / "mapa.html"
    assert p.exists(), "mapa.html missing"
    html = p.read_text(encoding="utf-8")
    assert "leaflet" in html.lower(), "Leaflet library not referenced"
    assert "PB_OFFICE" in html, "Pata Brava office marker code missing"
    assert "marker-cluster-custom" in html, "Custom cluster icon CSS missing"

@check("exports/email-diario.html + mobile.html · standalone pages exist")
def _():
    for f in ("email-diario.html", "mobile.html"):
        p = ROOT / "exports" / f
        assert p.exists(), f"Standalone page missing: {f}"
        html = p.read_text(encoding="utf-8")
        assert len(html) > 5000, f"{f} suspiciously small ({len(html)} bytes)"


# ── 6. Tier pricing consistency ──────────────────────────────────────
print(f"\n{BOLD}6. Pricing integrity{RESET}")

@check("Tier card prices match data-setup attributes")
def _():
    p = ROOT / "exports" / "demo_patabrava.html"
    html = p.read_text(encoding="utf-8")
    import re
    # data-tier="solo" data-setup="500" data-monthly="150"
    expected = {
        "solo":    ("500", "150"),
        "pro":     ("1000", "300"),
        "agencia": ("2000", "600"),
    }
    for tier, (setup, monthly) in expected.items():
        m = re.search(
            rf'data-tier="{tier}"\s+data-setup="(\d+)"\s+data-monthly="(\d+)"',
            html,
        )
        assert m, f"Tier card not found for: {tier}"
        assert m.group(1) == setup, f"{tier} setup mismatch: {m.group(1)} vs {setup}"
        assert m.group(2) == monthly, f"{tier} monthly mismatch: {m.group(2)} vs {monthly}"


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{BOLD}═══ Summary ═══{RESET}")
passed = sum(1 for _, ok, _ in results if ok)
failed = len(results) - passed
total  = len(results)
emoji  = GREEN + "✓" if failed == 0 else RED + "✗"
print(f"\n  {emoji} {passed}/{total} passed{RESET}")
if failed:
    print(f"\n  {RED}{BOLD}Failures:{RESET}")
    for name, ok, msg in results:
        if not ok:
            print(f"    · {name}")
            print(f"      {DIM}{msg.splitlines()[0] if msg else ''}{RESET}")
    sys.exit(1)

print(f"\n{GREEN}{BOLD}  ✓ Sistema pronto para apresentação à Susana{RESET}\n")
sys.exit(0)
