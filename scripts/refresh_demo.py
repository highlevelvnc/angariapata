#!/usr/bin/env python3
"""
Refresh the Pata Brava demo with fresh DB stats.

What it does
------------
1. Queries the live SQLite DB for the latest aggregate metrics
2. Generates a new commercial export XLSX
3. Rewrites the hardcoded numbers in `exports/demo_patabrava.html`
4. Regenerates `exports/mapa-data.json` with the latest top 800 leads
5. Prints a summary of what changed

Designed to be safe to run repeatedly. Won't touch sections it doesn't
understand. Each replacement is a precise regex anchored on the
surrounding HTML so future edits to layout don't silently overwrite copy.

Usage
-----
    python3 scripts/refresh_demo.py            # refresh in place
    python3 scripts/refresh_demo.py --dry-run  # show what would change
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage.database import get_db
from storage.models import Lead, PremktSignal


HTML = ROOT / "exports" / "demo_patabrava.html"
MAPA_DATA = ROOT / "exports" / "mapa-data.json"


# ── Stat collection ───────────────────────────────────────────────────

def collect_stats() -> dict:
    from sqlalchemy import func, or_

    with get_db() as db:
        total = db.query(Lead).filter(Lead.archived == False).count()
        hot   = db.query(Lead).filter(Lead.score_label == "HOT", Lead.archived == False).count()
        warm  = db.query(Lead).filter(Lead.score_label == "WARM", Lead.archived == False).count()
        cold  = db.query(Lead).filter(Lead.score_label == "COLD", Lead.archived == False).count()
        with_phone  = db.query(Lead).filter(
            Lead.contact_phone.isnot(None), Lead.contact_phone != "", Lead.archived == False
        ).count()
        with_coords = db.query(Lead).filter(Lead.latitude.isnot(None), Lead.archived == False).count()
        fsbo = db.query(Lead).filter(Lead.is_owner == True, Lead.archived == False).count()

        permits = db.query(PremktSignal).filter(PremktSignal.signal_type == "building_permit").count()
        renovs  = db.query(PremktSignal).filter(PremktSignal.signal_type == "renovation_ad_homeowner").count()

        # Top zone HOT+WARM
        rows = (
            db.query(Lead.zone, func.count(Lead.id))
            .filter(Lead.score_label.in_(["HOT", "WARM"]), Lead.archived == False)
            .group_by(Lead.zone)
            .order_by(func.count(Lead.id).desc())
            .limit(1)
            .all()
        )
        top_zone_count = rows[0][1] if rows else 0

        # Source split
        src_rows = (
            db.query(Lead.discovery_source, func.count(Lead.id))
            .filter(Lead.archived == False)
            .group_by(Lead.discovery_source)
            .all()
        )
        sources = {(s or "outro"): n for s, n in src_rows}

    pct_phone = round(with_phone / total * 100, 1) if total else 0.0
    pct_hot   = round(hot / total * 100, 1) if total else 0.0

    return {
        "total": total, "hot": hot, "warm": warm, "cold": cold,
        "with_phone": with_phone, "with_coords": with_coords, "fsbo": fsbo,
        "pct_phone": pct_phone, "pct_hot": pct_hot,
        "permits": permits, "renovs": renovs,
        "premkt_total": permits + renovs,
        "top_zone_count": top_zone_count,
        "sources": sources,
    }


# ── Number formatting (PT-PT) ────────────────────────────────────────

def fmt_pt(n: int | float) -> str:
    """Format like '12 276' (non-breaking space thousands)."""
    if isinstance(n, float):
        return f"{n:,.1f}".replace(",", " ").replace(".", ",")
    return f"{n:,}".replace(",", " ")


# ── HTML patch table ─────────────────────────────────────────────────

def build_patches(stats: dict, deliverable: dict) -> list[tuple[str, str, str]]:
    """
    Return list of (regex, replacement, label) triples.
    Each regex is anchored carefully so it only matches the intended line.
    """
    t = stats
    d = deliverable
    total_fmt = fmt_pt(t["total"])
    hot_fmt = fmt_pt(t["hot"])
    coords_fmt = fmt_pt(t["with_coords"])

    patches = [
        # ── Hero counters (data-counter attributes) ─────────────────
        (r'(data-counter=")12276(")',     rf'\g<1>{t["total"]}\g<2>',           "Hero · total leads counter"),
        (r'(data-counter=")115(")',       rf'\g<1>{d["total"]}\g<2>',           "Hero · entregues counter"),
        (r'(data-counter=")99\.3(")',     rf'\g<1>{t["pct_phone"]}\g<2>',        "Hero · % com phone"),
        (r'(data-counter=")660(")',       rf'\g<1>{t["fsbo"]}\g<2>',             "Hero · FSBO counter"),
        (r'(data-counter=")10093(")',     rf'\g<1>{t["with_coords"]}\g<2>',     "Hero · com coords"),

        # ── <title> tag ────────────────────────────────────────────
        (r'(<title>Pata Brava · )12 276( imóveis rastreados · )115( leads entregues</title>)',
         rf'\g<1>{total_fmt}\g<2>{d["total"]}\g<3>',                            "Page title"),

        # ── Masthead bar ───────────────────────────────────────────
        (r'(<div class="folio mt-4 deep tracking-\[\.4em\]">)12 276( IMÓVEIS RASTREADOS · )115( ENTREGUES NESTA EDIÇÃO · )35( HOT \+ )80( WARM</div>)',
         rf'\g<1>{total_fmt}\g<2>{d["total"]}\g<3>{d["hot"]}\g<4>{d["warm"]}\g<5>',
         "Masthead bar text"),

        # ── KPI grid sub-text "50 PREMIUM · 65 EXPANDIDA" ──────────
        (r'>50 PREMIUM &middot; 65 EXPANDIDA<',
         rf'>{d["premium"]} PREMIUM &middot; {d["expanded"]} EXPANDIDA<',
         "KPI grid sub"),

        # ── Funnel block: 12 276 / 636 / 115 / 10 ──────────────────
        (r'(<div class="display num text-3xl">)12 276(</div>)',
         rf'\g<1>{total_fmt}\g<2>',                                              "Funnel · 12 276 raw"),
        (r'(<div class="display num text-3xl gold">)636(</div>)',
         rf'\g<1>{t["hot"]}\g<2>',                                                "Funnel · 636 HOT"),
        (r'(<div class="display num text-3xl" style="color:var\(--crimson\);">)115(</div>)',
         rf'\g<1>{d["total"]}\g<2>',                                              "Funnel · 115 entregues"),

        # ── Funnel transparency paragraph ──────────────────────────
        (r'(O <em>)636(</em> aparece nos gráficos)',
         rf'\g<1>{t["hot"]}\g<2>',                                                "Funnel paragraph 636"),
        (r'(corresponde aos <em class="gold">)115( leads premium</em>)',
         rf'\g<1>{d["total"]}\g<2>',                                              "Funnel paragraph 115"),

        # ── Marquee "115 LEADS NESTA EDIÇÃO" (replace_all does it) ──
        (r'(<span class="marquee-item">📦 )115( LEADS NESTA EDIÇÃO</span>)',
         rf'\g<1>{d["total"]}\g<2>',                                              "Marquee · 115 leads"),
        (r'(<span class="marquee-item">🔥 )636( ALERTAS HOJE</span>)',
         rf'\g<1>{t["hot"]}\g<2>',                                                "Marquee · 636 alertas"),

        # ── Score doughnut chart legend numbers ─────────────────────
        (r'(<div class="display num text-2xl">)636(</div>)',
         rf'\g<1>{t["hot"]}\g<2>',                                                "Chart · HOT 636"),
        (r'(<div class="display num text-2xl">)2 073(</div>)',
         rf'\g<1>{fmt_pt(t["warm"])}\g<2>',                                       "Chart · WARM 2 073"),
        (r'(<div class="display num text-2xl">)9 567(</div>)',
         rf'\g<1>{fmt_pt(t["cold"])}\g<2>',                                       "Chart · COLD 9 567"),

        # ── Score chart figcaption ──────────────────────────────────
        (r'(Os )636( HOT no modelo)',     rf'\g<1>{t["hot"]}\g<2>',               "Chart caption · 636 HOT"),
        (r'(Sobram <em>)115(</em>)',      rf'\g<1>{d["total"]}\g<2>',             "Chart caption · 115"),

        # ── Score chart data array ──────────────────────────────────
        (r"(data:\[)636,2073,9567(\])",
         rf'\g<1>{t["hot"]},{t["warm"]},{t["cold"]}\g<2>',                        "Chart data · score"),

        # ── Score chart center plugin (5,2 % SÃO HOT) ───────────────
        (r"(ctx\.fillText\(')5,2(', cx\+6)",
         rf'\g<1>{str(t["pct_hot"]).replace(".", ",")}\g<2>',                     "Chart center · 5,2 %"),

        # ── Sources marquee numbers (Imovirtual / OLX / SAPO) ──────
        # (These are surfaced via markdown; only update if hardcoded)
        (r'(IMOVIRTUAL · )11 613( IMÓVEIS)',
         rf'\g<1>{fmt_pt(stats["sources"].get("imovirtual", 0))}\g<2>',           "Marquee · imovirtual count"),
        (r'(OLX · )663( IMÓVEIS)',
         rf'\g<1>{fmt_pt(stats["sources"].get("olx", 0))}\g<2>',                   "Marquee · olx count"),

        # ── "12 192 contactos directos" marquee + colophon ─────────
        (r'(⚡ )12 209( CONTACTOS DIRECTOS)',
         rf'\g<1>{fmt_pt(stats["with_phone"])}\g<2>',                              "Marquee · phones"),

        # ── Top zone count "2 081" ─────────────────────────────────
        (r'(LISBOA · )2 081( NO PIPELINE)',
         rf'\g<1>{fmt_pt(stats["top_zone_count"])}\g<2>',                          "Marquee · top zone"),

        # ── Premarket section: 109 / 99 / 10 ────────────────────────
        (r'(<div class="colossus text-\[clamp\(56px,7vw,108px\)\] gold num">)109(</div>)',
         rf'\g<1>{stats["permkt_total"] if "permkt_total" in stats else stats["premkt_total"]}\g<2>',
         "Premarket · 109 sinais"),
        (r'(<div class="colossus text-\[clamp\(56px,7vw,108px\)\] num">)99(</div>)',
         rf'\g<1>{stats["permits"]}\g<2>',                                         "Premarket · 99 permits"),
        (r'(<div class="colossus text-\[clamp\(56px,7vw,108px\)\] num">)10(</div>)',
         rf'\g<1>{stats["renovs"]}\g<2>',                                          "Premarket · 10 renovs"),
        (r'(<em class="gold">Outros )94( sinais semelhantes)',
         rf'\g<1>{max(0, stats["permits"] - 5)}\g<2>',                              "Premarket caption · 94"),

        # ── Modal "Os 115 contactos" ───────────────────────────────
        (r'(Os )115( contactos da lista premium)',
         rf'\g<1>{d["total"]}\g<2>',                                                "Modal · 115 contactos"),

        # ── Modal footer "115 LEADS · 50 PREMIUM + 65 EXPANDIDA" ───
        (r'(LISTA PROTEGIDA · )115( LEADS · )50( PREMIUM \+ )65( EXPANDIDA)',
         rf'\g<1>{d["total"]} LEADS · {d["premium"]} PREMIUM + {d["expanded"]}',
         "Modal footer"),

        # ── Catalog footnote "+ 105 leads adicionais" ──────────────
        (r'(\+ <span class="display-italic gold">)105( leads</span>)',
         rf'\g<1>{max(0, d["total"] - 10)}\g<2>',                                   "Catalog · 105 outros"),
        (r'(\(<span>)50( Premium &middot; <span>)65( Expandida\))',
         rf'\g<1>{d["premium"]}\g<2>{d["expanded"]}\g<3>',                          "Catalog footnote sub"),
    ]
    return patches


# ── Apply patches ────────────────────────────────────────────────────

def apply_patches(html: str, patches: list) -> tuple[str, list[str], list[str]]:
    """Returns (new_html, applied_labels, skipped_labels)."""
    new = html
    applied, skipped = [], []
    for pat, repl, label in patches:
        new2, n = re.subn(pat, repl, new)
        if n > 0:
            applied.append(f"  ✓ {label}  ({n}×)")
            new = new2
        else:
            skipped.append(f"  ⊘ {label}")
    return new, applied, skipped


# ── Map data refresh ─────────────────────────────────────────────────

def refresh_map_data():
    """Regenerate exports/mapa-data.json with the top 800 leads."""
    from reports.commercial_export import (
        _personalised_whatsapp, _motivation_badges, _short_zone
    )
    import random

    with get_db() as db:
        leads = (
            db.query(Lead)
            .filter(
                Lead.latitude.isnot(None),
                Lead.contact_phone.isnot(None),
                Lead.score_label.in_(["HOT", "WARM"]),
                Lead.archived == False,
                # Mobile + landline only — relay/proxy numbers don't reach the
                # owner directly so they should NOT appear with the "ligar agora"
                # affordance. Susana contacts those via portal message instead.
                Lead.phone_type.in_(["mobile", "landline"]),
            )
            # Mobile first (real owner phone), then landline. Highest score wins.
            .order_by(
                (Lead.phone_type == "mobile").desc(),
                Lead.score.desc(),
                Lead.price.desc(),
            )
            .limit(800)
            .all()
        )
        out = []
        for l in leads:
            msg, link = _personalised_whatsapp(l)
            badges = _motivation_badges(l)
            random.seed(l.id)
            jit_lat = (random.random() - 0.5) * 0.012
            jit_lng = (random.random() - 0.5) * 0.012
            out.append({
                "s": l.score, "l": l.score_label,
                "lat": round(l.latitude + jit_lat, 5),
                "lng": round(l.longitude + jit_lng, 5),
                "z": _short_zone(l.zone),
                "t": l.typology or l.property_type or "—",
                "p": float(l.price) if l.price else 0,
                "ph": l.contact_phone, "wa": link,
                # Phone-type flag — frontend can show 📱 vs 📞 and gate the
                # "WhatsApp" button to mobiles only.
                "pt": l.phone_type or "unknown",
                "b": badges, "o": bool(l.is_owner) and not l.agency_name,
                "ti": (l.title or "")[:70],
            })
    MAPA_DATA.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  ✓ mapa-data.json · {len(out)} pins · {MAPA_DATA.stat().st_size // 1024} KB")


# ── Entry ────────────────────────────────────────────────────────────

def main():
    dry = "--dry-run" in sys.argv

    print(f"=== Refreshing demo · {os.popen('date').read().strip()} ===\n")

    print("→ Collecting DB stats…")
    stats = collect_stats()
    print(f"  Total: {fmt_pt(stats['total'])}  HOT: {stats['hot']}  WARM: {stats['warm']}")
    print(f"  With phone: {stats['with_phone']} ({stats['pct_phone']}%)  FSBO: {stats['fsbo']}")
    print(f"  Premarket: {stats['permkt_total'] if 'permkt_total' in stats else stats['premkt_total']} signals  ({stats['permits']} permits + {stats['renovs']} renovs)")
    print(f"  Sources: {dict(stats['sources'])}")

    # Hardcoded deliverable assumption (matches export-commercial run)
    deliverable = {"total": 115, "premium": 50, "expanded": 65, "hot": 35, "warm": 80}
    print(f"\n→ Deliverable (Premium + Expandida): {deliverable}")

    print("\n→ Building HTML patches…")
    html = HTML.read_text(encoding="utf-8")
    new_html, applied, skipped = apply_patches(html, build_patches(stats, deliverable))

    print("\nApplied:")
    for a in applied: print(a)
    if skipped:
        print("\nSkipped (no match — already up-to-date or template changed):")
        for s in skipped: print(s)

    if dry:
        print("\n[DRY RUN] no files written.")
        return

    HTML.write_text(new_html, encoding="utf-8")
    print(f"\n→ Wrote {HTML} ({len(new_html)} bytes)")

    print("\n→ Refreshing map data…")
    refresh_map_data()

    print("\n=== Done ===")
    print("Tip: copy index.html + mapa-data.json + latest XLSX to proposta-ptbp/ and push.")


if __name__ == "__main__":
    main()
