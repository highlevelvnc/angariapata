"""
Morning Dashboard · Sprint 2026-05-11

Single-page HTML the operator (Susana) opens every morning to see:

  - KPIs do dia (total leads, HOT, Tier A+B, contactados, convertidos)
  - Top 15 leads para chamar hoje (Tier A+B, score-ordenado, com opening)
  - Fila de Re-engagement (leads cujo prazo de 30d expirou)
  - Mini funnel (novo → contactado → interessado → convertido)
  - Conversion analytics resumo (rates por zona, source, tier)

Self-contained, dark luxury aesthetic, no JS framework (vanilla + Chart.js
via CDN for the funnel chart). Written to data/dashboard.html — Susana
abre o ficheiro local no browser. Zero servidor, zero deps.

Refreshed automatically pelo post_run.sh quando integrado, ou on-demand:
    python main.py morning-prep
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from storage.database import get_db
from storage.models   import Lead
from utils.logger     import get_logger
from reports.commercial_export import (
    _classify_owner_tier, _short_zone, _PT_STAGE_LABELS,
)
from reports.conversion_analytics import compute_analytics, Bucket
from pipeline.precall_briefing import build_briefing

log = get_logger(__name__)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "data" / "dashboard.html"


# ── HTML template ────────────────────────────────────────────────────────────

_TEMPLATE = """<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pata Brava · Morning Dashboard · {{date_str}}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --ink: #0a0908;
    --gold: #ddc269;
    --gold-2: #c8a85a;
    --bone: #f7f1de;
    --bone-dim: #c5bea3;
    --rule: #3a342a;
    --crimson: #c62828;
    --hot: #c62828;
    --warm: #d4a017;
    --cool: #1f77b4;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--ink);
    color: var(--bone);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.5;
    padding: 24px 32px;
    min-height: 100vh;
  }
  header {
    border-bottom: 1px solid var(--rule);
    padding-bottom: 16px;
    margin-bottom: 28px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
  }
  h1 {
    font-family: Georgia, "Times New Roman", serif;
    font-weight: 300;
    font-size: 22px;
    letter-spacing: -0.01em;
  }
  h1 .accent { color: var(--gold); font-style: italic; }
  .date-stamp {
    color: var(--bone-dim);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  h2 {
    font-family: Georgia, serif;
    font-weight: 300;
    font-size: 16px;
    color: var(--gold);
    margin: 28px 0 14px;
    letter-spacing: -0.005em;
  }
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
  }
  .kpi {
    background: var(--ink);
    padding: 18px 16px;
  }
  .kpi-label {
    font-size: 9.5px;
    color: var(--bone-dim);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .kpi-value {
    font-family: Georgia, serif;
    font-weight: 300;
    font-size: 30px;
    color: var(--bone);
    line-height: 1;
  }
  .kpi-value.gold { color: var(--gold); }
  .kpi-value.hot  { color: var(--hot); }
  .kpi-value.cool { color: var(--cool); }
  .kpi-note {
    margin-top: 6px;
    color: var(--bone-dim);
    font-size: 11px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    background: rgba(221, 194, 105, 0.02);
    font-size: 13px;
  }
  th {
    text-align: left;
    color: var(--gold);
    font-weight: 600;
    font-size: 10.5px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--rule);
    padding: 10px 12px;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid rgba(58, 52, 42, 0.5);
    vertical-align: top;
  }
  tr:hover td { background: rgba(221, 194, 105, 0.04); }
  .tier { font-weight: 700; }
  .tier-A { color: var(--gold); }
  .tier-B { color: var(--gold-2); }
  .tier-C, .tier-D, .tier-E, .tier-? { color: var(--bone-dim); }
  .price { color: var(--gold); font-variant-numeric: tabular-nums; }
  .opening {
    color: var(--bone-dim);
    font-style: italic;
    max-width: 540px;
  }
  a.btn-wa {
    display: inline-block;
    background: #25D366;
    color: #fff !important;
    padding: 4px 10px;
    text-decoration: none;
    font-size: 11px;
    border-radius: 2px;
    margin-right: 4px;
  }
  a.btn-url {
    color: var(--bone-dim);
    font-size: 11px;
    text-decoration: none;
    border-bottom: 1px dotted var(--rule);
  }
  a.btn-url:hover { color: var(--gold); border-bottom-color: var(--gold); }
  .empty {
    color: var(--bone-dim);
    font-style: italic;
    padding: 14px;
    background: rgba(58, 52, 42, 0.2);
    border-left: 3px solid var(--bone-dim);
  }
  .chart-wrap {
    background: rgba(58, 52, 42, 0.2);
    padding: 20px;
    height: 280px;
  }
  .breakdown-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
  }
  .breakdown-card {
    background: rgba(58, 52, 42, 0.2);
    padding: 14px 16px;
    border-left: 2px solid var(--gold);
  }
  .breakdown-card h3 {
    font-family: Georgia, serif;
    font-weight: 300;
    font-size: 13px;
    color: var(--gold);
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .breakdown-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px dotted rgba(58, 52, 42, 0.6);
    font-size: 12.5px;
  }
  .breakdown-row:last-child { border-bottom: none; }
  .breakdown-row .label { color: var(--bone); }
  .breakdown-row .value { color: var(--gold); font-variant-numeric: tabular-nums; }
  footer {
    margin-top: 40px;
    padding-top: 16px;
    border-top: 1px solid var(--rule);
    color: var(--bone-dim);
    font-size: 11px;
    text-align: center;
    letter-spacing: 0.06em;
  }
