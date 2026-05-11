"""
Morning Brief · Sprint 2026-05-11

Generates a single TXT file that summarises the overnight run so the operator
opens ONE file in the morning to know exactly what happened and what to do.

Output: ``logs/MORNING_BRIEF.txt``

Contents (PT-PT, ASCII-clean, no emoji-only lines so it renders fine in
Terminal/TextEdit/cat):

  • Run stats (duration, sources, raw/new leads)
  • DB delta (∆ leads · ∆ HOT · ∆ Tier A+B)
  • Top 10 leads para chamar hoje (nome · zona · tipologia · preço · phone)
  • Fila re-engagement (count)
  • Conversion KPIs actuais
  • Erros e warnings detectados no run log

Lê SEMPRE o run log mais recente em ``logs/run_*.log``.

CLI:
    python main.py morning-brief
"""
from __future__ import annotations

import glob
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from storage.database import get_db
from storage.models   import Lead
from utils.logger     import get_logger
from reports.commercial_export import _classify_owner_tier, _short_zone
from reports.conversion_analytics import compute_analytics, Bucket

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "logs" / "MORNING_BRIEF.txt"


# ── Log parsing ──────────────────────────────────────────────────────────────

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(s: str) -> str:
    return _ANSI.sub("", s)


def _latest_run_log() -> Optional[Path]:
    files = sorted(
        ROOT.glob("logs/run_*.log"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return files[0] if files else None


def _parse_run_stats(log_path: Path) -> dict:
    """Pull a small number of structured facts out of the run log."""
    text = _strip(log_path.read_text(errors="ignore"))
    stats = {
        "log_file":     log_path.name,
        "log_size_kb":  log_path.stat().st_size // 1024,
        "started":      None,
        "ended":        None,
        "duration":     None,
        "sources":      [],
        "raw_persisted": 0,
        "errors":       [],
        "warnings":     0,
        "complete":     False,
    }
    # Timestamps from first & last ISO-ish lines
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.M)
    matches = ts_re.findall(text)
    if matches:
        stats["started"] = matches[0]
        stats["ended"]   = matches[-1]
        try:
            t0 = datetime.strptime(matches[0],  "%Y-%m-%d %H:%M:%S")
            t1 = datetime.strptime(matches[-1], "%Y-%m-%d %H:%M:%S")
            stats["duration"] = str(t1 - t0)
        except ValueError:
            pass
    # Sources used
    m = re.search(r"auto-selected sources from registry: (\[.+?\])", text)
    if m:
        stats["sources"] = [s.strip().strip("'") for s in m.group(1).strip("[]").split(",")]
    # Per-source persisted
    persists = re.findall(r"Persisted (\d+) new raw listings from (\w+)", text)
    stats["raw_per_source"] = {src: int(n) for n, src in persists}
    stats["raw_persisted"]  = sum(stats["raw_per_source"].values())
    # Pipeline complete?
    stats["complete"] = "Pipeline complete" in text or "Pipeline completo" in text
    # Warnings / errors (last 8 distinct ones)
    warn_lines = re.findall(r"WARNING\s*\|.*?— (.+?)(?:\[0m|\n)", text)
    stats["warnings"] = len(warn_lines)
    # Distinct error messages, last 5
    err_lines = re.findall(r"ERROR\s*\|.*?— (.+?)(?:\[0m|\n)", text)
    seen = set()
    for e in err_lines[-30:]:
        e = e.strip()[:140]
        if e and e not in seen:
            seen.add(e)
            stats["errors"].append(e)
    return stats


# ── Top leads to call ────────────────────────────────────────────────────────

def _top_leads_today(limit: int = 10) -> list[Lead]:
    with get_db() as db:
        fresh = (db.query(Lead)
                 .filter(
                     Lead.archived == False,                       # noqa: E712
                     Lead.contact_phone.isnot(None),
                     Lead.contact_phone != "",
                     Lead.phone_type == "mobile",
                     Lead.last_contacted_at.is_(None),
                     Lead.score >= 40,
                 )
                 .order_by(Lead.score.desc(), Lead.price.desc())
                 .limit(limit * 6)
                 .all())
        return [L for L in fresh
                if _classify_owner_tier(L) in ("A", "B")][:limit]


def _re_engagement_count() -> int:
    now = datetime.utcnow()
    with get_db() as db:
        return (db.query(Lead)
                .filter(
                    Lead.archived == False,                        # noqa: E712
                    Lead.re_engage_after.isnot(None),
                    Lead.re_engage_after <= now,
                )
                .count())


# ── Render ───────────────────────────────────────────────────────────────────

_HR = "=" * 72
_HR_THIN = "-" * 72


def _fmt_price(p) -> str:
    if not p: return "—"
    return f"{int(p):,} EUR".replace(",", " ")


def generate_morning_brief() -> Path:
    log_p = _latest_run_log()
    run_stats = _parse_run_stats(log_p) if log_p else {}

    top = _top_leads_today(limit=10)
    re_eng = _re_engagement_count()

    with get_db() as db:
        total      = db.query(Lead).filter(Lead.archived == False).count()
        hot        = db.query(Lead).filter(
            Lead.archived == False, Lead.score_label == "HOT").count()
        with_phone = db.query(Lead).filter(
            Lead.archived == False,
            Lead.contact_phone.isnot(None),
            Lead.contact_phone != "",
            Lead.phone_type == "mobile",
        ).count()
        tier_ab_q = db.query(Lead).filter(
            Lead.archived == False,
            Lead.contact_phone.isnot(None),
            Lead.phone_type == "mobile",
        )
        tier_ab = sum(1 for L in tier_ab_q.all()
                       if _classify_owner_tier(L) in ("A", "B"))

    stats = compute_analytics()
    overall: Bucket = stats["overall"]

    lines: list[str] = []
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines.append(_HR)
    lines.append(f"  PATA BRAVA · MORNING BRIEF · {now}")
    lines.append(_HR)
    lines.append("")
    lines.append("OVERVIEW DA BASE")
    lines.append(_HR_THIN)
    lines.append(f"  Total leads activos     : {total:>6,}".replace(",", " "))
    lines.append(f"  Com telemóvel (mobile)  : {with_phone:>6}")
    lines.append(f"  HOT (score ≥ 60)        : {hot:>6}")
    lines.append(f"  Tier A+B (donos prováv.) : {tier_ab:>6}")
    lines.append(f"  Re-engagement hoje      : {re_eng:>6}")
    lines.append("")

    if run_stats:
        lines.append("ÚLTIMA RUN DO SCRAPER")
        lines.append(_HR_THIN)
        lines.append(f"  Log               : {run_stats.get('log_file','—')}")
        lines.append(f"  Início            : {run_stats.get('started','—')}")
        lines.append(f"  Fim               : {run_stats.get('ended','—')}")
        lines.append(f"  Duração           : {run_stats.get('duration','—')}")
        lines.append(f"  Pipeline complete : {'sim' if run_stats.get('complete') else 'NÃO ⚠'}")
        lines.append(f"  Raw novos guard.  : {run_stats.get('raw_persisted',0)}")
        if run_stats.get("raw_per_source"):
            for src, n in sorted(run_stats["raw_per_source"].items(),
                                  key=lambda x: -x[1]):
                lines.append(f"    {src:18s} {n:>5}")
        lines.append(f"  Warnings          : {run_stats.get('warnings',0)}")
        if run_stats.get("errors"):
            lines.append(f"  Erros (últimos)   :")
            for e in run_stats["errors"][:5]:
                lines.append(f"    - {e}")
        lines.append("")

    lines.append("CONVERSION KPIs (cumulativo)")
    lines.append(_HR_THIN)
    lines.append(f"  Contactados       : {overall.contacted}")
    lines.append(f"  Interessados/conv : {overall.converted}")
    lines.append(f"  Não interessados  : {overall.refused}")
    lines.append(f"  Sem resposta      : {overall.no_answer}")
    if overall.contacted:
        lines.append(f"  Conversion rate   : {overall.conversion_pct}")
    lines.append("")

    lines.append("TOP 10 PARA CHAMAR HOJE (Tier A/B · mobile · novo)")
    lines.append(_HR_THIN)
    if not top:
        lines.append("  (Sem leads novos — base limpa ou todos já contactados.)")
    else:
        lines.append(
            f"  {'#':<3}{'TIER':<5}{'NOME':<22}{'ZONA':<14}{'TIPO':<10}"
            f"{'PREÇO':<15}{'TELEFONE':<18}"
        )
        for i, L in enumerate(top, 1):
            tier  = _classify_owner_tier(L) if L.contact_phone else "?"
            name  = (L.contact_name or "—")[:21]
            zone  = (_short_zone(L.zone) or "—")[:13]
            typ   = (L.typology or L.property_type or "—")[:9]
            price = _fmt_price(L.price)[:14]
            phone = (L.contact_phone or "—")
            lines.append(
                f"  {i:<3}{tier:<5}{name:<22}{zone:<14}{typ:<10}"
                f"{price:<15}{phone:<18}"
            )
    lines.append("")

    lines.append("FICHEIROS ENTREGUES (post-run)")
    lines.append(_HR_THIN)
    xlsx_files = sorted(ROOT.glob("exports/leads_comercial_*.xlsx"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if xlsx_files:
        lines.append(f"  XLSX comercial    : {xlsx_files[0].name}")
    cards_count = len(list((ROOT / "data" / "lead_cards").glob("*.pdf")))
    lines.append(f"  Lead cards PDF    : {cards_count} em data/lead_cards/")
    if (ROOT / "exports" / "conversion_analytics.xlsx").exists():
        lines.append(f"  Conversion XLSX   : exports/conversion_analytics.xlsx")
    if (ROOT / "data" / "dashboard.html").exists():
        lines.append(f"  Dashboard HTML    : data/dashboard.html (abrir no browser)")
    lines.append("")

    lines.append("PRÓXIMOS PASSOS")
    lines.append(_HR_THIN)
    lines.append("  1. Abre data/dashboard.html no browser")
    lines.append("  2. Liga aos top 10 acima (ver coluna TELEFONE)")
    lines.append("  3. Marca o resultado de cada chamada no XLSX (coluna Estado)")
    lines.append("  4. Re-importa com:  python3 main.py import-feedback <path.xlsx>")
    if re_eng:
        lines.append(f"  5. Há {re_eng} leads na fila de re-engagement — sheet '🔄 Re-engagement' no XLSX")
    lines.append("")
    lines.append(_HR)
    lines.append("  Gerado por reports/morning_brief.py · python3 main.py morning-brief")
    lines.append(_HR)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log.info("[morning_brief] wrote {p} ({n} lines)",
             p=OUT_PATH, n=len(lines))
    return OUT_PATH