</style>
</head>
<body>

<header>
  <h1>Pata Brava · <span class="accent">Morning Dashboard</span></h1>
  <div class="date-stamp">{{date_str}}</div>
</header>

<!-- KPIs do dia -->
<section>
  <div class="kpi-grid">
    <div class="kpi">
      <div class="kpi-label">Total na base</div>
      <div class="kpi-value">{{total_leads}}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Tier A+B</div>
      <div class="kpi-value gold">{{tier_ab}}</div>
      <div class="kpi-note">Donos com sinal forte</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">HOT score</div>
      <div class="kpi-value hot">{{hot_count}}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Para chamar HOJE</div>
      <div class="kpi-value gold">{{today_callable}}</div>
      <div class="kpi-note">Novos · não contactados</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Re-engagement</div>
      <div class="kpi-value cool">{{re_engagement_count}}</div>
      <div class="kpi-note">Prazo expirou</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Conv rate</div>
      <div class="kpi-value gold">{{conversion_rate}}</div>
      <div class="kpi-note">{{converted}} de {{contacted}} contactados</div>
    </div>
  </div>
</section>

<!-- Top 15 para chamar HOJE -->
<section>
  <h2>📞 Top 15 para chamar hoje</h2>
  {{top_calls_table}}
</section>

<!-- Re-engagement queue -->
<section>
  <h2>🔄 Fila de re-engagement</h2>
  {{re_engagement_table}}
</section>

<!-- Funnel chart -->
<section>
  <h2>📊 Funil de contacto</h2>
  <div class="chart-wrap"><canvas id="funnelChart"></canvas></div>
</section>

<!-- Breakdown cards -->
<section>
  <h2>📈 Breakdown de conversão</h2>
  <div class="breakdown-grid">
    {{breakdown_cards}}
  </div>
</section>

<footer>
  Gerado pelo motor Pata Brava · {{generated_at}} ·
  <a href="dashboard.html" style="color: var(--gold-2);">recarregar</a>
</footer>

<script>
const funnelData = {{funnel_json}};
const ctx = document.getElementById('funnelChart').getContext('2d');
new Chart(ctx, {
  type: 'bar',
  data: {
    labels: funnelData.labels,
    datasets: [{
      data: funnelData.values,
      backgroundColor: [
        '#3a342a', '#c8a85a', '#ddc269', '#1f77b4',
        '#d4a017', '#c62828'
      ],
      borderColor: '#ddc269',
      borderWidth: 0,
    }]
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        ticks: { color: '#c5bea3' },
        grid:  { color: 'rgba(58,52,42,0.6)' },
      },
      y: {
        ticks: { color: '#f7f1de', font: { weight: '600' } },
        grid:  { display: false },
      }
    }
  }
});
</script>

</body>
</html>
"""


# ── Builders ─────────────────────────────────────────────────────────────────

def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _build_today_calls_table(leads: list[Lead]) -> str:
    if not leads:
        return ('<div class="empty">Sem leads novos prontos. Volta amanhã '
                'ou corre uma nova run do scraper.</div>')
    rows = []
    rows.append(
        "<table><thead><tr>"
        "<th>#</th><th>Tier</th><th>Nome · Zona</th><th>Tipologia</th>"
        "<th>Preço</th><th>Opening</th><th>Acções</th>"
        "</tr></thead><tbody>"
    )
    for i, L in enumerate(leads, 1):
        tier = _classify_owner_tier(L) if L.contact_phone else "?"
        zone = _short_zone(L.zone) or "—"
        typ  = (L.typology or L.property_type or "—")
        price = f"€{int(L.price):,}".replace(",", " ") if L.price else "—"
        try:
            br = build_briefing(L)
            opening = br.get("opening") or ""
        except Exception:
            opening = ""
        # WhatsApp link
        ph = (L.contact_phone or "").lstrip("+").replace(" ", "")
        from urllib.parse import quote
        wa = f"https://wa.me/{ph}?text={quote(opening or '')}" if ph and opening else "#"
        # Source URL
        url = ""
        try:
            src = json.loads(L.sources_json or "[]")
            if src:
                url = src[0].get("url", "")
        except Exception:
            pass

        rows.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td class='tier tier-{tier}'>{tier}</td>"
            f"<td><strong>{_esc(L.contact_name or '—')}</strong><br>"
            f"<span style='color:var(--bone-dim);font-size:11px'>{_esc(zone)}</span></td>"
            f"<td>{_esc(typ)}</td>"
            f"<td class='price'>{price}</td>"
            f"<td class='opening'>{_esc((opening or '')[:140])}</td>"
            f"<td>"
            + (f"<a href='{wa}' class='btn-wa' target='_blank'>WhatsApp</a>" if wa != '#' else '')
            + (f"<a href='{_esc(url)}' class='btn-url' target='_blank'>anúncio</a>" if url else '')
            + "</td></tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _build_re_engagement_table(leads: list[Lead]) -> str:
    if not leads:
        return ('<div class="empty">Sem leads para re-engagement hoje. '
                'Aparecem 30 dias depois de "sem resposta" ou "contactado".</div>')
    rows = ["<table><thead><tr>"
            "<th>Nome</th><th>Zona</th><th>Última chamada</th>"
            "<th>Estado anterior</th><th>Notas anteriores</th>"
            "</tr></thead><tbody>"]
    for L in leads:
        last = (L.last_contacted_at.strftime("%d/%m/%Y")
                if L.last_contacted_at else "—")
        stage = _PT_STAGE_LABELS.get(L.crm_stage, L.crm_stage or "—")
        notes = (L.contact_outcome or "—")[:120]
        rows.append(
            f"<tr><td>{_esc(L.contact_name or '—')}</td>"
            f"<td>{_esc(_short_zone(L.zone) or '—')}</td>"
            f"<td>{last}</td>"
            f"<td>{_esc(stage)}</td>"
            f"<td class='opening'>{_esc(notes)}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _build_breakdown_cards(stats: dict) -> str:
    cards = []
    for title, key in [
        ("Por Zona",       "by_zone"),
        ("Por Source",     "by_source"),
        ("Por Tier",       "by_tier"),
        ("Por Score Band", "by_score_band"),
    ]:
        buckets = stats.get(key, {})
        rows = sorted(buckets.values(),
                      key=lambda b: b.contacted, reverse=True)
        rows = [b for b in rows if b.contacted > 0][:6]
        if not rows:
            inner = "<div style='color:var(--bone-dim);font-size:12px;font-style:italic'>Sem dados ainda</div>"
        else:
            inner_rows = []
            for b in rows:
                inner_rows.append(
                    f"<div class='breakdown-row'>"
                    f"<span class='label'>{_esc(b.label)}</span>"
                    f"<span class='value'>{b.converted}/{b.contacted} · {b.conversion_pct}</span>"
                    f"</div>"
                )
            inner = "\n".join(inner_rows)
        cards.append(
            f"<div class='breakdown-card'><h3>{_esc(title)}</h3>{inner}</div>"
        )
    return "\n".join(cards)


def generate_dashboard(output_path: Path = OUTPUT_PATH) -> Path:
    """Build dashboard.html. Returns the output path."""
    now = datetime.utcnow()

    # 1. Top calls today — Tier A+B, mobile, not contacted, score-ordered
    with get_db() as db:
        fresh = (db.query(Lead)
                 .filter(
                     Lead.archived == False,                    # noqa: E712
                     Lead.contact_phone.isnot(None),
                     Lead.contact_phone != "",
                     Lead.phone_type == "mobile",
                     Lead.last_contacted_at.is_(None),
                     Lead.score >= 40,
                 )
                 .order_by(Lead.score.desc(), Lead.price.desc())
                 .limit(80)
                 .all())
        top_calls = [L for L in fresh
                     if _classify_owner_tier(L) in ("A", "B")][:15]

        re_engage = (db.query(Lead)
                     .filter(
                         Lead.archived == False,                 # noqa: E712
                         Lead.re_engage_after.isnot(None),
                         Lead.re_engage_after <= now,
                     )
                     .order_by(Lead.score.desc())
                     .limit(15)
                     .all())

        total_leads   = db.query(Lead).filter(Lead.archived == False).count()
        hot_count     = db.query(Lead).filter(
            Lead.archived == False, Lead.score_label == "HOT").count()

    # 2. Conversion analytics
    stats = compute_analytics()
    overall: Bucket = stats["overall"]

    # 3. Compute Tier A+B + callable counts
    tier_ab_total = 0
    callable_today = 0
    with get_db() as db:
        for L in db.query(Lead).filter(
            Lead.archived == False, Lead.contact_phone.isnot(None)
        ).all():
            t = _classify_owner_tier(L)
            if t in ("A", "B"):
                tier_ab_total += 1
                if not L.last_contacted_at:
                    callable_today += 1

    # 4. Funnel data
    sc = stats["stage_counts"]
    funnel_labels = ["Novos", "Contactados", "Sem resposta",
                     "Interessados", "Convertidos", "Não interessado"]
    funnel_values = [
        sc.get("novo", 0),
        sc.get("contactado", 0),
        sc.get("sem_resposta", 0),
        sc.get("interessado", 0),
        sc.get("convertido", 0),
        sc.get("nao_interessado", 0),
    ]

    # 5. Render
    h = _TEMPLATE
    placeholders = {
        "{{date_str}}":             now.strftime("%d %b %Y · %H:%M UTC"),
        "{{total_leads}}":          f"{total_leads:,}".replace(",", " "),
        "{{tier_ab}}":              str(tier_ab_total),
        "{{hot_count}}":            str(hot_count),
        "{{today_callable}}":       str(callable_today),
        "{{re_engagement_count}}":  str(len(re_engage)),
        "{{conversion_rate}}":      overall.conversion_pct,
        "{{converted}}":            str(overall.converted),
        "{{contacted}}":            str(overall.contacted),
        "{{top_calls_table}}":      _build_today_calls_table(top_calls),
        "{{re_engagement_table}}":  _build_re_engagement_table(re_engage),
        "{{breakdown_cards}}":      _build_breakdown_cards(stats),
        "{{funnel_json}}":          json.dumps({
            "labels": funnel_labels, "values": funnel_values,
        }),
        "{{generated_at}}":         now.strftime("%d/%m/%Y %H:%M:%S UTC"),
    }
    for k, v in placeholders.items():
        h = h.replace(k, v)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(h, encoding="utf-8")
    log.info("[morning_dashboard] wrote {p} ({n} chars)",
             p=output_path, n=len(h))
    return output_path
