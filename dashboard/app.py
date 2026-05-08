"""
PATABRAVA — Captação de imóveis
Dashboard de oportunidades em tempo real.

Run: streamlit run dashboard/app.py
     python main.py dashboard
"""
from __future__ import annotations

import base64
import sys
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
from PIL import Image as PILImage


# ─── Brand assets ────────────────────────────────────────────────────────────
_STATIC_DIR  = ROOT / "static"
_LOGO_PATH   = _STATIC_DIR / "logo.png"
_LOGO2X_PATH = _STATIC_DIR / "logo@2x.png"
_FAVICON     = _STATIC_DIR / "favicon.png"


@lru_cache(maxsize=4)
def _asset_b64(path: Path) -> str:
    """Read an image asset once and return a base64 data URI."""
    if not path.exists():
        return ""
    suffix = path.suffix.lstrip(".").lower() or "png"
    mime = {"jpg": "jpeg", "svg": "svg+xml"}.get(suffix, suffix)
    return f"data:image/{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


# ─── i18n — Portuguese / English ───────────────────────────────────────────
# Single source of truth for every user-facing string that needs to switch
# language. Keys use dot-namespacing so it's easy to scan. Missing keys
# fall back to the key itself, so a typo is visible in the UI.

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Top toggle ─────────────────────────────────────────────────────────
    "lang.label":                 {"pt": "Idioma",                    "en": "Language"},

    # ── Sidebar nav groups ────────────────────────────────────────────────
    "nav.hunt.title":             {"pt": "Caça",                      "en": "Hunt"},
    "nav.hunt.caption":           {"pt": "Encontrar leads",           "en": "Find leads"},
    "nav.sell.title":              {"pt": "Venda",                     "en": "Sell"},
    "nav.sell.caption":            {"pt": "Trabalhar leads",           "en": "Work leads"},
    "nav.intel.title":             {"pt": "Inteligência",              "en": "Intelligence"},
    "nav.intel.caption":           {"pt": "Análise estratégica",       "en": "Strategic analysis"},
    "nav.engine.title":            {"pt": "Motor",                     "en": "Engine"},
    "nav.engine.caption":          {"pt": "Bastidores",                "en": "Behind the scenes"},

    # ── Sidebar nav items (label · caption) ───────────────────────────────
    "nav.dashboard.label":         {"pt": "Dashboard",                 "en": "Dashboard"},
    "nav.dashboard.caption":       {"pt": "Vista do dia",              "en": "Daily view"},
    "nav.hot.label":               {"pt": "HOT Focus",                 "en": "HOT Focus"},
    "nav.hot.caption":             {"pt": "Acção imediata",            "en": "Immediate action"},
    "nav.premarket.label":         {"pt": "Pre-Market",                "en": "Pre-Market"},
    "nav.premarket.caption":       {"pt": "Antes do mercado",          "en": "Before the market"},
    "nav.opportunities.label":     {"pt": "Oportunidades",             "en": "Opportunities"},
    "nav.opportunities.caption":   {"pt": "Stock completo",            "en": "Full stock"},
    "nav.crm.label":               {"pt": "CRM",                       "en": "CRM"},
    "nav.crm.caption":             {"pt": "Pipeline de negociação",    "en": "Sales pipeline"},
    "nav.activity.label":          {"pt": "Atividade",                 "en": "Activity"},
    "nav.activity.caption":        {"pt": "Cronologia",                "en": "Timeline"},
    "nav.map.label":               {"pt": "Mapa & BI",                 "en": "Map & BI"},
    "nav.map.caption":             {"pt": "Geografia & funil",         "en": "Geography & funnel"},
    "nav.system.label":            {"pt": "Sistema",                   "en": "System"},
    "nav.system.caption":          {"pt": "Saúde operacional",         "en": "Operational health"},
    "nav.engine_page.label":       {"pt": "Motor",                     "en": "Engine"},
    "nav.engine_page.caption":     {"pt": "Pipeline interno",          "en": "Internal pipeline"},
    "nav.export.label":            {"pt": "Exportar",                  "en": "Export"},
    "nav.export.caption":          {"pt": "Trocas de dados",           "en": "Data exchange"},

    # ── Maison hero (Dashboard) ───────────────────────────────────────────
    "maison.eyebrow":              {"pt": "Maison · Angariação Lisboa",
                                    "en": "Maison · Lisbon listings desk"},
    "maison.title.line1":          {"pt": "Patabrava",                  "en": "Patabrava"},
    "maison.title.line2":          {"pt": "Maison de l'immobilier",     "en": "Maison de l'immobilier"},
    "maison.deck":                 {"pt": "Lead intelligence em tempo real. Cada manhã, uma nova selecção "
                                          "de imóveis directamente do proprietário — para a equipa angariar antes "
                                          "de qualquer outra agência da capital.",
                                    "en": "Real-time lead intelligence. Every morning, a fresh selection of "
                                          "owner-direct listings — for the team to capture before any other "
                                          "agency in the city."},
    "maison.byline.opps":          {"pt": "{n} oportunidades activas",  "en": "{n} active opportunities"},
    "maison.figure.lbl":           {"pt": "HOT na agenda",              "en": "HOT on the agenda"},
    "maison.figure.sub.new":       {"pt": "+ {n} novos hoje",           "en": "+ {n} new today"},
    "maison.figure.sub.none":      {"pt": "sem novos hoje",             "en": "none new today"},
    "maison.stat.warm":            {"pt": "Warm",                       "en": "Warm"},
    "maison.stat.with_phone":      {"pt": "Com telefone",               "en": "With phone"},
    "maison.stat.avg_score":       {"pt": "Score médio",                "en": "Avg. score"},

    # Section markers
    "marker.daily_view":           {"pt": "Vista do dia",               "en": "Daily view"},
    "marker.daily_view.caption":   {"pt": "Indicadores principais",     "en": "Key indicators"},
    "marker.lots":                 {"pt": "Lots du jour",               "en": "Lots du jour"},
    "marker.lots.caption":         {"pt": "Top accionáveis · ordem de prioridade",
                                    "en": "Top actionable · priority order"},
    "marker.cartography":          {"pt": "Carta geográfica",           "en": "Cartography"},
    "marker.cartography.caption":  {"pt": "Densidade · score · €/m²",   "en": "Density · score · €/m²"},

    # ── Quick actions strip ───────────────────────────────────────────────
    "qa.heading":                  {"pt": "ATALHOS DO DIA",             "en": "DAILY SHORTCUTS"},
    "qa.hot":                      {"pt": "🔥  Ir para HOT Focus",      "en": "🔥  Open HOT Focus"},
    "qa.update":                   {"pt": "⟳  Atualizar dados agora",   "en": "⟳  Refresh data now"},
    "qa.update.spinner":           {"pt": "A executar pipeline (scrape · process · score)…",
                                    "en": "Running pipeline (scrape · process · score)…"},
    "qa.update.success":           {"pt": "✓  {a} novos · {b} actualizados",
                                    "en": "✓  {a} new · {b} updated"},
    "qa.export":                   {"pt": "📋  Exportar lista HOT",     "en": "📋  Export HOT list"},
    "qa.export.toast":             {"pt": "✓  Ficheiro: {p}",           "en": "✓  File: {p}"},
    "qa.map":                      {"pt": "📊  Mapa & inteligência",    "en": "📊  Map & intelligence"},

    # ── Empty state ───────────────────────────────────────────────────────
    "empty.eyebrow":               {"pt": "Pronto para começar",        "en": "Ready to begin"},
    "empty.title.before":          {"pt": "Lança o ",                   "en": "Start the "},
    "empty.title.em":              {"pt": "motor",                      "en": "engine"},
    "empty.title.after":           {"pt": ".",                          "en": "."},
    "empty.deck":                  {"pt": "A base de dados está vazia — ainda não há leads para mostrar. "
                                          "O processo é simples: o motor varre os portais, identifica "
                                          "proprietários directos e traz contactos com telefone para a tua agenda.",
                                    "en": "The database is empty — no leads to show yet. The process is simple: "
                                          "the engine sweeps the portals, identifies direct owners, and brings "
                                          "phone contacts to your agenda."},
    "empty.step1.title":           {"pt": "Atualiza dados",             "en": "Refresh data"},
    "empty.step1.body":            {"pt": "Carrega <em>\"Atualizar dados agora\"</em> acima. O scrape leva ~5–10 min na primeira vez.",
                                    "en": "Hit <em>\"Refresh data now\"</em> above. The first scrape takes ~5–10 min."},
    "empty.step2.title":           {"pt": "Vai a HOT Focus",            "en": "Go to HOT Focus"},
    "empty.step2.body":            {"pt": "Os leads mais quentes do dia aparecem ranked por urgência. Liga primeiro aos do topo.",
                                    "en": "The day's hottest leads appear ranked by urgency. Call the top ones first."},
    "empty.step3.title":           {"pt": "Move no CRM",                "en": "Move in the CRM"},
    "empty.step3.body":            {"pt": "Cada lead contactado avança no funil — visitas, propostas, ganhos.",
                                    "en": "Each contacted lead advances through the funnel — visits, offers, wins."},

    # ── Footer ────────────────────────────────────────────────────────────
    "footer.lemma":                {"pt": "Maison de l'immobilier",     "en": "Maison de l'immobilier"},

    # ── Mini hero per page (eyebrow · title · deck · byline_caption) ──────
    "page.hot.eyebrow":            {"pt": "Hot Focus · A próxima ligação",
                                    "en": "Hot Focus · The next call"},
    "page.hot.title.before":       {"pt": "O telefonema ",              "en": "The right "},
    "page.hot.title.em":           {"pt": "certo",                      "en": "call"},
    "page.hot.title.after":        {"pt": ", agora.",                   "en": ", right now."},
    "page.hot.deck":               {"pt": "Top 50 leads ordenados por urgência composta — score, queda de preço, "
                                          "dias parado e qualidade de contacto cruzados num só ranking. Os botões "
                                          "abaixo abrem chamada, WhatsApp ou email directamente.",
                                    "en": "Top 50 leads ranked by composite urgency — score, price drops, days "
                                          "stalled and contact quality merged into one ranking. The buttons below "
                                          "open call, WhatsApp or email directly."},
    "page.hot.byline":             {"pt": "Acção imediata",              "en": "Immediate action"},

    "page.opportunities.eyebrow":  {"pt": "Mercado · Catálogo do dia",  "en": "Market · Catalogue of the day"},
    "page.opportunities.title.before": {"pt": "Ranking de ",             "en": "Ranking of "},
    "page.opportunities.title.em":     {"pt": "oportunidades",           "en": "opportunities"},
    "page.opportunities.title.after":  {"pt": ".",                       "en": "."},
    "page.opportunities.deck":     {"pt": "Todas as propriedades detectadas, classificadas pela pontuação composta. "
                                          "Filtra por classificação, fase do funil e tipo de vendedor para refinar a tua selecção.",
                                    "en": "Every detected property, ranked by composite score. Filter by tier, "
                                          "funnel stage and seller type to refine your selection."},
    "page.opportunities.byline":   {"pt": "Todo o stock",                "en": "All stock"},

    "page.crm.eyebrow":            {"pt": "Gestão · Acompanhamento",    "en": "Management · Tracking"},
    "page.crm.title.before":       {"pt": "Pipeline de ",                "en": "Sales "},
    "page.crm.title.em":           {"pt": "negociação",                  "en": "pipeline"},
    "page.crm.title.after":        {"pt": ".",                           "en": "."},
    "page.crm.deck":               {"pt": "Cada lead em fase própria — contactos feitos, visitas marcadas, "
                                          "propostas em curso, ganhos. Mover é arrastar; tudo guardado em histórico.",
                                    "en": "Every lead in its own stage — contacted, visits booked, offers in motion, "
                                          "won. Moving is dragging; everything saved in history."},
    "page.crm.byline":             {"pt": "Coluna por coluna",           "en": "Column by column"},

    "page.activity.eyebrow":       {"pt": "Atividade · Cronologia",      "en": "Activity · Timeline"},
    "page.activity.title.before":  {"pt": "O que ",                      "en": "What "},
    "page.activity.title.em":      {"pt": "aconteceu",                   "en": "happened"},
    "page.activity.title.after":   {"pt": " hoje.",                      "en": " today."},
    "page.activity.deck":          {"pt": "Novos leads que entraram, quedas de preço detectadas, "
                                          "anúncios re-publicados, listagens sumidas e follow-ups gerados. A história "
                                          "contínua da operação, vista pela ordem em que foi acontecendo.",
                                    "en": "New leads that came in, price drops detected, ads re-posted, "
                                          "listings vanished, follow-ups generated. The continuous story of the "
                                          "operation, in the order it happened."},
    "page.activity.byline":        {"pt": "Diário",                      "en": "Diary"},

    "page.map.eyebrow":            {"pt": "Mapa & BI · Visão de cima",   "en": "Map & BI · From above"},
    "page.map.title.before":       {"pt": "A última ",                   "en": "The past "},
    "page.map.title.em":           {"pt": "semana",                      "en": "week"},
    "page.map.title.after":        {"pt": ", em panorama.",              "en": ", in panorama."},
    "page.map.deck":               {"pt": "Funil, geografia das oportunidades e ranking das agências cruzados "
                                          "num só lugar. Os 7 dias mais recentes — o que entrou, o que aqueceu, o que mexeu de preço.",
                                    "en": "Funnel, opportunity geography and agency ranking merged into one "
                                          "place. The most recent 7 days — what came in, what heated up, what shifted in price."},
    "page.map.byline":             {"pt": "Inteligência consolidada",    "en": "Consolidated intelligence"},
    "page.map.stat.new7d":         {"pt": "Novos 7d",                    "en": "New (7d)"},
    "page.map.stat.newhot":        {"pt": "Novos HOT",                   "en": "New HOT"},
    "page.map.stat.drops":         {"pt": "Quedas preço",                "en": "Price drops"},
    "page.map.stat.super":         {"pt": "Super-sellers",               "en": "Super-sellers"},
    "page.map.stat.contacted":     {"pt": "Contactados",                 "en": "Contacted"},

    "page.premarket.eyebrow":      {"pt": "Inteligência · Sinais antecipados",
                                    "en": "Intelligence · Early signals"},
    "page.premarket.title.before": {"pt": "Pré-mercado ",                 "en": "Silent "},
    "page.premarket.title.em":     {"pt": "silencioso",                   "en": "pre-market"},
    "page.premarket.title.after":  {"pt": ".",                            "en": "."},
    "page.premarket.deck":         {"pt": "Proprietários que podem vender antes de pôr o anúncio — licenças de "
                                          "obras emitidas, remodelações em curso, mudanças profissionais. Apanhar antes "
                                          "do mercado é a vantagem competitiva.",
                                    "en": "Owners who may sell before listing — building permits, ongoing "
                                          "renovations, professional moves. Catching them before the market is the edge."},
    "page.premarket.byline":       {"pt": "Antes da concorrência",       "en": "Ahead of competitors"},

    "page.system.eyebrow":         {"pt": "Sistema · Sala de máquinas",  "en": "System · Engine room"},
    "page.system.title.before":    {"pt": "Saúde ",                      "en": "Operational "},
    "page.system.title.em":        {"pt": "operacional",                 "en": "health"},
    "page.system.title.after":     {"pt": ".",                           "en": "."},
    "page.system.deck":            {"pt": "Estado dos últimos runs do scrapper, backups da base de dados, "
                                          "jobs agendados e fila de processamento. Tudo o que mantém a operação a respirar.",
                                    "en": "Last scraper runs, database backups, scheduled jobs and processing "
                                          "queue. Everything that keeps the operation breathing."},
    "page.system.byline":          {"pt": "Diagnóstico",                 "en": "Diagnostics"},

    "page.engine_page.eyebrow":    {"pt": "Operações · Bastidores",      "en": "Operations · Backstage"},
    "page.engine_page.title.before": {"pt": "O ",                         "en": "The "},
    "page.engine_page.title.em":     {"pt": "motor",                      "en": "engine"},
    "page.engine_page.title.after":  {"pt": ".",                          "en": "."},
    "page.engine_page.deck":       {"pt": "Recolha automática · normalização · identificação de proprietários "
                                          "· scoring · alertas HOT. Os engrenagens que correm enquanto a equipa dorme.",
                                    "en": "Automatic collection · normalisation · owner identification · "
                                          "scoring · HOT alerts. The gears that turn while the team sleeps."},
    "page.engine_page.byline":     {"pt": "Pipeline interno",             "en": "Internal pipeline"},

    "page.export.eyebrow":         {"pt": "Trocas · Entre sistemas",     "en": "Exchange · Between systems"},
    "page.export.title.before":    {"pt": "Exportar & ",                 "en": "Export & "},
    "page.export.title.em":        {"pt": "importar",                    "en": "import"},
    "page.export.title.after":     {"pt": ".",                           "en": "."},
    "page.export.deck":            {"pt": "Listas prontas para entregar ao cliente, ou contactos antigos do CRM "
                                          "para alimentar o motor. Os formatos certos para cada caso.",
                                    "en": "Lists ready to deliver to clients, or older CRM contacts to feed the "
                                          "engine. The right format for each case."},
    "page.export.byline":          {"pt": "CSV · JSON · Excel",          "en": "CSV · JSON · Excel"},

    # ── Sidebar filter sections + controls ─────────────────────────────────
    "sb.search.header":            {"pt": "Pesquisa",                    "en": "Search"},
    "sb.search.placeholder":       {"pt": "Ex: T2 Lisboa piscina · 'Avenidas Novas'",
                                    "en": "e.g. T2 Lisbon pool · 'Avenidas Novas'"},
    "sb.search.help":              {"pt": "Pesquisa rápida (FTS5). Operadores: AND OR NOT NEAR · "
                                          "Aspas para frase: \"Avenidas Novas\" · Acaba com * para prefix: apartament*",
                                    "en": "Fast search (FTS5). Operators: AND OR NOT NEAR · "
                                          "Quote phrases: \"Avenidas Novas\" · End with * for prefix: apartament*"},
    "sb.bookmarks":                {"pt": "Bookmarks",                    "en": "Bookmarks"},
    "sb.bookmarks.help":           {"pt": "Carregar pesquisa guardada",   "en": "Load saved search"},
    "sb.bookmarks.save_as":        {"pt": "Guardar como…",                "en": "Save as…"},
    "sb.bookmarks.save_btn":       {"pt": "Guardar atual",                "en": "Save current"},
    "sb.presets.header":           {"pt": "Filtros rápidos",              "en": "Quick filters"},
    "sb.presets.fsbo_hot":         {"pt": "🔥 FSBO HOT",                  "en": "🔥 FSBO HOT"},
    "sb.presets.banks":            {"pt": "🏦 Bancos",                    "en": "🏦 Banks"},
    "sb.presets.auctions":         {"pt": "⚖ Leilões",                    "en": "⚖ Auctions"},
    "sb.presets.urgent":           {"pt": "⏰ Urgente",                    "en": "⏰ Urgent"},
    "sb.presets.with_phone":       {"pt": "📞 Com telefone",              "en": "📞 With phone"},
    "sb.presets.with_email":       {"pt": "✉ Com e-mail",                 "en": "✉ With email"},
    "sb.presets.sea_view":         {"pt": "🌅 Vista mar",                 "en": "🌅 Sea view"},
    "sb.presets.clear":            {"pt": "🧹 Limpar",                    "en": "🧹 Clear"},
    "sb.advanced":                 {"pt": "⚙  Refinamento avançado",      "en": "⚙  Advanced filters"},
    "sb.advanced.data_origin":     {"pt": "Origem dos dados",             "en": "Data source"},
    "sb.advanced.contact":         {"pt": "Contacto",                     "en": "Contact"},
    "sb.advanced.geo_typology":    {"pt": "Geografia & tipologia",        "en": "Geography & typology"},
    "sb.advanced.exclude_relay":   {"pt": "Excluir relay/OLX (6xx)",      "en": "Exclude relay/OLX (6xx)"},
    "sb.advanced.exclude_relay.help": {"pt": "Remove números temporários OLX que expiram quando o anúncio sai",
                                       "en": "Removes temporary OLX numbers that expire when the listing closes"},

    # Data origin / contact / owner / typology select options
    "opt.all":                     {"pt": "Todos",                        "en": "All"},
    "opt.real_only":               {"pt": "🟢 Apenas reais",              "en": "🟢 Real only"},
    "opt.demo_only":               {"pt": "🟡 Apenas demo",               "en": "🟡 Demo only"},
    "opt.with_phone":              {"pt": "📞 Com telefone",              "en": "📞 With phone"},
    "opt.mobile_only":             {"pt": "📱 Só telemóvel real",          "en": "📱 Mobile only"},
    "opt.with_email":              {"pt": "✉ Com email",                  "en": "✉ With email"},
    "opt.any_contact":             {"pt": "✅ Qualquer contacto",         "en": "✅ Any contact"},
    "opt.no_contact":              {"pt": "❌ Sem contacto",              "en": "❌ No contact"},
    "opt.zone.label":              {"pt": "Zona",                         "en": "Zone"},
    "opt.zone.all":                {"pt": "Todas as zonas",               "en": "All zones"},
    "opt.typology.label":          {"pt": "Tipologia",                    "en": "Typology"},
    "opt.typology.all":            {"pt": "Todas as tipologias",          "en": "All typologies"},
    "opt.owner.label":             {"pt": "Tipo vendedor",                "en": "Seller type"},
    "opt.owner.fsbo":              {"pt": "👤 Particular (FSBO)",         "en": "👤 Owner direct (FSBO)"},
    "opt.owner.agency":            {"pt": "🏢 Agência",                   "en": "🏢 Agency"},
    "opt.owner.developer":         {"pt": "🏗 Promotor",                   "en": "🏗 Developer"},
    "opt.owner.unknown":           {"pt": "❓ Desconhecido",               "en": "❓ Unknown"},
    "opt.lead_type.label":         {"pt": "Tipo de lead",                 "en": "Lead type"},
    "opt.lead_type.fsbo":          {"pt": "🏠 FSBO (venda)",              "en": "🏠 FSBO (sale)"},
    "opt.lead_type.frbo":          {"pt": "🔑 FRBO (arrendamento)",       "en": "🔑 FRBO (rental)"},
    "opt.lead_type.active":        {"pt": "👥 Active Owner",              "en": "👥 Active Owner"},
    "opt.lead_type.agency":        {"pt": "🏢 Agência",                   "en": "🏢 Agency"},
    "opt.lead_type.dev":           {"pt": "🚧 Promotor",                  "en": "🚧 Developer"},
    "opt.csource.label":           {"pt": "Origem do contacto",           "en": "Contact source"},
    "opt.csource.direct":          {"pt": "Direto",                       "en": "Direct"},
    "opt.csource.agency_site":     {"pt": "Agência / Site",               "en": "Agency / Website"},
    "opt.csource.cross":           {"pt": "Cross-portal",                 "en": "Cross-portal"},
    "opt.score_min":               {"pt": "Pontuação mínima",             "en": "Minimum score"},
    "sb.refresh_btn":              {"pt": "Actualizar oportunidades",     "en": "Refresh opportunities"},
    "sb.market_run_btn":           {"pt": "Executar análise de mercado",  "en": "Run market analysis"},

    # ── KPI metric labels (Dashboard) ─────────────────────────────────────
    "kpi.hot":                     {"pt": "🔴 HOT",                       "en": "🔴 HOT"},
    "kpi.hot.help":                {"pt": "Score >= 75",                  "en": "Score >= 75"},
    "kpi.hot.delta":               {"pt": "+{n} hoje",                    "en": "+{n} today"},
    "kpi.warm":                    {"pt": "🟡 WARM",                      "en": "🟡 WARM"},
    "kpi.warm.help":               {"pt": "Score 50-74",                  "en": "Score 50-74"},
    "kpi.today":                   {"pt": "📥 Hoje",                      "en": "📥 Today"},
    "kpi.today.help":              {"pt": "Últimas 24h",                  "en": "Last 24h"},
    "kpi.in_negotiation":          {"pt": "🔄 Em negociação",             "en": "🔄 In negotiation"},
    "kpi.in_negotiation.help":     {"pt": "Leads activos no funil",       "en": "Active leads in funnel"},
    "kpi.avg_score":               {"pt": "⭐ Score médio",                "en": "⭐ Avg. score"},
    "kpi.avg_score.help":          {"pt": "Média das oportunidades activas",
                                    "en": "Average of active opportunities"},
    "kpi.with_phone":              {"pt": "📞 Com telefone",              "en": "📞 With phone"},
    "kpi.with_phone.help":         {"pt": "Leads com número de telefone — contacto directo imediato (+15 pts)",
                                    "en": "Leads with phone number — immediate direct contact (+15 pts)"},
    "kpi.with_email":              {"pt": "✉️ Com email",                  "en": "✉️ With email"},
    "kpi.with_email.help":         {"pt": "Leads com email disponível (+5 pts)",
                                    "en": "Leads with email available (+5 pts)"},
    "kpi.no_contact":              {"pt": "🚫 Sem contacto",              "en": "🚫 No contact"},
    "kpi.no_contact.help":         {"pt": "Leads sem qualquer contacto — penalização -15 pts no score",
                                    "en": "Leads with no contact — -15 pts score penalty"},

    # ── Section labels (lbl-section across pages) ─────────────────────────
    "lbl.priority_opps":           {"pt": "Oportunidades prioritárias",   "en": "Priority opportunities"},
    "lbl.trend_30d":               {"pt": "Tendência (últimos 30 dias)",  "en": "Trend (last 30 days)"},
    "lbl.score_distribution":     {"pt": "Distribuição de pontuações",    "en": "Score distribution"},
    "lbl.opps_by_zone":            {"pt": "Oportunidades por zona",       "en": "Opportunities by zone"},
    "lbl.compa rables":            {"pt": "Comparáveis",                  "en": "Comparables"},
    "lbl.pipeline_flow":           {"pt": "Fluxo de análise automática",  "en": "Automated analysis flow"},
    "lbl.opps_map":                {"pt": "Mapa de oportunidades",        "en": "Opportunities map"},

    # ── Network / IP status widget ─────────────────────────────────────────
    "net.header":                  {"pt": "Estado da rede",               "en": "Network status"},
    "net.ip":                      {"pt": "IP público",                   "en": "Public IP"},
    "net.country":                 {"pt": "País",                         "en": "Country"},
    "net.org":                     {"pt": "Operadora",                    "en": "Carrier"},
    "net.kind.mobile":             {"pt": "📱 Dados móveis",              "en": "📱 Mobile data"},
    "net.kind.vpn":                {"pt": "🛡 NordVPN/VPN",                "en": "🛡 NordVPN/VPN"},
    "net.kind.unknown":            {"pt": "🌐 Rede directa",              "en": "🌐 Direct network"},
    "net.portals.title":           {"pt": "Portais",                      "en": "Portals"},
    "net.portal.clean":            {"pt": "limpo",                        "en": "clean"},
    "net.portal.blocked":          {"pt": "bloqueado",                    "en": "blocked"},
    "net.portal.unknown":          {"pt": "desconhecido",                 "en": "unknown"},
    "net.refresh":                 {"pt": "Verificar agora",              "en": "Check now"},
    "net.status.allclean":         {"pt": "Tudo limpo — pronto para correr.",
                                    "en": "All clean — ready to run."},
    "net.status.someblocked":      {"pt": "{n} portal(is) bloqueado(s) deste IP.",
                                    "en": "{n} portal(s) blocked from this IP."},
    "net.tip.heading":             {"pt": "Como destrancar",              "en": "How to unblock"},
    "net.tip.line1":               {"pt": "1. Liga o NordVPN num servidor de Portugal",
                                    "en": "1. Connect NordVPN to a Portugal server"},
    "net.tip.line2":               {"pt": "2. Ou desliga e religa os dados móveis (novo IP CGNAT)",
                                    "en": "2. Or toggle mobile data off/on (new CGNAT IP)"},
    "net.tip.line3":               {"pt": "3. Ou aguarda 6-24h para o IP descongelar",
                                    "en": "3. Or wait 6-24h for the IP to cool down"},

    # ── Async run progress strip ───────────────────────────────────────────
    "run.live.eyebrow":           {"pt": "MOTOR EM CURSO",                "en": "ENGINE RUNNING"},
    "run.live.elapsed":           {"pt": "Tempo decorrido",               "en": "Elapsed"},
    "run.live.zones":             {"pt": "Zonas",                         "en": "Zones"},
    "run.live.listings":          {"pt": "Anúncios capturados",           "en": "Listings captured"},
    "run.live.last_zone":         {"pt": "A processar",                   "en": "Processing"},
    "run.live.blocks":            {"pt": "Bloqueios",                     "en": "Blocks"},
    "run.live.stop":              {"pt": "Parar agora",                   "en": "Stop now"},
    "run.live.refresh":           {"pt": "Auto-refresh a cada 5s",        "en": "Auto-refresh every 5s"},
    "run.done.eyebrow.ok":        {"pt": "MOTOR PRONTO",                  "en": "ENGINE DONE"},
    "run.done.eyebrow.ko":        {"pt": "MOTOR PAROU",                   "en": "ENGINE STOPPED"},
    "run.done.dismiss":           {"pt": "Fechar",                        "en": "Dismiss"},
    "run.starting":               {"pt": "A arrancar o motor…",           "en": "Starting the engine…"},
    "run.already_running":        {"pt": "Já há um run em curso.",        "en": "A run is already in flight."},
    "run.preflight.rejected":     {"pt": "Lançamento recusado",           "en": "Launch refused"},
    "run.preflight.ip_blocked":   {"pt": "O IP {ip} está bloqueado em {portals}.",
                                    "en": "IP {ip} is blocked on {portals}."},
    "run.preflight.suggestion":   {"pt": "Muda de servidor NordVPN ou alterna os dados móveis. "
                                          "Volta a clicar quando o widget de rede ficar verde.",
                                    "en": "Switch NordVPN server or toggle mobile data. "
                                          "Try again when the network widget turns green."},
    "run.preflight.force":        {"pt": "Forçar mesmo assim",            "en": "Force launch anyway"},
    "run.diff.new":               {"pt": "🟢 {n} leads novos hoje",       "en": "🟢 {n} new leads today"},
    "run.diff.zero":              {"pt": "Sem leads novos.",              "en": "No new leads."},

    # ── Persona health widget ──────────────────────────────────────────────
    "ph.header":                  {"pt": "Saúde das personas",            "en": "Persona health"},
    "ph.empty":                   {"pt": "Sem dados ainda — corre o motor para começar a registar.",
                                    "en": "No data yet — run the engine to start tracking."},
    "ph.cooldown":                {"pt": "Em cooldown {m} min",           "en": "Cooldown {m} min"},
    "ph.win_rate":                {"pt": "{pct}%",                        "en": "{pct}%"},
    "ph.reset":                   {"pt": "Reset stats",                   "en": "Reset stats"},

    # ── Schedule editor ────────────────────────────────────────────────────
    "sch.section.eyebrow":        {"pt": "Agenda automática",             "en": "Automated schedule"},
    "sch.section.title":          {"pt": "Cada manhã, sem clique.",       "en": "Every morning, hands-off."},
    "sch.section.deck":           {"pt": "Define quando o motor corre — o resto é silêncio. "
                                          "Cada agenda é um pacote independente: hora, dias da semana, fontes e zonas.",
                                    "en": "Set when the engine runs — the rest is silence. "
                                          "Each schedule is an independent bundle: time, weekdays, sources and zones."},
    "sch.empty":                  {"pt": "Nenhuma agenda criada. Adiciona uma abaixo.",
                                    "en": "No schedules yet. Add one below."},
    "sch.next_in":                {"pt": "Próximo em",                    "en": "Next in"},
    "sch.last_run":               {"pt": "Último",                        "en": "Last run"},
    "sch.never":                  {"pt": "Nunca",                          "en": "Never"},
    "sch.run_now":                {"pt": "Correr agora",                   "en": "Run now"},
    "sch.delete":                 {"pt": "Apagar",                         "en": "Delete"},
    "sch.add.title":              {"pt": "Nova agenda",                    "en": "New schedule"},
    "sch.field.name":             {"pt": "Nome",                           "en": "Name"},
    "sch.field.hour":             {"pt": "Hora",                           "en": "Hour"},
    "sch.field.minute":           {"pt": "Minuto",                         "en": "Minute"},
    "sch.field.days":             {"pt": "Dias da semana",                 "en": "Days of week"},
    "sch.field.sources":          {"pt": "Fontes (vazio = automático)",    "en": "Sources (empty = auto)"},
    "sch.field.zones":            {"pt": "Zonas (vazio = todas)",          "en": "Zones (empty = all)"},
    "sch.create":                 {"pt": "Criar agenda",                   "en": "Create schedule"},
    "sch.created":                {"pt": "✓ Agenda criada",                "en": "✓ Schedule created"},
    "sch.deleted":                {"pt": "✓ Agenda apagada",               "en": "✓ Schedule deleted"},
    "sch.daemon.note":            {"pt": "ⓘ  Estas agendas servem de referência. "
                                          "Para correrem sozinhas, instala o cron: "
                                          "`crontab -e` e adiciona uma linha por agenda.",
                                    "en": "ⓘ  These schedules are reference definitions. "
                                          "For unattended execution, install via cron: "
                                          "`crontab -e` and add one line per schedule."},
}


def t(key: str, **fmt) -> str:
    """Translate a key using the language stored in session_state.
    Falls back to the key itself when missing — surfaces typos quickly.
    Optional kwargs let callers do `.format(**fmt)` style interpolation.
    """
    lang = st.session_state.get("__lang", "pt")
    entry = TRANSLATIONS.get(key, {})
    raw = entry.get(lang) or entry.get("pt") or key
    if fmt:
        try:
            return raw.format(**fmt)
        except Exception:
            return raw
    return raw


# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Patabrava · Lead Intelligence",
    page_icon=PILImage.open(_FAVICON) if _FAVICON.exists() else "◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Streamlit native top-of-sidebar logo (1.31+). Tolerates missing asset.
if _LOGO_PATH.exists() and hasattr(st, "logo"):
    st.logo(str(_LOGO2X_PATH if _LOGO2X_PATH.exists() else _LOGO_PATH))

# ─── CSS: PATABRAVA premium dark theme ──────────────────────────────────────────
# Glassmorphism + animated gradients + micro-interactions. Designed for an
# upmarket SaaS feel: investors, executives, agencies. Drop-in safe — only
# Streamlit-DOM selectors, no app-level class restructuring.
#
# Brand palette
#   ink/00     #0a0806   page (deepest)
#   ink/10     #141008   surface (sidebar / cards background)
#   ink/20     #1f180c   surface raised
#   ink/30     #2a2010   border / subtle
#   mint/0     #ddc269   primary accent
#   mint/+     #a8861a   primary deep
#   sky        #38bdf8   info
#   violet     #a78bfa   premium
#   rose       #fb7185   hot/danger
#   amber      #fbbf24   warm
#   ice        #f5efe0   text high
#   fog        #d6cdb8   text mid
#   smoke      #a89c80   text muted
#   slate      #786c52   text dim

_CSS_BASE = """<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT@0,9..144,300..700,0..100;1,9..144,300..700,0..100&family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap');

/* ──── Root tokens ──────────────────────────────────────────────────────── */
/*
 *  PATABRAVA — MAISON DE L'IMMOBILIER
 *  Aesthetic direction: auction house × architectural digest.
 *  Fraunces (variable serif, opsz axis) carries every "moment" — display
 *  titles, dominant numerals, italic accents, kicker labels. Inter remains
 *  the workhorse for tabular data and dense UI text. Space Grotesk lingers
 *  only on legacy components for now.
 */
:root {
  --ink-00: #0a0806;
  --ink-10: #141008;
  --ink-20: #1f180c;
  --ink-30: #2a2010;
  --ink-40: #3a2c14;

  --mint:    #ddc269;
  --mint-d:  #a8861a;
  --mint-l:  #eedaa0;
  --sky:     #38bdf8;
  --violet:  #a78bfa;
  --rose:    #fb7185;
  --amber:   #fbbf24;

  --ice:   #f5efe0;
  --fog:   #d6cdb8;
  --smoke: #a89c80;
  --slate: #786c52;
  --dust:  #5c5240;

  --grad-primary:  linear-gradient(135deg, #a8861a 0%, #ddc269 50%, #eedaa0 100%);
  --grad-hot:      linear-gradient(135deg, #fb7185 0%, #f43f5e 100%);
  --grad-warm:     linear-gradient(135deg, #fbbf24 0%, #f97316 100%);
  --grad-cold:     linear-gradient(135deg, #a89c80 0%, #786c52 100%);
  --grad-surface:  linear-gradient(180deg, rgba(19,26,49,.6) 0%, rgba(11,16,32,.4) 100%);

  --shadow-card:  0 1px 0 rgba(255,255,255,.04) inset, 0 8px 32px -16px rgba(0,0,0,.6);
  --shadow-glow:  0 0 0 1px rgba(221,194,105,.15), 0 8px 40px -12px rgba(221,194,105,.25);
  --shadow-glow-violet: 0 0 0 1px rgba(198, 162, 100,.18), 0 8px 40px -12px rgba(198, 162, 100,.3);

  /* ──── Editorial typography stack ─────────────────────────────────────── */
  --font-display: 'Fraunces', 'Cormorant Garamond', Georgia, serif;
  --font-body:    'Inter', system-ui, sans-serif;
  --font-mono:    'JetBrains Mono', ui-monospace, monospace;
  --font-legacy:  'Space Grotesk', sans-serif;

  /* Spacing scale — generous, magazine-like. Use these instead of literals. */
  --sp-1: 4px;   --sp-2: 8px;   --sp-3: 12px;   --sp-4: 18px;
  --sp-5: 28px;  --sp-6: 44px;  --sp-7: 72px;   --sp-8: 116px;

  /* Numeric type scale — used for editorial numerals */
  --num-xxl: clamp(72px, 11vw, 156px);   /* hero kicker */
  --num-xl:  clamp(40px, 5vw, 64px);     /* section anchor numeral */
  --num-lg:  clamp(28px, 3vw, 40px);     /* card-level KPI */
}

/* ──── Page chrome ─────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.stApp {
    background:
        radial-gradient(900px 480px at 8% -10%, rgba(221,194,105,.06), transparent 60%),
        radial-gradient(800px 480px at 92% 110%, rgba(198, 162, 100,.08), transparent 60%),
        var(--ink-00) !important;
}
.main .block-container {
    padding: 0 2.2rem 5rem !important;
    max-width: 1480px !important;
}
section[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, var(--ink-10) 0%, #08060a 100%) !important;
    border-right: 1px solid rgba(255,255,255,.04) !important;
    box-shadow: 1px 0 0 rgba(255,255,255,.02);
}
section[data-testid="stSidebar"] > div { padding-top: 0 !important; }

h1, h2, h3, h4 {
    color: var(--ice) !important;
    font-family: 'Space Grotesk', 'Inter', sans-serif !important;
    letter-spacing: -.02em !important;
}
h1 { font-weight: 700 !important; }
h2 { font-weight: 600 !important; }

/* ──── Streamlit metrics → glass cards with hover lift ─────────────────── */
[data-testid="stMetric"] {
    background:
        linear-gradient(180deg, rgba(29,39,71,.45) 0%, rgba(11,16,32,.85) 100%) !important;
    backdrop-filter: blur(12px) saturate(140%);
    -webkit-backdrop-filter: blur(12px) saturate(140%);
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 14px !important;
    padding: 1.05rem 1.25rem !important;
    box-shadow: var(--shadow-card);
    transition: transform .25s cubic-bezier(.4,0,.2,1),
                border-color .25s, box-shadow .25s;
    position: relative; overflow: hidden;
}
[data-testid="stMetric"]::before {
    content: "";
    position: absolute; inset: 0;
    background: var(--grad-primary);
    opacity: 0;
    transition: opacity .3s;
    pointer-events: none;
    border-radius: 14px;
    -webkit-mask:
        linear-gradient(#fff 0 0) content-box,
        linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
            mask-composite: exclude;
    padding: 1px;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    border-color: rgba(221,194,105,.3) !important;
    box-shadow: var(--shadow-glow);
}
[data-testid="stMetric"]:hover::before { opacity: .6; }

[data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.95rem !important;
    font-weight: 700 !important;
    color: var(--ice) !important;
    letter-spacing: -.025em !important;
    background: var(--grad-primary);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
    color: transparent !important;
}
[data-testid="stMetricLabel"] {
    font-size: .68rem !important;
    font-weight: 700 !important;
    color: var(--slate) !important;
    text-transform: uppercase !important;
    letter-spacing: 1.2px !important;
}
[data-testid="stMetricDelta"] svg { display: none; }

/* ──── Buttons ─────────────────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,.05) !important;
    margin: 1.5rem 0 !important;
}
.stButton > button {
    background: rgba(29,39,71,.5) !important;
    color: var(--fog) !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    letter-spacing: .01em !important;
    transition: all .2s cubic-bezier(.4,0,.2,1) !important;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}
.stButton > button:hover {
    background: rgba(221,194,105,.1) !important;
    color: var(--mint) !important;
    border-color: rgba(221,194,105,.4) !important;
    transform: translateY(-1px);
    box-shadow: 0 6px 22px -10px rgba(221,194,105,.45) !important;
}
.stButton > button:active { transform: translateY(0); }

/* Primary-tinted button class — opt-in via key */
.stButton button[kind="primary"] {
    background: var(--grad-primary) !important;
    color: #052016 !important;
    border: none !important;
    font-weight: 700 !important;
    box-shadow: 0 6px 24px -8px rgba(221,194,105,.5) !important;
}
.stButton button[kind="primary"]:hover {
    color: #052016 !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 32px -8px rgba(221,194,105,.7) !important;
}

/* ──── Form fields ─────────────────────────────────────────────────────── */
.stSelectbox [data-baseweb="select"] > div,
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    background: rgba(11,16,32,.6) !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 10px !important;
    color: var(--fog) !important;
    transition: border-color .2s, box-shadow .2s;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: rgba(221,194,105,.5) !important;
    box-shadow: 0 0 0 3px rgba(221,194,105,.15) !important;
    outline: none !important;
}

/* ──── Data frames ─────────────────────────────────────────────────────── */
.stDataFrame {
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-card);
}

/* ──── Expanders ───────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: rgba(29,39,71,.4) !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 10px !important;
    color: var(--fog) !important;
    transition: all .2s;
}
.streamlit-expanderHeader:hover {
    background: rgba(29,39,71,.6) !important;
    border-color: rgba(221,194,105,.2) !important;
}
.streamlit-expanderContent {
    background: rgba(5,8,16,.5) !important;
    border: 1px solid rgba(255,255,255,.04) !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    padding: 1.1rem !important;
}

/* ──── Tabs ────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: rgba(11,16,32,.5);
    padding: 4px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,.05);
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: var(--smoke) !important;
    font-weight: 600 !important;
    transition: all .2s !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(221,194,105,.12) !important;
    color: var(--mint) !important;
    box-shadow: 0 0 0 1px rgba(221,194,105,.25);
}

/* ──── Scrollbar — slim premium ────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--ink-30) 0%, var(--ink-40) 100%);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--mint-d) 0%, var(--sky) 100%);
}

/* ──── Streamlit header: blend into bg ─────────────────────────────────── */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
    backdrop-filter: blur(8px);
}
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stToolbar"] { background: transparent !important; }
[data-testid="stStatusWidget"] { color: var(--dust) !important; }
.stDeployButton { display: none !important; }
div[data-testid="stAppViewBlockContainer"] { padding-top: 1rem !important; }

/* ──── Page-level animations ───────────────────────────────────────────── */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}
@keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes glowPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(221,194,105,.45); }
    50%      { box-shadow: 0 0 0 8px rgba(221,194,105,0); }
}
@keyframes float {
    0%, 100% { transform: translateY(0); }
    50%      { transform: translateY(-3px); }
}

[data-testid="stMetric"],
.card,
.kanban-card,
.intel-box,
.alert-card,
.pf-wrap {
    animation: fadeUp .45s cubic-bezier(.4,0,.2,1) both;
}
</style>"""

_CSS_CARDS = """<style>
/* ──── Lead cards — glass + animated borders ───────────────────────────── */
.card {
    background:
        linear-gradient(180deg, rgba(29,39,71,.55) 0%, rgba(11,16,32,.85) 100%);
    backdrop-filter: blur(14px) saturate(140%);
    -webkit-backdrop-filter: blur(14px) saturate(140%);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 14px;
    position: relative;
    overflow: hidden;
    transition: transform .25s cubic-bezier(.4,0,.2,1),
                border-color .25s, box-shadow .25s;
    box-shadow: var(--shadow-card);
}
.card::after {
    content: "";
    position: absolute; inset: 0;
    border-radius: 14px;
    pointer-events: none;
    background: linear-gradient(135deg,
        rgba(221,194,105,0) 0%,
        rgba(221,194,105,.04) 30%,
        rgba(198, 162, 100,.04) 70%,
        rgba(56,189,248,0) 100%);
    opacity: 0;
    transition: opacity .3s;
}
.card:hover {
    transform: translateY(-2px);
    border-color: rgba(221,194,105,.25);
    box-shadow: 0 0 0 1px rgba(221,194,105,.1), 0 16px 48px -16px rgba(221,194,105,.18);
}
.card:hover::after { opacity: 1; }

.card-hot {
    border-color: rgba(251,113,133,.35);
    background:
        linear-gradient(135deg, rgba(251,113,133,.08) 0%, transparent 60%),
        linear-gradient(180deg, rgba(29,39,71,.55) 0%, rgba(11,16,32,.85) 100%);
    box-shadow: 0 0 0 1px rgba(251,113,133,.12), 0 12px 40px -16px rgba(251,113,133,.3);
}
.card-hot:hover {
    border-color: rgba(251,113,133,.6);
    box-shadow: 0 0 0 1px rgba(251,113,133,.25), 0 16px 56px -16px rgba(251,113,133,.5);
}
.card-warm {
    border-color: rgba(251,191,36,.3);
    background:
        linear-gradient(135deg, rgba(251,191,36,.05) 0%, transparent 60%),
        linear-gradient(180deg, rgba(29,39,71,.55) 0%, rgba(11,16,32,.85) 100%);
}

/* ──── Badges ──────────────────────────────────────────────────────────── */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: .62rem;
    font-weight: 800;
    letter-spacing: .8px;
    text-transform: uppercase;
    margin-right: 5px;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    transition: transform .15s;
}
.badge:hover { transform: scale(1.04); }
.badge-hot {
    background: linear-gradient(135deg, rgba(251,113,133,.18), rgba(244,63,94,.12));
    color: #fb7185;
    border: 1px solid rgba(251,113,133,.35);
    box-shadow: 0 0 12px -2px rgba(251,113,133,.4);
    animation: glowPulse 2.4s ease-in-out infinite;
}
.badge-warm {
    background: linear-gradient(135deg, rgba(251,191,36,.18), rgba(245,158,11,.1));
    color: #fbbf24;
    border: 1px solid rgba(251,191,36,.3);
}
.badge-cold {
    background: linear-gradient(135deg, rgba(56,189,248,.14), rgba(99,102,241,.1));
    color: #38bdf8;
    border: 1px solid rgba(56,189,248,.25);
}
.badge-owner {
    background: linear-gradient(135deg, rgba(221,194,105,.16), rgba(168,134,26,.08));
    color: #ddc269;
    border: 1px solid rgba(221,194,105,.3);
}
.badge-drop {
    background: linear-gradient(135deg, rgba(249,115,22,.18), rgba(234,88,12,.08));
    color: #fb923c;
    border: 1px solid rgba(249,115,22,.3);
    box-shadow: 0 0 14px -3px rgba(249,115,22,.45);
}
.badge-demo {
    background: rgba(148,163,184,.07);
    color: var(--dust);
    border: 1px solid rgba(148,163,184,.12);
    font-size: .56rem;
    letter-spacing: .4px;
}
.card-demo {
    opacity: .65;
    border-color: rgba(148,163,184,.1) !important;
}
.badge-phone {
    background: linear-gradient(135deg, rgba(221,194,105,.16), rgba(168,134,26,.08));
    color: #ddc269;
    border: 1px solid rgba(221,194,105,.3);
}
.badge-email {
    background: linear-gradient(135deg, rgba(56,189,248,.16), rgba(14,165,233,.08));
    color: #38bdf8;
    border: 1px solid rgba(56,189,248,.3);
}
.badge-nocontact {
    background: rgba(239,68,68,.06);
    color: #f87171;
    border: 1px solid rgba(239,68,68,.18);
}

/* ──── Score orb ───────────────────────────────────────────────────────── */
.score-orb {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 56px; height: 56px;
    border-radius: 50%;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.05rem;
    font-weight: 700;
    flex-shrink: 0;
    position: relative;
    transition: transform .25s, box-shadow .25s;
}
.score-orb::before {
    content: "";
    position: absolute; inset: -2px;
    border-radius: 50%;
    background: var(--grad-primary);
    z-index: -1;
    opacity: .4;
    filter: blur(8px);
    transition: opacity .3s;
}
.score-orb:hover { transform: scale(1.06); }
.score-orb:hover::before { opacity: .8; }
.orb-hot {
    background: rgba(251,113,133,.12);
    color: #fb7185;
    border: 2px solid rgba(251,113,133,.4);
    box-shadow: 0 4px 20px -4px rgba(251,113,133,.4);
}
.orb-hot::before { background: var(--grad-hot); }
.orb-warm {
    background: rgba(251,191,36,.12);
    color: #fbbf24;
    border: 2px solid rgba(251,191,36,.35);
    box-shadow: 0 4px 20px -4px rgba(251,191,36,.35);
}
.orb-warm::before { background: var(--grad-warm); }
.orb-cold {
    background: rgba(56,189,248,.1);
    color: #38bdf8;
    border: 2px solid rgba(56,189,248,.3);
    box-shadow: 0 4px 20px -4px rgba(56,189,248,.3);
}
.orb-cold::before { background: var(--grad-cold); }

/* ──── Chips ───────────────────────────────────────────────────────────── */
.chip {
    display: inline-block;
    background: rgba(29,39,71,.5);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 7px;
    padding: 3px 10px;
    font-size: .73rem;
    color: var(--fog);
    margin-right: 5px;
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    transition: all .15s;
}
.chip:hover {
    border-color: rgba(255,255,255,.15);
    color: var(--ice);
}

/* ──── Price typography — editorial Fraunces italic for that auction-house feel ─── */
.price {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 36, "SOFT" 60;
    font-size: 1.42rem;
    font-weight: 380;
    color: var(--ice);
    letter-spacing: -.01em;
    font-feature-settings: "lnum","tnum";
    background: linear-gradient(180deg, var(--mint-l) 0%, var(--mint) 70%, var(--mint-d) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
}
.delta-pos {
    font-size: .72rem;
    font-weight: 700;
    color: var(--mint);
    background: rgba(221,194,105,.08);
    padding: 2px 7px;
    border-radius: 5px;
}
.delta-neg {
    font-size: .72rem;
    font-weight: 700;
    color: var(--rose);
    background: rgba(251,113,133,.08);
    padding: 2px 7px;
    border-radius: 5px;
}

.lbl-section {
    font-family: 'Space Grotesk', sans-serif;
    font-size: .65rem;
    font-weight: 600;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    color: var(--slate);
    margin-bottom: 10px;
}

/* ──── Kanban ──────────────────────────────────────────────────────────── */
.kanban-card {
    background:
        linear-gradient(180deg, rgba(29,39,71,.45) 0%, rgba(11,16,32,.7) 100%);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 11px;
    padding: 14px 16px;
    transition: transform .2s, border-color .2s;
    cursor: pointer;
}
.kanban-card:hover {
    transform: translateY(-2px);
    border-color: rgba(221,194,105,.25);
    box-shadow: 0 8px 24px -10px rgba(221,194,105,.25);
}

.activity-row {
    display: flex;
    gap: 12px;
    padding: 12px 0;
    border-bottom: 1px solid rgba(255,255,255,.04);
    font-size: .82rem;
    color: var(--fog);
    transition: background .2s, padding-left .2s;
}
.activity-row:hover {
    background: rgba(221,194,105,.04);
    padding-left: 8px;
}

/* ──── Intel boxes (KPI tiles) ─────────────────────────────────────────── */
.intel-box {
    background:
        linear-gradient(180deg, rgba(29,39,71,.5) 0%, rgba(11,16,32,.8) 100%);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
    transition: all .25s;
    position: relative;
    overflow: hidden;
}
.intel-box::before {
    content: "";
    position: absolute;
    top: 0; left: 0; height: 2px; width: 100%;
    background: var(--grad-primary);
    opacity: 0;
    transition: opacity .3s;
}
.intel-box:hover {
    transform: translateY(-1px);
    border-color: rgba(221,194,105,.3);
}
.intel-box:hover::before { opacity: 1; }
.intel-lbl {
    font-family: 'Space Grotesk', sans-serif;
    font-size: .62rem;
    font-weight: 600;
    color: var(--slate);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
}
.intel-val {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.32rem;
    font-weight: 700;
    color: var(--ice);
    letter-spacing: -.025em;
}

/* ──── Alerts ──────────────────────────────────────────────────────────── */
.alert-card {
    display: flex;
    gap: 12px;
    background:
        linear-gradient(90deg, rgba(29,39,71,.55) 0%, rgba(11,16,32,.4) 100%);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,.06);
    border-left: 3px solid var(--sky);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    font-size: .82rem;
    color: var(--fog);
    transition: transform .2s, border-color .2s;
}
.alert-card:hover {
    transform: translateX(2px);
}
.alert-hot  {
    border-left-color: var(--rose);
    background: linear-gradient(90deg, rgba(251,113,133,.08) 0%, transparent 50%);
}
.alert-warm {
    border-left-color: var(--amber);
    background: linear-gradient(90deg, rgba(251,191,36,.06) 0%, transparent 50%);
}
.alert-grn  {
    border-left-color: var(--mint);
    background: linear-gradient(90deg, rgba(221,194,105,.06) 0%, transparent 50%);
}

/* ──── Pipeline / funnel steps ─────────────────────────────────────────── */
.pf-wrap {
    display: flex;
    gap: 0;
    background:
        linear-gradient(180deg, rgba(29,39,71,.4) 0%, rgba(11,16,32,.7) 100%);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 22px;
    box-shadow: var(--shadow-card);
}
.pf-step {
    flex: 1;
    padding: 18px 14px;
    font-size: .78rem;
    color: var(--smoke);
    border-right: 1px solid rgba(255,255,255,.04);
    transition: background .25s;
}
.pf-step:last-child { border-right: none; }
.pf-step:hover {
    background: rgba(221,194,105,.04);
}
.pf-step-active {
    background: linear-gradient(180deg, rgba(221,194,105,.08) 0%, rgba(56,189,248,.05) 100%);
    box-shadow: inset 0 -2px 0 var(--mint);
}
.pf-icon {
    font-size: 1.4rem;
    display: block;
    margin-bottom: 8px;
    filter: drop-shadow(0 0 8px currentColor);
}
.pf-n {
    font-family: 'Space Grotesk', sans-serif;
    font-size: .58rem;
    font-weight: 600;
    color: var(--slate);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 3px;
}
.pf-name {
    font-size: .82rem;
    font-weight: 700;
    color: var(--fog);
    margin-bottom: 4px;
}
.pf-desc {
    font-size: .68rem;
    color: var(--dust);
    line-height: 1.45;
}

/* ──── Source bars ─────────────────────────────────────────────────────── */
.src-bar-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 7px 0;
}
.src-bar-name {
    font-family: 'Space Grotesk', sans-serif;
    font-size: .78rem;
    font-weight: 600;
    color: var(--fog);
    width: 90px;
    flex-shrink: 0;
}
.src-bar-track {
    flex: 1;
    background: rgba(11,16,32,.7);
    border-radius: 6px;
    height: 8px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,.04);
}
.src-bar-fill {
    height: 8px;
    border-radius: 5px;
    background: var(--grad-primary);
    box-shadow: 0 0 10px -2px rgba(221,194,105,.5);
    background-size: 200% 100%;
    animation: shimmer 4s linear infinite;
}
.src-bar-count {
    font-family: 'Space Grotesk', sans-serif;
    font-size: .8rem;
    font-weight: 700;
    color: var(--fog);
    width: 32px;
    text-align: right;
}

/* ──── Brand mark ──────────────────────────────────────────────────────── */
.patabrava-mark {
    padding: 16px 0 12px;
    margin-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,.05);
}
.patabrava-logo-img {
    display: block;
    width: 100%;
    max-width: 180px;
    height: auto;
    margin: 2px 0 10px;
    filter: drop-shadow(0 4px 16px rgba(221,194,105,.25));
    transition: filter .3s ease, transform .3s ease;
}
.patabrava-logo-img:hover {
    filter: drop-shadow(0 6px 20px rgba(221,194,105,.45));
    transform: translateY(-1px);
}
.patabrava-logo {
    width: 38px; height: 38px;
    border-radius: 11px;
    background: var(--grad-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #052016;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.1rem;
    font-weight: 800;
    box-shadow:
        0 6px 20px -6px rgba(221,194,105,.6),
        inset 0 -1px 2px rgba(0,0,0,.2);
    flex-shrink: 0;
    position: relative;
}
.patabrava-logo::after {
    content: "";
    position: absolute; inset: 2px;
    border-radius: 9px;
    background: linear-gradient(135deg, rgba(255,255,255,.2), transparent 50%);
    pointer-events: none;
}
.patabrava-name {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--ice);
    letter-spacing: -.01em;
    line-height: 1.1;
}
.patabrava-tag {
    font-size: .68rem;
    color: var(--smoke);
    margin-top: 2px;
    letter-spacing: .4px;
}
.patabrava-version {
    display: inline-block;
    margin-top: 6px;
    padding: 2px 8px;
    background: rgba(221,194,105,.1);
    border: 1px solid rgba(221,194,105,.25);
    border-radius: 999px;
    font-size: .58rem;
    font-weight: 700;
    color: var(--mint);
    letter-spacing: .8px;
    text-transform: uppercase;
}

/* ──── Hero header on main page ────────────────────────────────────────── */
.hero {
    position: relative;
    padding: 28px 32px;
    border-radius: 20px;
    background:
        radial-gradient(600px 320px at 0% 0%, rgba(221,194,105,.12), transparent 60%),
        radial-gradient(600px 320px at 100% 100%, rgba(198, 162, 100,.1), transparent 60%),
        linear-gradient(135deg, rgba(29,39,71,.7) 0%, rgba(11,16,32,.9) 100%);
    backdrop-filter: blur(16px) saturate(140%);
    -webkit-backdrop-filter: blur(16px) saturate(140%);
    border: 1px solid rgba(255,255,255,.07);
    box-shadow: var(--shadow-card);
    margin-bottom: 24px;
    overflow: hidden;
}
.hero::before {
    content: "";
    position: absolute;
    top: -2px; left: 0; right: 0; height: 2px;
    background: var(--grad-primary);
    background-size: 200% 100%;
    animation: shimmer 6s linear infinite;
}
.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--ice);
    letter-spacing: -.025em;
    margin-bottom: 6px;
}
.hero-title-accent {
    background: var(--grad-primary);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-sub {
    font-size: .9rem;
    color: var(--smoke);
    line-height: 1.5;
}

/* ════════════════════════════════════════════════════════════════════════ */
/*  MAISON — editorial luxury hero                                          */
/*  Used on the main Dashboard page. Conceptually: a magazine "spread"     */
/*  with a dominant numeral kicker, eyebrow tracked-out small caps, italic */
/*  Fraunces sub-line, and three secondary numerals as supporting facts.   */
/* ════════════════════════════════════════════════════════════════════════ */
.maison {
    position: relative;
    padding: var(--sp-6) var(--sp-6) var(--sp-5);
    margin: var(--sp-3) 0 var(--sp-6);
    isolation: isolate;
    overflow: hidden;
    border-top:    1px solid rgba(221,194,105,.35);
    border-bottom: 1px solid rgba(221,194,105,.18);
    background:
        radial-gradient(900px 480px at 88% -20%, rgba(221,194,105,.10), transparent 65%),
        radial-gradient(700px 380px at -10% 110%, rgba(168,134,26,.08), transparent 70%),
        linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
    /* film-grain noise */
}
.maison::before {
    /* Vertical hairline left — auction-catalogue marker */
    content: "";
    position: absolute;
    left: 0; top: 18%; bottom: 18%;
    width: 1px;
    background: linear-gradient(180deg, transparent 0%, var(--mint) 50%, transparent 100%);
    opacity: .55;
}
.maison::after {
    /* Subtle grain to break the flat dark background */
    content: "";
    position: absolute; inset: 0;
    pointer-events: none;
    opacity: .035;
    mix-blend-mode: overlay;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 .85 0 0 0 0 .55 0 0 0 .9 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

.maison-grid {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
    gap: var(--sp-5) var(--sp-6);
    align-items: end;
}
@media (max-width: 900px) {
    .maison-grid { grid-template-columns: 1fr; }
}

.maison-eyebrow {
    font-family: var(--font-body);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: var(--mint);
    margin-bottom: var(--sp-3);
    display: flex;
    align-items: center;
    gap: 10px;
}
.maison-eyebrow::before {
    content: "";
    display: inline-block;
    width: 22px; height: 1px;
    background: var(--mint);
    opacity: .9;
}
.maison-title {
    font-family: var(--font-display);
    font-optical-sizing: auto;
    font-variation-settings: "opsz" 144, "SOFT" 40;
    font-weight: 380;
    font-size: clamp(38px, 5.6vw, 78px);
    line-height: .96;
    letter-spacing: -0.022em;
    color: var(--ice);
    margin: 0 0 var(--sp-3) 0;
}
.maison-title em {
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 100;
    font-weight: 320;
    color: var(--mint-l);
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
}
.maison-deck {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 32, "SOFT" 60;
    font-weight: 320;
    font-size: clamp(15px, 1.5vw, 19px);
    line-height: 1.5;
    color: var(--fog);
    max-width: 56ch;
    margin: var(--sp-3) 0 var(--sp-2);
}
.maison-byline {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 500;
    letter-spacing: .22em;
    text-transform: uppercase;
    color: var(--slate);
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    flex-wrap: wrap;
    margin-top: var(--sp-4);
}
.maison-byline > span:not(:last-child)::after {
    content: "·";
    margin-left: var(--sp-3);
    color: var(--mint);
    opacity: .7;
}

/* Numeral block — dominant figure on the right */
.maison-numerals {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-4);
}
.maison-figure {
    display: grid;
    grid-template-columns: auto 1fr;
    align-items: end;
    gap: var(--sp-4);
    padding-bottom: var(--sp-3);
    border-bottom: 1px solid rgba(221,194,105,.18);
    width: 100%;
}
.maison-figure-num {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 0;
    font-weight: 280;
    font-size: var(--num-xxl);
    line-height: .82;
    letter-spacing: -0.04em;
    color: var(--ice);
    font-feature-settings: "lnum", "tnum";
}
.maison-figure-num.is-hot {
    background: linear-gradient(180deg, #ffe6c2 0%, #ddc269 55%, #a8861a 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* Shimmer sweep — polished gold engraving feel on key numerals.
   A diagonal highlight band passes through the gradient text once
   every 6 seconds, slow and theatrical (not blinking-disco). */
.has-shimmer {
    background:
        linear-gradient(
            115deg,
            #a8861a 0%,
            #ddc269 25%,
            #ffe6c2 45%,
            #ffffff 50%,
            #ffe6c2 55%,
            #ddc269 75%,
            #a8861a 100%
        );
    background-size: 240% 100%;
    background-position: 100% 0;
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: gold-sweep 6.5s cubic-bezier(.4, 0, .2, 1) infinite;
}
@keyframes gold-sweep {
    0%, 60% { background-position: 100% 0; }
    100%    { background-position: -120% 0; }
}
@media (prefers-reduced-motion: reduce) {
    .has-shimmer { animation: none; background-position: 50% 0; }
}
.maison-figure-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-bottom: 12px;
}
.maison-figure-lbl {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--smoke);
}
.maison-figure-sub {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 14;
    font-weight: 300;
    font-size: 14px;
    color: var(--fog);
    margin-top: 2px;
}

.maison-stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--sp-3) var(--sp-5);
    width: 100%;
    padding-top: var(--sp-2);
}
.maison-stat-num {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 72, "SOFT" 0;
    font-weight: 320;
    font-size: var(--num-lg);
    line-height: 1;
    letter-spacing: -0.02em;
    color: var(--ice);
    font-feature-settings: "lnum","tnum";
}
.maison-stat-num.is-warm  { color: var(--amber); }
.maison-stat-num.is-rose  { color: var(--rose); }
.maison-stat-num.is-mint  { color: var(--mint); }
.maison-stat-lbl {
    font-family: var(--font-body);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--slate);
    margin-top: 4px;
}

/* Page-load orchestration — staggered reveals on the maison */
@keyframes maison-rise {
    0%   { opacity: 0; transform: translateY(14px); filter: blur(4px); }
    100% { opacity: 1; transform: translateY(0);    filter: blur(0); }
}
.maison-eyebrow,
.maison-title,
.maison-deck,
.maison-byline,
.maison-figure,
.maison-stats {
    opacity: 0;
    animation: maison-rise .9s cubic-bezier(.2,.7,.2,1) forwards;
}
.maison-eyebrow { animation-delay: 80ms; }
.maison-title   { animation-delay: 160ms; }
.maison-deck    { animation-delay: 240ms; }
.maison-figure  { animation-delay: 320ms; }
.maison-stats   { animation-delay: 400ms; }
.maison-byline  { animation-delay: 480ms; }

/* Section marker — roman numeral plate, used between the maison and the data view */
.section-marker {
    display: flex;
    align-items: center;
    gap: var(--sp-4);
    margin: var(--sp-6) 0 var(--sp-4);
    padding: 0 var(--sp-2);
}
.section-marker__num {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 32;
    font-weight: 300;
    font-size: 18px;
    color: var(--ink-00);
    letter-spacing: .04em;
    min-width: 36px;
    height: 36px;
    padding: 0 12px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    border-radius: 999px;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.4),
        0 4px 16px -4px rgba(221,194,105,.5);
    text-shadow: 0 1px 0 rgba(255,255,255,.25);
    font-weight: 600;
}
.section-marker__title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 24, "SOFT" 30;
    font-weight: 400;
    font-size: 22px;
    color: var(--ice);
    letter-spacing: -.012em;
    flex: 0 0 auto;
}
.section-marker__rule {
    flex: 1;
    height: 1px;
    position: relative;
    background: linear-gradient(90deg, rgba(221,194,105,.55) 0%, rgba(221,194,105,0) 100%);
}
.section-marker__rule::before {
    /* parallel hairline above for double-rule effect */
    content: "";
    position: absolute;
    left: 0; right: 30%;
    bottom: 5px;
    height: 1px;
    background: linear-gradient(90deg, rgba(221,194,105,.22) 0%, rgba(221,194,105,0) 100%);
}
.section-marker__fleuron {
    font-family: var(--font-display);
    font-style: italic;
    font-size: 22px;
    color: var(--mint);
    line-height: 1;
    margin: 0 -2px;
    opacity: .85;
}
.section-marker__caption {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .22em;
    text-transform: uppercase;
    color: var(--slate);
}

/* ──── Maison MINI — compact editorial hero for sub-pages ───────────────── */
.maison--mini {
    position: relative;
    padding: var(--sp-5) var(--sp-5) var(--sp-4);
    margin: var(--sp-2) 0 var(--sp-5);
    overflow: hidden;
    border-top:    1px solid rgba(221,194,105,.32);
    border-bottom: 1px solid rgba(221,194,105,.14);
    background:
        radial-gradient(700px 320px at 95% -30%, rgba(221,194,105,.08), transparent 70%),
        linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
}
.maison--mini::before {
    content: "";
    position: absolute;
    left: 0; top: 22%; bottom: 22%;
    width: 1px;
    background: linear-gradient(180deg, transparent 0%, var(--mint) 50%, transparent 100%);
    opacity: .5;
}
.maison--mini .maison-eyebrow {
    margin-bottom: var(--sp-2);
}
.maison--mini .maison-title {
    font-size: clamp(28px, 3.6vw, 44px);
    margin-bottom: var(--sp-2);
}
.maison--mini .maison-deck {
    font-size: clamp(14px, 1.2vw, 16px);
    margin-top: var(--sp-2);
    max-width: 72ch;
}
.maison--mini .maison-byline {
    margin-top: var(--sp-3);
}
.maison--mini .maison-eyebrow,
.maison--mini .maison-title,
.maison--mini .maison-deck,
.maison--mini .maison-byline { animation-duration: .7s; }

/* ──── Maison watermark + double-rule + drop cap upgrades ────────────────── */
.maison-watermark {
    position: absolute;
    inset: 0;
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    overflow: hidden;
    z-index: 0;
    padding-right: 4%;
}
.maison-watermark__text {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 80;
    font-weight: 200;
    font-size: clamp(140px, 20vw, 280px);
    line-height: .8;
    letter-spacing: -0.05em;
    color: var(--mint);
    opacity: .035;
    user-select: none;
    white-space: nowrap;
}

.maison-rule-top,
.maison-rule-bot {
    position: absolute; left: 0; right: 0;
    height: 8px;
    pointer-events: none;
    z-index: 2;
}
.maison-rule-top { top: 0; }
.maison-rule-bot { bottom: 0; }
.maison-rule-top::before,
.maison-rule-top::after,
.maison-rule-bot::before,
.maison-rule-bot::after {
    content: "";
    position: absolute; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(221,194,105,.55) 12%,
        var(--mint) 50%,
        rgba(221,194,105,.55) 88%,
        transparent 100%);
}
.maison-rule-top::before { top: 0; opacity: .9; }
.maison-rule-top::after  { top: 4px; opacity: .35; }
.maison-rule-bot::before { bottom: 4px; opacity: .35; }
.maison-rule-bot::after  { bottom: 0; opacity: .9; }

/* Asterism ornament between figure and supporting stats */
.maison-asterism {
    display: flex;
    align-items: center;
    justify-content: center;
    margin: var(--sp-2) 0;
    padding: 4px 0;
    color: var(--mint);
    opacity: .55;
    font-family: var(--font-display);
    font-size: 16px;
    letter-spacing: .8em;
    user-select: none;
}

/* Editorial drop cap — used on .maison-deck when wrapped with .has-dropcap */
.maison-deck.has-dropcap::first-letter {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 80;
    font-weight: 320;
    float: left;
    font-size: 4.4em;
    line-height: .85;
    padding: .12em .14em 0 0;
    margin-right: .04em;
    background: linear-gradient(180deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* ──── Smooth scroll + skeleton shimmer for loading states ──────────────── */
html { scroll-behavior: smooth; }

.skeleton {
    background: linear-gradient(
        90deg,
        rgba(221,194,105,.04) 0%,
        rgba(221,194,105,.10) 35%,
        rgba(238,218,160,.18) 50%,
        rgba(221,194,105,.10) 65%,
        rgba(221,194,105,.04) 100%
    );
    background-size: 220% 100%;
    border-radius: 8px;
    animation: skeleton-sweep 1.4s cubic-bezier(.4,0,.2,1) infinite;
}
.skeleton--line {
    height: 14px;
    margin: 6px 0;
}
.skeleton--big   { height: 36px; }
.skeleton--block { height: 96px; border-radius: 14px; }
@keyframes skeleton-sweep {
    from { background-position: 100% 0; }
    to   { background-position: -120% 0; }
}

/* ════════════════════════════════════════════════════════════════════════ */
/*  PRINT STYLESHEET                                                         */
/*  When the operator prints (or saves to PDF) a page, strip the dashboard  */
/*  chrome and keep only the editorial content — turn it into a clean       */
/*  magazine page printable on A4.                                          */
/* ════════════════════════════════════════════════════════════════════════ */
@media print {
    /* Reset to paper-friendly background */
    :root {
        --ink-00: #ffffff;
        --ink-10: #ffffff;
        --ink-20: #f8f4ea;
        --ink-30: #ece4d3;
        --ice:   #1a1106;
        --fog:   #2a2010;
        --smoke: #5c5240;
        --slate: #786c52;
        --dust:  #a89c80;
    }
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    .main,
    body {
        background: #ffffff !important;
        color: #1a1106 !important;
    }
    /* Hide everything that's not editorial content */
    [data-testid="stSidebar"],
    [data-testid="stToolbar"],
    [data-testid="stHeader"],
    .stDeployButton,
    .stButton,
    .dust,
    .stTextInput,
    .stSelectbox,
    .stMultiSelect,
    .stCheckbox,
    .stRadio,
    .stSlider,
    .stExpander summary svg,
    .stTabs [role="tablist"] { display: none !important; }

    /* Maison hero — paper variant: keep the typography, drop the dark glow */
    .maison,
    .maison--mini,
    .lot-page,
    .card,
    .lot {
        background: #ffffff !important;
        border: none !important;
        box-shadow: none !important;
        page-break-inside: avoid;
        backdrop-filter: none !important;
        padding: 16px 0 !important;
    }
    .maison-watermark { display: none !important; }
    .maison-rule-top, .maison-rule-bot,
    .lot-page__rule {
        background: transparent !important;
    }
    .maison-rule-top::before,
    .maison-rule-top::after,
    .maison-rule-bot::before,
    .maison-rule-bot::after,
    .lot-page__rule {
        background: linear-gradient(90deg, transparent, #c2a84b 30%, #c2a84b 70%, transparent) !important;
        opacity: 1 !important;
    }
    /* Gold gradients become deep gold ink on paper */
    .has-shimmer,
    .maison-figure-num.is-hot,
    .lot-page__price,
    .price,
    .hero-title-accent {
        background: none !important;
        -webkit-text-fill-color: #b89030 !important;
        color: #b89030 !important;
        animation: none !important;
    }
    .maison-eyebrow,
    .lot-page__eyebrow,
    .section-marker__caption,
    .maison-byline,
    .maison-stat-lbl,
    .maison-figure-lbl {
        color: #5c5240 !important;
    }
    .section-marker__num {
        background: #b89030 !important;
        color: #ffffff !important;
        text-shadow: none !important;
        box-shadow: none !important;
    }
    .lot-cta__call {
        background: none !important;
        border: 1px solid #b89030 !important;
        color: #b89030 !important;
        box-shadow: none !important;
    }
    .lot-page__title,
    .maison-title,
    .lot-title,
    .section-marker__title {
        color: #1a1106 !important;
    }
    .lot::before { color: #5c5240 !important; }
    .lot::after  { display: none !important; }

    .maison-footer {
        margin-top: 32px !important;
        border-top: 1px solid #c2a84b !important;
    }
    .maison-footer__mark,
    .maison-footer__row,
    .maison-footer__addr {
        color: #1a1106 !important;
    }
    .maison-footer__row > span:not(:last-child)::after {
        color: #b89030 !important;
    }

    /* Page break hints */
    .section-marker { page-break-before: avoid; page-break-after: avoid; }
    h1, h2, h3 { page-break-after: avoid; }
    article, section { page-break-inside: avoid; }

    @page {
        size: A4;
        margin: 18mm 20mm 22mm 20mm;
    }
}

/* ──── Lot page — magazine spread header for a single lead detail ───────── */
.lot-page {
    margin: var(--sp-3) 0 var(--sp-4);
    padding: var(--sp-4) var(--sp-5);
    background:
        linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
    border-top: 1px solid rgba(221,194,105,.32);
    border-bottom: 1px solid rgba(221,194,105,.14);
    position: relative;
    overflow: hidden;
}
.lot-page::before {
    content: "";
    position: absolute;
    top: 0; left: 0; bottom: 0;
    width: 2px;
    background: linear-gradient(180deg, transparent 0%, var(--mint) 50%, transparent 100%);
}
.lot-page__eyebrow {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .28em;
    text-transform: uppercase;
    color: var(--mint);
    margin-bottom: var(--sp-2);
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    flex-wrap: wrap;
}
.lot-page__sep { opacity: .6; color: var(--smoke); margin: 0 -2px; }
.lot-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: .22em;
    margin-left: var(--sp-2);
}
.lot-chip--fsbo {
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 100%);
    color: var(--ink-00);
    box-shadow: 0 4px 14px -4px rgba(221,194,105,.5);
}
.lot-chip--agency {
    background: rgba(168,134,26,.12);
    color: var(--mint-d);
    border: 1px solid rgba(168,134,26,.3);
}
.lot-page__title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 32, "SOFT" 30;
    font-weight: 420;
    font-size: clamp(20px, 2.4vw, 28px);
    color: var(--ice);
    letter-spacing: -0.012em;
    line-height: 1.25;
    margin-bottom: var(--sp-3);
    max-width: 60ch;
}
.lot-page__row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--sp-5);
    flex-wrap: wrap;
    margin-bottom: var(--sp-3);
}
.lot-page__price {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 80;
    font-weight: 320;
    font-size: clamp(36px, 4.2vw, 56px);
    line-height: 1;
    letter-spacing: -.02em;
    background: linear-gradient(180deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
    font-feature-settings: "lnum","tnum";
}
.lot-spec {
    font-family: var(--font-body);
    font-size: 12.5px;
    font-weight: 500;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--smoke);
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-2);
}
.lot-spec b {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 480;
    font-size: 1.4em;
    text-transform: none;
    letter-spacing: 0;
    color: var(--ice);
    margin-right: 2px;
}
.lot-page__rule {
    height: 1px;
    margin: var(--sp-3) 0 var(--sp-4);
    background: linear-gradient(90deg, var(--mint) 0%, transparent 70%);
    opacity: .4;
}
.lot-cta {
    display: flex;
    gap: var(--sp-3);
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: var(--sp-3);
}
.lot-cta__call {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 18px;
    border-radius: 999px;
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    color: var(--ink-00) !important;
    font-family: var(--font-body);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: .04em;
    text-decoration: none !important;
    border: none !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.4),
        0 8px 22px -8px rgba(221,194,105,.6);
    transition: transform .2s, box-shadow .2s;
}
.lot-cta__call:hover {
    transform: translateY(-1px);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.5),
        0 12px 30px -8px rgba(221,194,105,.85);
}
.lot-cta__wa {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 9px 14px;
    color: var(--mint-l) !important;
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 14;
    font-size: 13.5px;
    text-decoration: none !important;
    border-bottom: 1px dotted rgba(221,194,105,.5) !important;
    transition: color .2s, border-color .2s;
}
.lot-cta__wa:hover {
    color: var(--ice) !important;
    border-bottom-color: var(--mint) !important;
}
.lot-page__source {
    font-family: var(--font-mono);
    font-size: 9.5px;
    font-weight: 500;
    letter-spacing: .28em;
    color: var(--slate);
    text-transform: uppercase;
}

/* ──── Editorial footer — appears once at the bottom of every page ───────── */
.maison-footer {
    margin: var(--sp-7) auto var(--sp-5);
    padding: var(--sp-5) var(--sp-4) var(--sp-3);
    text-align: center;
    border-top: 1px solid rgba(221,194,105,.18);
    position: relative;
}
.maison-footer::before {
    /* parallel hairline above for double-rule effect */
    content: "";
    position: absolute;
    left: 30%; right: 30%;
    top: -5px;
    height: 1px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(221,194,105,.45) 50%, transparent 100%);
}
.maison-footer__mark {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 32, "SOFT" 80;
    font-weight: 320;
    font-size: 22px;
    line-height: 1;
    color: var(--mint);
    letter-spacing: -.01em;
    margin-bottom: var(--sp-3);
}
.maison-footer__row {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: var(--slate);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-3);
    flex-wrap: wrap;
    margin-bottom: var(--sp-3);
}
.maison-footer__row > span:not(:last-child)::after {
    content: "·";
    margin-left: var(--sp-3);
    color: var(--mint);
    opacity: .8;
}
.maison-footer__addr {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 14;
    font-weight: 320;
    font-size: 12.5px;
    color: var(--smoke);
    letter-spacing: .01em;
    line-height: 1.55;
    max-width: 60ch;
    margin: 0 auto;
}

/* ──── Ambient gold dust — slow CSS-only floating particles ──────────────── */
/*
 *  Six gold motes drift across the viewport in independent loops. Pure CSS
 *  (no JS), low opacity, mix-blend-mode "screen" so they only brighten
 *  pixels they pass over — they never look like dirt on a screen.
 *  Sits above background but below content (z-index 0 vs default static).
 */
.dust {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
}
.dust__mote {
    position: absolute;
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: radial-gradient(circle, var(--mint-l) 0%, var(--mint) 45%, transparent 70%);
    opacity: 0;
    mix-blend-mode: screen;
    filter: blur(.4px);
    will-change: transform, opacity;
}
@keyframes dust-drift-a {
    0%   { transform: translate(0, 100vh) scale(.6); opacity: 0; }
    8%   { opacity: .55; }
    50%  { transform: translate(40px, 50vh) scale(1); opacity: .8; }
    92%  { opacity: .35; }
    100% { transform: translate(-25px, -8vh) scale(.7); opacity: 0; }
}
@keyframes dust-drift-b {
    0%   { transform: translate(0, 100vh) scale(.5); opacity: 0; }
    10%  { opacity: .4; }
    50%  { transform: translate(-60px, 45vh) scale(.9); opacity: .7; }
    90%  { opacity: .3; }
    100% { transform: translate(20px, -10vh) scale(.5); opacity: 0; }
}
.dust__mote:nth-child(1) { left:  8%;  width: 3px; height: 3px; animation: dust-drift-a 38s linear infinite;        animation-delay: 0s;   }
.dust__mote:nth-child(2) { left: 22%;  width: 5px; height: 5px; animation: dust-drift-b 44s linear infinite;        animation-delay: 6s;   }
.dust__mote:nth-child(3) { left: 41%;  width: 2px; height: 2px; animation: dust-drift-a 32s linear infinite;        animation-delay: 14s;  }
.dust__mote:nth-child(4) { left: 58%;  width: 4px; height: 4px; animation: dust-drift-b 50s linear infinite;        animation-delay: 22s;  }
.dust__mote:nth-child(5) { left: 73%;  width: 3px; height: 3px; animation: dust-drift-a 41s linear infinite;        animation-delay: 9s;   }
.dust__mote:nth-child(6) { left: 88%;  width: 5px; height: 5px; animation: dust-drift-b 36s linear infinite;        animation-delay: 18s;  }

@media (prefers-reduced-motion: reduce) {
    .dust__mote { animation: none !important; opacity: 0 !important; }
}

/* ──── Editorial polish: selection, scrollbar, focus rings ──────────────── */
::selection {
    background: rgba(221,194,105,.32);
    color: var(--ice);
    text-shadow: none;
}
* {
    scrollbar-width: thin;
    scrollbar-color: rgba(221,194,105,.3) transparent;
}
*::-webkit-scrollbar { width: 8px; height: 8px; }
*::-webkit-scrollbar-track { background: transparent; }
*::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, rgba(221,194,105,.45) 0%, rgba(168,134,26,.45) 100%);
    border-radius: 999px;
    border: 2px solid transparent;
    background-clip: padding-box;
}
*::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--mint-l) 0%, var(--mint) 100%);
    background-clip: padding-box;
}

/* ──── Sidebar network-status widget ──────────────────────────────────── */
.net-card {
    margin: 6px 0 10px;
    padding: var(--sp-3) var(--sp-3);
    background: linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
    border: 1px solid rgba(221,194,105,.14);
    border-radius: 10px;
    font-family: var(--font-body);
}
.net-card__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 8px;
}
.net-card__title {
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--smoke);
}
.net-pill {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: .14em;
    padding: 3px 8px;
    border-radius: 999px;
    line-height: 1;
}
.net-pill--ok {
    background: rgba(86,175,116,.15);
    color: #86d4a8;
    border: 1px solid rgba(86,175,116,.4);
}
.net-pill--err {
    background: rgba(251,113,133,.15);
    color: #fbb1bc;
    border: 1px solid rgba(251,113,133,.4);
}
.net-pill--warn {
    background: rgba(251,191,36,.12);
    color: #fbcf6e;
    border: 1px solid rgba(251,191,36,.35);
}
.net-card__row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 11px;
    line-height: 1.4;
    margin: 1px 0;
}
.net-card__lbl {
    color: var(--slate);
    text-transform: uppercase;
    letter-spacing: .14em;
    font-size: 9px;
    font-weight: 600;
    padding-top: 2px;
}
.net-card__val {
    color: var(--ice);
    font-family: var(--font-mono);
    font-size: 11px;
    text-align: right;
    word-break: break-word;
    max-width: 60%;
}
.net-card__kind {
    margin: 8px 0 4px;
    padding: 4px 8px;
    background: rgba(221,194,105,.06);
    border-radius: 6px;
    font-size: 10.5px;
    text-align: center;
    color: var(--mint-l);
    letter-spacing: .04em;
}
.net-card__portals-lbl {
    margin-top: 6px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--slate);
}
.net-card__portals {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-top: 4px;
}
.net-portal {
    display: inline-block;
    font-family: var(--font-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: .04em;
    padding: 2px 7px;
    border-radius: 999px;
    border: 1px solid transparent;
}
.net-portal--ok  {
    background: rgba(86,175,116,.10);
    color: #9adfb8;
    border-color: rgba(86,175,116,.35);
}
.net-portal--err {
    background: rgba(251,113,133,.10);
    color: #fbb1bc;
    border-color: rgba(251,113,133,.4);
}
.net-portal--wn  {
    background: rgba(168,156,128,.10);
    color: var(--smoke);
    border-color: rgba(168,156,128,.32);
}

.net-tip {
    margin: 4px 0 12px;
    padding: 10px 12px;
    background: linear-gradient(180deg, rgba(251,113,133,.08) 0%, rgba(20,16,8,.4) 100%);
    border-left: 2px solid var(--rose);
    border-radius: 4px 8px 8px 4px;
}
.net-tip__title {
    font-family: var(--font-display);
    font-style: italic;
    font-size: 12px;
    font-weight: 460;
    color: var(--rose);
    margin-bottom: 4px;
}
.net-tip__line {
    font-size: 10.5px;
    line-height: 1.45;
    color: var(--fog);
    padding-left: 4px;
}

/* ════════════════════════════════════════════════════════════════════════ */
/*  SCHEDULE EDITOR — section + cards on the Motor page                     */
/* ════════════════════════════════════════════════════════════════════════ */

.sched-section {
    margin: var(--sp-3) 0 var(--sp-4);
    padding: var(--sp-3) 0;
    border-top: 1px solid rgba(221,194,105,.18);
}
.sched-section__eyebrow {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: var(--mint);
    margin-bottom: 6px;
}
.sched-section__title {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 72, "SOFT" 60;
    font-weight: 320;
    font-size: clamp(22px, 2.6vw, 32px);
    line-height: 1.1;
    color: var(--ice);
    margin: 0 0 var(--sp-2);
    letter-spacing: -.014em;
}
.sched-section__deck {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 320;
    font-size: 14px;
    line-height: 1.55;
    color: var(--fog);
    max-width: 70ch;
    margin: 0 0 var(--sp-3);
}

.sched-empty {
    padding: 18px 14px;
    font-family: var(--font-display);
    font-style: italic;
    font-size: 13px;
    color: var(--smoke);
    background: rgba(20,16,8,.4);
    border-left: 2px solid var(--smoke);
    border-radius: 4px 8px 8px 4px;
}

.sched-card {
    margin: 8px 0 4px;
    padding: 14px 18px;
    border-radius: 12px;
    background: linear-gradient(180deg, rgba(20,16,8,.6) 0%, rgba(10,8,6,.85) 100%);
    border: 1px solid rgba(221,194,105,.18);
    border-left: 3px solid var(--mint);
}
.sched-card--off {
    border-left-color: var(--smoke);
    opacity: .55;
}

.sched-card__head {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 18px;
    align-items: center;
}
.sched-card__time {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 72, "SOFT" 0;
    font-weight: 360;
    font-size: clamp(28px, 3vw, 38px);
    line-height: 1;
    letter-spacing: -.02em;
    color: var(--mint-l);
    font-feature-settings: "lnum","tnum";
    min-width: 90px;
}
.sched-card--off .sched-card__time { color: var(--smoke); }

.sched-card__name {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 24, "SOFT" 30;
    font-weight: 460;
    font-size: 15px;
    color: var(--ice);
    letter-spacing: -.005em;
    margin-bottom: 2px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.sched-card__days {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--smoke);
}
.sched-card__badge {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: .14em;
    padding: 2px 7px;
    border-radius: 999px;
}
.sched-card__badge--on {
    background: rgba(86,175,116,.15);
    color: #86d4a8;
    border: 1px solid rgba(86,175,116,.4);
}
.sched-card__badge--off {
    background: rgba(168,156,128,.10);
    color: var(--smoke);
    border: 1px solid rgba(168,156,128,.32);
}

.sched-card__next-wrap {
    text-align: right;
    line-height: 1.1;
    min-width: 100px;
}
.sched-card__next-lbl {
    font-family: var(--font-body);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--slate);
    margin-bottom: 2px;
}
.sched-card__next-val {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 24;
    font-weight: 380;
    font-size: 17px;
    color: var(--mint-l);
    font-feature-settings: "lnum","tnum";
}
.sched-card__next--off .sched-card__next-val { color: var(--smoke); }

.sched-card__detail {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid rgba(221,194,105,.10);
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px 16px;
    font-family: var(--font-body);
    font-size: 11px;
}
@media (max-width: 700px) {
    .sched-card__detail { grid-template-columns: 1fr; }
}
.sched-card__lbl {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--slate);
    margin-right: 6px;
}
.sched-card__val {
    color: var(--ice);
    font-family: var(--font-mono);
    font-size: 11px;
    word-break: break-word;
}

/* ════════════════════════════════════════════════════════════════════════ */
/*  LEAD DETAIL MAGAZINE MODAL — st.dialog                                  */
/*  The moment-of-truth surface. When the agent clicks a lead card on       */
/*  Top Accionáveis, this modal opens. Layout: photo left, editorial right. */
/*  Big italic gold price, Sec-CH-UA-tier badge, WhatsApp pill gigante.     */
/* ════════════════════════════════════════════════════════════════════════ */

.dlg-photo-wrap {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(221,194,105,.18);
    background: linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
    aspect-ratio: 4/3;
    display: flex;
    align-items: center;
    justify-content: center;
}
.dlg-photo-wrap img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
}
.dlg-photo-stub {
    font-family: var(--font-display);
    font-style: italic;
    font-size: 14px;
    color: var(--smoke);
    letter-spacing: .04em;
}
.dlg-source {
    margin-top: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--font-mono);
    font-size: 9.5px;
    letter-spacing: .26em;
    text-transform: uppercase;
}
.dlg-source__lbl   { color: var(--slate); }
.dlg-source__val   { color: var(--mint-l); font-weight: 600; }
.dlg-source__link  {
    color: var(--mint) !important;
    text-decoration: none !important;
    font-family: var(--font-display);
    font-style: italic;
    font-size: 12.5px;
    letter-spacing: .02em;
    text-transform: none;
    border-bottom: 1px dotted rgba(221,194,105,.4) !important;
}
.dlg-source__link:hover { color: var(--ice) !important; }

.dlg-eyebrow {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--mint);
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.dlg-eyebrow .dlg-sep {
    color: var(--smoke);
    opacity: .6;
}
.dlg-chip {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: .22em;
    margin-left: 4px;
}
.dlg-chip--fsbo {
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 100%);
    color: var(--ink-00);
    box-shadow: 0 4px 10px -4px rgba(221,194,105,.5);
}
.dlg-chip--agency {
    background: rgba(168,134,26,.12);
    color: var(--mint-d);
    border: 1px solid rgba(168,134,26,.3);
}

.dlg-title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 32, "SOFT" 30;
    font-weight: 420;
    font-size: clamp(18px, 1.8vw, 24px);
    line-height: 1.3;
    color: var(--ice);
    letter-spacing: -.012em;
    margin-bottom: 10px;
    max-width: 50ch;
}

.dlg-price {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 80;
    font-weight: 320;
    font-size: clamp(40px, 5.4vw, 64px);
    line-height: 1;
    letter-spacing: -.02em;
    background: linear-gradient(180deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
    font-feature-settings: "lnum","tnum";
    margin-bottom: 6px;
}
.dlg-spec {
    font-family: var(--font-body);
    font-size: 11.5px;
    font-weight: 500;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--smoke);
    margin-bottom: 12px;
}
.dlg-spec b {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 480;
    font-size: 1.4em;
    text-transform: none;
    letter-spacing: 0;
    color: var(--ice);
    margin-right: 2px;
}
.dlg-rule {
    height: 1px;
    margin: 10px 0;
    background: linear-gradient(90deg, var(--mint) 0%, transparent 60%);
    opacity: .45;
}

.dlg-tier {
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 8px;
    margin-bottom: 14px;
    font-family: var(--font-body);
}
.dlg-tier__num {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 32;
    font-weight: 460;
    font-size: 22px;
    line-height: 1;
}
.dlg-tier__lbl {
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: .26em;
    text-transform: uppercase;
}
.dlg-tier--hot  {
    background: rgba(251,113,133,.12);
    border: 1px solid rgba(251,113,133,.32);
    color: var(--rose);
}
.dlg-tier--warm {
    background: rgba(251,191,36,.10);
    border: 1px solid rgba(251,191,36,.30);
    color: var(--amber);
}
.dlg-tier--cold {
    background: rgba(168,156,128,.10);
    border: 1px solid rgba(168,156,128,.30);
    color: var(--smoke);
}

.dlg-cta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin: 6px 0 8px;
}
.dlg-cta--empty {
    padding: 12px 14px;
    background: rgba(168,156,128,.08);
    border-radius: 10px;
    color: var(--smoke);
    font-style: italic;
    font-family: var(--font-display);
    font-size: 13px;
}
.dlg-cta__wa {
    flex: 1 1 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 14px 20px;
    border-radius: 999px;
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    color: var(--ink-00) !important;
    font-family: var(--font-body);
    font-weight: 700;
    font-size: 14px;
    letter-spacing: .02em;
    text-decoration: none !important;
    border: none !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.4),
        0 12px 28px -8px rgba(221,194,105,.55);
    transition: transform .2s, box-shadow .2s;
}
.dlg-cta__wa:hover {
    transform: translateY(-1px);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.5),
        0 16px 36px -8px rgba(221,194,105,.85);
}
.dlg-cta__call {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 14px 18px;
    border-radius: 999px;
    background: rgba(221,194,105,.06);
    border: 1px solid rgba(221,194,105,.32);
    color: var(--ice) !important;
    font-family: var(--font-body);
    font-weight: 600;
    font-size: 13.5px;
    text-decoration: none !important;
    transition: background .2s, border-color .2s;
}
.dlg-cta__call:hover {
    background: rgba(221,194,105,.12);
    border-color: rgba(221,194,105,.5);
}
.dlg-email {
    display: inline-block;
    margin-top: 8px;
    color: var(--mint-l) !important;
    font-family: var(--font-display);
    font-style: italic;
    font-size: 13px;
    text-decoration: none !important;
    border-bottom: 1px dotted rgba(221,194,105,.4) !important;
}

.dlg-section-lbl,
.dlg-desc-lbl {
    margin-top: 22px;
    margin-bottom: 8px;
    font-family: var(--font-body);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: var(--mint);
}
.dlg-desc {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 16;
    font-weight: 320;
    font-size: 13.5px;
    line-height: 1.6;
    color: var(--fog);
    background: rgba(20,16,8,.4);
    padding: 12px 14px;
    border-left: 2px solid rgba(221,194,105,.32);
    border-radius: 4px 8px 8px 4px;
}

.dlg-notes {
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.dlg-note {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 12px;
    padding: 8px 12px;
    background: rgba(20,16,8,.4);
    border-left: 2px solid var(--mint);
    border-radius: 4px 8px 8px 4px;
}
.dlg-note__time {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: .14em;
    color: var(--slate);
    white-space: nowrap;
    min-width: 80px;
    padding-top: 1px;
}
.dlg-note__body {
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--ice);
}

/* "Open detail" button on lot cards — gold pill, small, restrained. */
.lot button[data-testid="stBaseButton-secondary"][title*="Abrir"],
.lot button[data-testid="stBaseButton-secondary"][title*="Open"] {
    background: rgba(221,194,105,.06) !important;
    border: 1px solid rgba(221,194,105,.32) !important;
    color: var(--mint-l) !important;
    font-family: var(--font-body) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: .14em !important;
    padding: 4px 10px !important;
    min-height: 24px !important;
}

/* ──── Persona health rows ─────────────────────────────────────────────── */
.ph-host {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 320;
    font-size: 12px;
    color: var(--mint-l);
    margin: 8px 0 4px;
    letter-spacing: .01em;
}
.ph-row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 8px;
    align-items: center;
    padding: 4px 8px;
    margin: 1px 0;
    border-radius: 6px;
    border-left: 2px solid transparent;
    font-family: var(--font-body);
    font-size: 10.5px;
}
.ph-row--ok    { background: rgba(86,175,116,.08);  border-left-color: #56af74; }
.ph-row--warn  { background: rgba(251,191,36,.08);  border-left-color: var(--amber); }
.ph-row--bad   { background: rgba(251,113,133,.10); border-left-color: var(--rose); }
.ph-row--cool  { background: rgba(168,156,128,.08); border-left-color: var(--smoke); opacity: .7; }
.ph-row__name {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 600;
    color: var(--ice);
    letter-spacing: .02em;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ph-row__rate {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 460;
    font-size: 13px;
    color: var(--ice);
    font-feature-settings: "lnum","tnum";
    min-width: 32px;
    text-align: right;
}
.ph-row--ok   .ph-row__rate { color: #86d4a8; }
.ph-row--warn .ph-row__rate { color: var(--amber); }
.ph-row--bad  .ph-row__rate { color: var(--rose); }
.ph-row--cool .ph-row__rate { color: var(--smoke); }
.ph-row__sub {
    font-size: 9px;
    font-weight: 600;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--slate);
    white-space: nowrap;
}

/* ──── Live run-progress strip ─────────────────────────────────────────── */
.run-live {
    position: relative;
    margin: var(--sp-3) 0 var(--sp-4);
    padding: var(--sp-4) var(--sp-5);
    border-radius: 14px;
    background:
        radial-gradient(800px 200px at 0% 0%, rgba(221,194,105,.10), transparent 65%),
        linear-gradient(180deg, rgba(20,16,8,.7) 0%, rgba(10,8,6,.95) 100%);
    border: 1px solid rgba(221,194,105,.32);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.04),
        0 8px 28px -10px rgba(221,194,105,.30);
    overflow: hidden;
}
.run-live::before {
    /* hairline gold rule top */
    content: "";
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg,
        transparent 0%,
        var(--mint-d) 15%, var(--mint) 50%, var(--mint-d) 85%,
        transparent 100%);
    background-size: 200% 100%;
    animation: shimmer 4s linear infinite;
}
.run-live__pulse {
    position: absolute;
    top: 18px; left: 18px;
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--mint);
    box-shadow: 0 0 0 0 rgba(221,194,105,.6);
    animation: glowPulse 1.6s ease-out infinite;
}
.run-live__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--sp-3);
    margin-bottom: var(--sp-3);
    padding-left: 24px;
}
.run-live__eyebrow {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: var(--mint);
}
.run-live__sources {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 320;
    font-size: 13px;
    color: var(--fog);
}
.run-live__grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--sp-3) var(--sp-5);
    align-items: end;
}
@media (max-width: 900px) {
    .run-live__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.run-live__num {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 72, "SOFT" 0;
    font-weight: 320;
    font-size: clamp(22px, 3vw, 36px);
    line-height: 1;
    letter-spacing: -.02em;
    color: var(--ice);
    font-feature-settings: "lnum","tnum";
}
.run-live__num--zone {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--mint-l);
    letter-spacing: .04em;
    word-break: break-word;
}
.run-live__num--err { color: var(--rose); }
.run-live__lbl {
    font-family: var(--font-body);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--slate);
    margin-top: 4px;
}

/* ── Done banner — appears for ~60s after run completes ──────────────── */
.run-done {
    margin: var(--sp-3) 0 var(--sp-4);
    padding: var(--sp-3) var(--sp-4);
    border-radius: 10px;
    background: linear-gradient(180deg, rgba(86,175,116,.10) 0%, rgba(20,16,8,.5) 100%);
    border-left: 3px solid #56af74;
    display: flex;
    align-items: baseline;
    gap: var(--sp-4);
    flex-wrap: wrap;
}
.run-done--ko {
    background: linear-gradient(180deg, rgba(251,113,133,.10) 0%, rgba(20,16,8,.5) 100%);
    border-left-color: var(--rose);
}
.run-done__eyebrow {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: #86d4a8;
}
.run-done--ko .run-done__eyebrow { color: var(--rose); }
.run-done__row {
    font-family: var(--font-display);
    font-style: italic;
    font-size: 14px;
    color: var(--fog);
    display: flex;
    gap: var(--sp-3);
}
.run-done__row b {
    font-weight: 460;
    font-style: normal;
    color: var(--ice);
    margin-right: 2px;
}

/* ──── Quick actions strip — Dashboard top toolbar ─────────────────────── */
.qa-strip {
    display: block;
    margin: var(--sp-3) 0 var(--sp-4);
    padding: var(--sp-3) var(--sp-3);
    background:
        linear-gradient(90deg, rgba(221,194,105,.04) 0%, transparent 30%),
        linear-gradient(180deg, rgba(20,16,8,.4) 0%, rgba(10,8,6,.6) 100%);
    border: 1px solid rgba(221,194,105,.12);
    border-radius: 14px;
    position: relative;
}
.qa-strip::before {
    content: attr(data-eyebrow);
    position: absolute;
    top: -8px;
    left: 18px;
    padding: 0 8px;
    font-family: var(--font-body);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: .28em;
    color: var(--mint);
    background: var(--ink-00);
}
/* Buttons inside qa-strip — sober but clearly clickable */
.qa-strip + div [data-testid="stBaseButton-secondary"],
.qa-strip [data-testid="stBaseButton-secondary"] {
    background: rgba(221,194,105,.04) !important;
    border: 1px solid rgba(221,194,105,.18) !important;
    color: var(--ice) !important;
    font-family: var(--font-body) !important;
    font-size: 12.5px !important;
    font-weight: 500 !important;
    letter-spacing: .02em !important;
    padding: 10px 14px !important;
    transition: background .2s, border-color .2s, transform .15s;
}
.qa-strip + div [data-testid="stBaseButton-secondary"]:hover,
.qa-strip [data-testid="stBaseButton-secondary"]:hover {
    background: rgba(221,194,105,.10) !important;
    border-color: rgba(221,194,105,.4) !important;
    transform: translateY(-1px);
}
.qa-strip + div [data-testid="stBaseButton-primary"],
.qa-strip [data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%) !important;
    border: none !important;
    color: var(--ink-00) !important;
    font-weight: 700 !important;
    font-size: 12.5px !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.4),
        0 4px 14px -4px rgba(221,194,105,.5) !important;
    transition: transform .15s, box-shadow .15s;
}
.qa-strip + div [data-testid="stBaseButton-primary"]:hover,
.qa-strip [data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-1px);
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.5),
        0 8px 22px -4px rgba(221,194,105,.7) !important;
}

/* ──── Empty state ré-skin: a guided invitation, not a blank page ──────── */
.empty-stage {
    margin: var(--sp-5) auto var(--sp-6);
    max-width: 720px;
    padding: var(--sp-6) var(--sp-5);
    text-align: center;
    background:
        radial-gradient(600px 280px at 50% 0%, rgba(221,194,105,.10), transparent 70%),
        linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
    border-top: 1px solid rgba(221,194,105,.32);
    border-bottom: 1px solid rgba(221,194,105,.14);
    position: relative;
}
.empty-stage__eyebrow {
    font-family: var(--font-body);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .32em;
    text-transform: uppercase;
    color: var(--mint);
    margin-bottom: var(--sp-3);
}
.empty-stage__title {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 80;
    font-weight: 320;
    font-size: clamp(28px, 3.6vw, 42px);
    line-height: 1.05;
    color: var(--ice);
    margin: 0 0 var(--sp-3);
    letter-spacing: -.018em;
}
.empty-stage__title em {
    background: linear-gradient(180deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
}
.empty-stage__deck {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 18;
    font-weight: 320;
    font-size: 14.5px;
    color: var(--fog);
    line-height: 1.6;
    max-width: 50ch;
    margin: 0 auto var(--sp-4);
}
.empty-stage__steps {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--sp-4);
    margin-top: var(--sp-5);
    text-align: left;
}
.empty-stage__step {
    padding-left: var(--sp-3);
    border-left: 1px solid rgba(221,194,105,.25);
}
.empty-stage__step-num {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 32;
    font-size: 18px;
    color: var(--mint);
    margin-bottom: 4px;
    letter-spacing: .04em;
}
.empty-stage__step-title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 20, "SOFT" 30;
    font-weight: 460;
    font-size: 14px;
    color: var(--ice);
    margin-bottom: 4px;
}
.empty-stage__step-body {
    font-family: var(--font-body);
    font-size: 12px;
    color: var(--smoke);
    line-height: 1.55;
}

/* ──── Language toggle (PT / EN) at top of sidebar ──────────────────────── */
.lang-toggle {
    display: block;
    padding: 8px 4px 4px;
    margin: 4px 0 8px;
    border-bottom: 1px solid rgba(221,194,105,.10);
}
.lang-toggle + div [data-testid="stBaseButton-secondary"],
.lang-toggle + div [data-testid="stBaseButton-primary"] {
    background: transparent !important;
    border: 1px solid rgba(221,194,105,.18) !important;
    border-radius: 999px !important;
    color: var(--smoke) !important;
    font-family: var(--font-body) !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    letter-spacing: .12em !important;
    padding: 4px 10px !important;
    min-height: 28px !important;
    height: 28px !important;
    box-shadow: none !important;
    transition: background .18s, border-color .18s, color .18s;
}
.lang-toggle + div [data-testid="stBaseButton-secondary"]:hover {
    background: rgba(221,194,105,.06) !important;
    border-color: rgba(221,194,105,.32) !important;
    color: var(--ice) !important;
}
.lang-toggle + div [data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, var(--mint-l) 0%, var(--mint) 60%, var(--mint-d) 100%) !important;
    border-color: transparent !important;
    color: var(--ink-00) !important;
    font-weight: 700 !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.4),
        0 4px 10px -4px rgba(221,194,105,.5) !important;
}

/* ──── Sidebar navigation grouped by purpose ───────────────────────────── */
.nav-wrap {
    margin: var(--sp-2) 0 var(--sp-4);
}
.nav-group {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: var(--sp-3) 8px 6px 4px;
    margin-top: var(--sp-3);
    margin-bottom: 4px;
    border-bottom: 1px solid rgba(221,194,105,.10);
    position: relative;
}
.nav-group:first-child { margin-top: var(--sp-2); }
.nav-group__roman {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 24, "SOFT" 60;
    font-weight: 320;
    font-size: 16px;
    line-height: 1;
    color: var(--mint);
    min-width: 28px;
    letter-spacing: .04em;
}
.nav-group__meta { line-height: 1.1; }
.nav-group__title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 24, "SOFT" 30;
    font-weight: 420;
    font-size: 13px;
    color: var(--ice);
    letter-spacing: -.005em;
    line-height: 1.1;
}
.nav-group__caption {
    font-family: var(--font-body);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: .26em;
    text-transform: uppercase;
    color: var(--slate);
    margin-top: 3px;
}

/* Nav buttons — sober link-row look (NOT chunky CTA chips) */
.nav-wrap [data-testid="stBaseButton-secondary"],
.nav-wrap [data-testid="stBaseButton-primary"] {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-left: 2px solid transparent !important;
    border-radius: 0 6px 6px 0 !important;
    color: var(--fog) !important;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 6px 12px !important;
    margin: 1px 0 !important;
    font-family: var(--font-body) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: -.005em !important;
    transition: background .2s, border-color .2s, color .2s, padding-left .2s;
    box-shadow: none !important;
    min-height: 30px !important;
    height: auto !important;
}
.nav-wrap [data-testid="stBaseButton-secondary"]:hover {
    background: rgba(221,194,105,.05) !important;
    border-left-color: rgba(221,194,105,.45) !important;
    color: var(--ice) !important;
    padding-left: 16px !important;
}
.nav-wrap [data-testid="stBaseButton-primary"] {
    background: linear-gradient(90deg, rgba(221,194,105,.16) 0%, rgba(221,194,105,.04) 60%, transparent 100%) !important;
    border-left-color: var(--mint) !important;
    color: var(--ice) !important;
    font-weight: 600 !important;
    padding-left: 16px !important;
}
.nav-wrap [data-testid="stBaseButton-primary"]::after {
    content: "›";
    margin-left: auto;
    color: var(--mint);
    font-family: var(--font-display);
    font-style: italic;
    font-size: 18px;
    opacity: .85;
}
.nav-wrap [data-testid="stBaseButton-primary"]:hover {
    background: linear-gradient(90deg, rgba(221,194,105,.22) 0%, rgba(221,194,105,.06) 60%, transparent 100%) !important;
}

/* ──── Sidebar: gold-frame plate around the logo ────────────────────────── */
.patabrava-mark {
    position: relative;
}
.patabrava-mark::before {
    content: "";
    position: absolute;
    top: 12px; left: -2px; right: -2px;
    height: 1px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(221,194,105,.4) 30%,
        rgba(221,194,105,.4) 70%, transparent 100%);
}
.patabrava-mark::after {
    content: "";
    position: absolute;
    bottom: 12px; left: -2px; right: -2px;
    height: 1px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(221,194,105,.18) 30%,
        rgba(221,194,105,.18) 70%, transparent 100%);
}

/* ──── Auction-lot card variant ─────────────────────────────────────────── */
/* Apply alongside .card to upgrade a lead row to lot-style presentation. */
.lot {
    position: relative;
    padding: 32px var(--sp-5) var(--sp-4) var(--sp-6);
    border-left: 2px solid var(--mint);
    border-radius: 4px 14px 14px 4px;
    background:
        linear-gradient(90deg, rgba(221,194,105,.06) 0%, transparent 18%),
        linear-gradient(180deg, rgba(20,16,8,.55) 0%, rgba(10,8,6,.85) 100%);
    margin-bottom: 8px;
}
.lot::before {
    /* "Lot Nº" label — small caps */
    content: "LOT " counter(lot, decimal-leading-zero);
    position: absolute;
    top: 10px;
    left: 18px;
    font-family: var(--font-mono);
    font-size: 9.5px;
    font-weight: 500;
    letter-spacing: .28em;
    color: var(--mint);
    opacity: .8;
}
.lot::after {
    /* Right-side micro asterisk before chips */
    content: "";
    position: absolute;
    top: 12px;
    right: 18px;
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--mint);
    box-shadow: 0 0 8px rgba(221,194,105,.6);
    opacity: .7;
}
.lot-list { counter-reset: lot; }
.lot { counter-increment: lot; }

.lot-title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 24, "SOFT" 30;
    font-weight: 420;
    font-size: 1.08rem;
    color: var(--ice);
    letter-spacing: -0.012em;
    line-height: 1.25;
    margin-bottom: 3px;
}
.lot-meta {
    font-family: var(--font-body);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--smoke);
}
.lot-meta em {
    font-family: var(--font-display);
    font-style: italic;
    font-variation-settings: "opsz" 14, "SOFT" 60;
    font-weight: 400;
    font-size: 0.84rem;
    text-transform: none;
    letter-spacing: 0;
    color: var(--mint-l);
}
.lot-days {
    font-family: var(--font-mono) !important;
    font-size: 0.66rem !important;
    letter-spacing: .12em !important;
    color: var(--slate) !important;
}

/* Hover ornaments — small gold corner ticks on cards */
.card {
    --corner-size: 14px;
    --corner-color: rgba(221,194,105,0);
    transition:
        transform .25s cubic-bezier(.4,0,.2,1),
        border-color .25s,
        box-shadow .25s,
        --corner-color .3s;
}
.card:hover {
    --corner-color: rgba(221,194,105,.55);
}
.card::before {
    content: "";
    position: absolute;
    top: 6px; left: 6px;
    width: var(--corner-size); height: var(--corner-size);
    border-top: 1px solid var(--corner-color);
    border-left: 1px solid var(--corner-color);
    transition: opacity .3s, border-color .3s;
    pointer-events: none;
    border-radius: 1px;
}
.card > *:last-child::after,
.card-corner-br {
    /* fallback corner via a sibling div if the structure allows */
}
</style>"""

st.markdown(_CSS_BASE, unsafe_allow_html=True)
st.markdown(_CSS_CARDS, unsafe_allow_html=True)


# ─── CSS: polish layer ───────────────────────────────────────────────────────
# Loaded last so its rules take precedence over the base + cards layers.
# Adds: animated mesh-grid background, refined sidebar nav, button shimmer,
# data-frame polish, toast styling, section dividers, skeleton states,
# refined radios/checkboxes, page-load fade, and Plotly-friendly chart frames.

_CSS_POLISH = """<style>
/* ──── Global page-load fade ───────────────────────────────────────────── */
[data-testid="stAppViewBlockContainer"] > div {
    animation: fadeIn .5s cubic-bezier(.4,0,.2,1) both;
}

/* ──── Background: animated mesh + subtle grid texture ─────────────────── */
.stApp::before {
    content: "";
    position: fixed; inset: 0;
    z-index: 0;
    pointer-events: none;
    background-image:
        radial-gradient(circle at 20% 0%,  rgba(221,194,105,.08), transparent 35%),
        radial-gradient(circle at 80% 100%, rgba(198, 162, 100,.10), transparent 40%),
        radial-gradient(circle at 50% 50%, rgba(56,189,248,.04),  transparent 50%);
    background-size: 100% 100%, 100% 100%, 100% 100%;
    background-position: 0 0;
    animation: meshDrift 22s ease-in-out infinite alternate;
}
.stApp::after {
    content: "";
    position: fixed; inset: 0;
    z-index: 0;
    pointer-events: none;
    background-image:
        linear-gradient(rgba(255,255,255,.013) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.013) 1px, transparent 1px);
    background-size: 48px 48px, 48px 48px;
    mask-image: radial-gradient(ellipse at center, #000 30%, transparent 80%);
    -webkit-mask-image: radial-gradient(ellipse at center, #000 30%, transparent 80%);
}
.main, section[data-testid="stSidebar"] { position: relative; z-index: 1; }

@keyframes meshDrift {
    0%   { background-position: 0% 0%, 100% 100%, 50% 50%; }
    100% { background-position: 6% 4%, 94% 96%, 54% 46%; }
}

/* ──── Sidebar navigation: pill-style radio with gradient indicator ────── */
section[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 4px !important;
    flex-direction: column !important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 11px !important;
    padding: 9px 12px !important;
    transition: all .2s cubic-bezier(.4,0,.2,1) !important;
    cursor: pointer !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    position: relative !important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {
    display: none !important;        /* hide native bullet */
}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(221,194,105,.06) !important;
    border-color: rgba(221,194,105,.18) !important;
    transform: translateX(2px);
}
section[data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb*="checked"],
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background:
        linear-gradient(90deg, rgba(221,194,105,.16) 0%, rgba(56,189,248,.06) 100%) !important;
    border-color: rgba(221,194,105,.4) !important;
    box-shadow:
        inset 3px 0 0 var(--mint),
        0 4px 14px -6px rgba(221,194,105,.4) !important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label p {
    font-weight: 600 !important;
    color: var(--fog) !important;
    margin: 0 !important;
    font-size: .87rem !important;
}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
    color: var(--mint) !important;
}

/* ──── Buttons: shimmer sweep on hover ─────────────────────────────────── */
.stButton > button {
    position: relative;
    overflow: hidden;
}
.stButton > button::after {
    content: "";
    position: absolute; top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(255,255,255,.08) 50%,
        transparent 100%);
    transition: left .6s cubic-bezier(.4,0,.2,1);
    pointer-events: none;
}
.stButton > button:hover::after {
    left: 100%;
}

/* ──── Selectbox dropdown panel — match dark theme ─────────────────────── */
[data-baseweb="popover"] > div {
    background: rgba(11,16,32,.95) !important;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 10px !important;
    box-shadow: 0 16px 48px -12px rgba(0,0,0,.6) !important;
}
[data-baseweb="menu"] li {
    color: var(--fog) !important;
    transition: background .15s, padding-left .15s;
}
[data-baseweb="menu"] li:hover {
    background: rgba(221,194,105,.1) !important;
    color: var(--mint) !important;
    padding-left: 18px !important;
}

/* ──── Slider: refined track + handle ──────────────────────────────────── */
.stSlider [role="slider"] {
    background: var(--grad-primary) !important;
    border: 2px solid var(--ink-10) !important;
    box-shadow: 0 0 0 4px rgba(221,194,105,.1),
                0 4px 14px -4px rgba(221,194,105,.5) !important;
    transition: transform .15s !important;
}
.stSlider [role="slider"]:hover {
    transform: scale(1.15);
    box-shadow: 0 0 0 6px rgba(221,194,105,.15),
                0 6px 20px -4px rgba(221,194,105,.7) !important;
}
.stSlider > div > div > div > div {
    background: var(--grad-primary) !important;
}

/* ──── Checkbox: refined glass tick ────────────────────────────────────── */
.stCheckbox label > div:first-child {
    border-radius: 6px !important;
    border: 1.5px solid rgba(255,255,255,.15) !important;
    background: rgba(11,16,32,.5) !important;
    transition: all .2s !important;
}
.stCheckbox label:hover > div:first-child {
    border-color: var(--mint) !important;
    box-shadow: 0 0 0 4px rgba(221,194,105,.08);
}
.stCheckbox label > div:first-child[aria-checked="true"] {
    background: var(--grad-primary) !important;
    border-color: transparent !important;
    box-shadow: 0 4px 14px -4px rgba(221,194,105,.5);
}

/* ──── Toasts and status messages ──────────────────────────────────────── */
.stAlert, [data-testid="stNotification"] {
    background: rgba(11,16,32,.85) !important;
    backdrop-filter: blur(14px) saturate(150%);
    -webkit-backdrop-filter: blur(14px) saturate(150%);
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 12px !important;
    box-shadow: 0 12px 40px -12px rgba(0,0,0,.5) !important;
    padding: 12px 16px !important;
    animation: slideInRight .4s cubic-bezier(.4,0,.2,1) both;
}
.stAlert[data-baseweb="notification"][kind="success"] {
    border-left: 3px solid var(--mint) !important;
    background:
        linear-gradient(90deg, rgba(221,194,105,.1) 0%, rgba(11,16,32,.85) 50%) !important;
}
.stAlert[data-baseweb="notification"][kind="error"] {
    border-left: 3px solid var(--rose) !important;
    background:
        linear-gradient(90deg, rgba(251,113,133,.1) 0%, rgba(11,16,32,.85) 50%) !important;
}
.stAlert[data-baseweb="notification"][kind="warning"] {
    border-left: 3px solid var(--amber) !important;
    background:
        linear-gradient(90deg, rgba(251,191,36,.1) 0%, rgba(11,16,32,.85) 50%) !important;
}
.stAlert[data-baseweb="notification"][kind="info"] {
    border-left: 3px solid var(--sky) !important;
    background:
        linear-gradient(90deg, rgba(56,189,248,.1) 0%, rgba(11,16,32,.85) 50%) !important;
}

@keyframes slideInRight {
    from { opacity: 0; transform: translateX(20px); }
    to   { opacity: 1; transform: translateX(0); }
}

/* ──── Section divider with gradient + label ──────────────────────────── */
hr {
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(255,255,255,.1) 30%,
        rgba(221,194,105,.25) 50%,
        rgba(255,255,255,.1) 70%,
        transparent 100%) !important;
    height: 1px !important;
    border: none !important;
    margin: 1.8rem 0 !important;
}

/* ──── Section labels: small mark before text ─────────────────────────── */
.lbl-section {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px !important;
}
.lbl-section::before {
    content: "";
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--grad-primary);
    box-shadow: 0 0 8px -1px rgba(221,194,105,.6);
    flex-shrink: 0;
}

/* ──── Data frames — striped, sticky header, hover row ─────────────────── */
.stDataFrame [data-testid="stDataFrameResizable"] {
    border: 1px solid rgba(255,255,255,.06) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    background: rgba(11,16,32,.4) !important;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}
.stDataFrame [data-testid="stTable"] thead tr th {
    background: rgba(29,39,71,.65) !important;
    border-bottom: 1px solid rgba(255,255,255,.08) !important;
    color: var(--smoke) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    font-size: .72rem !important;
    text-transform: uppercase !important;
    letter-spacing: .08em !important;
    padding: 10px 14px !important;
}
.stDataFrame [data-testid="stTable"] tbody tr {
    transition: background .15s !important;
}
.stDataFrame [data-testid="stTable"] tbody tr:nth-child(odd) {
    background: rgba(255,255,255,.012) !important;
}
.stDataFrame [data-testid="stTable"] tbody tr:hover {
    background: rgba(221,194,105,.05) !important;
}
.stDataFrame [data-testid="stTable"] tbody td {
    border-bottom: 1px solid rgba(255,255,255,.03) !important;
    color: var(--fog) !important;
    font-size: .82rem !important;
    padding: 9px 14px !important;
}

/* ──── Progress bar ────────────────────────────────────────────────────── */
.stProgress > div > div > div {
    background: var(--grad-primary) !important;
    background-size: 200% 100% !important;
    animation: shimmer 2.5s linear infinite !important;
    border-radius: 999px !important;
    box-shadow: 0 0 12px -2px rgba(221,194,105,.5);
}
.stProgress > div > div {
    background: rgba(11,16,32,.6) !important;
    border-radius: 999px !important;
}

/* ──── Skeleton loader (use with class="skeleton") ─────────────────────── */
.skeleton {
    background:
        linear-gradient(90deg,
            rgba(29,39,71,.4) 0%,
            rgba(221,194,105,.08) 50%,
            rgba(29,39,71,.4) 100%);
    background-size: 200% 100%;
    animation: shimmer 1.6s linear infinite;
    border-radius: 8px;
}

/* ──── Spinner refresh — match palette ─────────────────────────────────── */
.stSpinner > div {
    border-top-color: var(--mint) !important;
    border-right-color: var(--sky) !important;
    border-bottom-color: var(--violet) !important;
    border-left-color: transparent !important;
    filter: drop-shadow(0 0 8px rgba(221,194,105,.4));
}

/* ──── Caption / muted text ────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--dust) !important;
    font-size: .78rem !important;
    font-style: normal !important;
    letter-spacing: .01em;
}

/* ──── Tooltips (Streamlit help indicator) ─────────────────────────────── */
[data-baseweb="tooltip"] {
    background: rgba(5,8,16,.95) !important;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 8px !important;
    color: var(--fog) !important;
    font-size: .78rem !important;
    box-shadow: 0 8px 28px -8px rgba(0,0,0,.7) !important;
}

/* ──── Charts: subtle frame around plotly canvas ───────────────────────── */
[data-testid="stPlotlyChart"] {
    background: rgba(11,16,32,.4) !important;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,.05);
    border-radius: 12px;
    padding: 8px;
    box-shadow: var(--shadow-card);
    transition: border-color .25s, box-shadow .25s;
}
[data-testid="stPlotlyChart"]:hover {
    border-color: rgba(221,194,105,.18);
}

/* ──── Number input refined ────────────────────────────────────────────── */
.stNumberInput button {
    background: rgba(29,39,71,.5) !important;
    border: 1px solid rgba(255,255,255,.06) !important;
    color: var(--smoke) !important;
}
.stNumberInput button:hover {
    color: var(--mint) !important;
    border-color: rgba(221,194,105,.3) !important;
}

/* ──── Refined badge animations ────────────────────────────────────────── */
.badge-drop {
    position: relative;
}
.badge-drop::after {
    content: "↓";
    position: absolute;
    right: -2px; top: 50%;
    transform: translateY(-50%) translateX(120%);
    opacity: 0;
    color: currentColor;
    font-weight: 900;
    transition: all .25s;
}
.badge-drop:hover::after {
    opacity: 1;
    transform: translateY(-50%) translateX(0%);
}

/* ──── Cursor accent — subtle gradient on focusable elements ───────────── */
.stApp button:focus-visible,
.stApp input:focus-visible,
.stApp [role="radio"]:focus-visible {
    outline: 2px solid rgba(221,194,105,.5) !important;
    outline-offset: 2px !important;
}

/* ──── Score orb hover: pulse ring ─────────────────────────────────────── */
.score-orb {
    cursor: default;
}
.score-orb.orb-hot:hover {
    animation: orbPulseHot 1.2s cubic-bezier(.4,0,.2,1) infinite;
}
@keyframes orbPulseHot {
    0%, 100% {
        box-shadow: 0 4px 20px -4px rgba(251,113,133,.45),
                    0 0 0 0   rgba(251,113,133,.5);
    }
    50% {
        box-shadow: 0 4px 24px -4px rgba(251,113,133,.7),
                    0 0 0 8px rgba(251,113,133,0);
    }
}

/* ──── Tabs: gradient active underline ─────────────────────────────────── */
.stTabs [aria-selected="true"] {
    position: relative;
}
.stTabs [aria-selected="true"]::after {
    content: "";
    position: absolute;
    bottom: 0; left: 12%; right: 12%; height: 2px;
    background: var(--grad-primary);
    border-radius: 2px;
    box-shadow: 0 0 8px -1px rgba(221,194,105,.6);
}

/* ──── Subtle breathing on logo ────────────────────────────────────────── */
.patabrava-logo {
    animation: float 5.5s ease-in-out infinite;
}

/* ──── Image + Text alignment fixes ────────────────────────────────────── */
[data-testid="stMarkdownContainer"] a {
    color: var(--mint) !important;
    text-decoration: none !important;
    border-bottom: 1px dotted rgba(221,194,105,.4);
    transition: border-color .15s, color .15s;
}
[data-testid="stMarkdownContainer"] a:hover {
    color: var(--mint-l) !important;
    border-bottom-color: var(--mint-l);
}

/* ──── Improve density / breathing of key sections ─────────────────────── */
[data-testid="column"]:not(:last-child) { padding-right: .25rem; }
[data-testid="column"]:not(:first-child) { padding-left: .25rem; }
</style>"""

st.markdown(_CSS_POLISH, unsafe_allow_html=True)


# ─── CSS: UX practicality layer ──────────────────────────────────────────────
# Final layer focused on speed-of-use rather than aesthetics:
#   * Compact card density toggle-friendly classes
#   * Sticky filter bar (scrolls with page, always reachable)
#   * Empty-state illustrations (no more bare "Sem dados")
#   * Quick-action keyboard hints
#   * "New since last visit" pulse for fresh leads
#   * Reduced motion mode for users with prefers-reduced-motion
#   * Stronger focus rings + larger click targets on small screens

_CSS_UX = """<style>
/* ──── Reduced motion respect ──────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: .01ms !important;
    }
    .stApp::before { animation: none !important; }
}

/* ──── Sticky filter bar — sidebar bottom CTA stays visible ────────────── */
section[data-testid="stSidebar"] > div > div > div:last-child {
    position: sticky;
    bottom: 0;
    background: linear-gradient(180deg, transparent 0%, var(--ink-10) 35%);
    padding-top: 1rem;
}

/* ──── Hover preview on cards ─────────────────────────────────────────── */
.card { cursor: default; }
.card:focus-within {
    outline: 2px solid rgba(221,194,105,.4);
    outline-offset: 2px;
}

/* ──── Empty-state styling ─────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    background:
        linear-gradient(180deg, rgba(29,39,71,.25) 0%, rgba(11,16,32,.4) 100%);
    border: 1px dashed rgba(255,255,255,.08);
    border-radius: 16px;
    margin: 24px 0;
}
.empty-state .icon {
    font-size: 2.4rem;
    background: var(--grad-primary);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 14px;
    display: inline-block;
    animation: float 4s ease-in-out infinite;
}
.empty-state .title {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    color: var(--ice);
    font-size: 1.05rem;
    margin-bottom: 6px;
}
.empty-state .hint {
    color: var(--smoke);
    font-size: .85rem;
    line-height: 1.5;
}

/* ──── Fresh badge — pulse for new-since-last-visit ────────────────────── */
.fresh-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--mint);
    box-shadow: 0 0 0 0 var(--mint);
    animation: glowPulse 2s infinite;
    margin-right: 6px;
    vertical-align: middle;
}

/* ──── Click targets larger on touch ───────────────────────────────────── */
@media (hover: none) {
    .stButton > button,
    section[data-testid="stSidebar"] [role="radiogroup"] label {
        min-height: 44px !important;     /* iOS HIG minimum */
    }
}

/* ──── Number-up reveal on metric values ───────────────────────────────── */
@keyframes counter {
    from { opacity: 0; transform: scale(.92); }
    to   { opacity: 1; transform: scale(1); }
}
[data-testid="stMetricValue"] {
    animation: counter .6s cubic-bezier(.34,1.56,.64,1) both;
}

/* ──── Keyboard hint pills (use class="kbd") ──────────────────────────── */
.kbd {
    display: inline-block;
    font-family: 'Space Grotesk', monospace;
    font-size: .68rem;
    font-weight: 600;
    padding: 1px 7px;
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.12);
    border-bottom-width: 2px;
    border-radius: 5px;
    color: var(--fog);
    line-height: 1.5;
    margin: 0 2px;
}

/* ──── Quick-action bar (used in lead detail expanders) ────────────────── */
.quick-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 12px;
}
.quick-bar a {
    text-decoration: none !important;
    border-bottom: none !important;
    padding: 6px 12px;
    background: rgba(29,39,71,.5);
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 8px;
    font-size: .78rem;
    font-weight: 600;
    color: var(--fog) !important;
    transition: all .2s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.quick-bar a:hover {
    transform: translateY(-1px);
    background: rgba(221,194,105,.12);
    border-color: rgba(221,194,105,.4);
    color: var(--mint) !important;
    box-shadow: 0 6px 16px -8px rgba(221,194,105,.4);
}
.quick-bar a.qa-phone:hover     { background: rgba(221,194,105,.12);  color: var(--mint) !important; }
.quick-bar a.qa-whatsapp:hover  { background: rgba(34,211,153,.15);  color: #25d366 !important; border-color: rgba(37,211,102,.4); }
.quick-bar a.qa-email:hover     { background: rgba(56,189,248,.12);  color: var(--sky) !important; }
.quick-bar a.qa-portal:hover    { background: rgba(198, 162, 100,.12); color: var(--violet) !important; }

/* ──── Sticky stage shortcuts on Oportunidades page ────────────────────── */
.stage-bar {
    position: sticky; top: 8px;
    z-index: 5;
    background:
        linear-gradient(180deg, var(--ink-00) 0%, rgba(5,8,16,.85) 100%);
    backdrop-filter: blur(14px) saturate(140%);
    -webkit-backdrop-filter: blur(14px) saturate(140%);
    padding: 12px;
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,.06);
    margin-bottom: 16px;
}

/* ──── Toast positioning, top-right unobtrusive ────────────────────────── */
.stToast {
    bottom: auto !important;
    top: 16px !important;
    right: 16px !important;
}

/* ──── Compact-mode adjustment on narrow viewports ─────────────────────── */
@media (max-width: 1100px) {
    .main .block-container { padding: 0 1rem 4rem !important; }
    .hero { padding: 20px 22px; }
    [data-testid="stMetricValue"] { font-size: 1.65rem !important; }
    .patabrava-name { font-size: 1.1rem; }
}

/* ──── Shimmer skeleton placeholder ─────────────────────────────────────
   Use class="sk sk-line", "sk sk-card" while data is loading. */
.sk {
    background: linear-gradient(90deg,
        rgba(29,39,71,.4) 0%,
        rgba(221,194,105,.08) 50%,
        rgba(29,39,71,.4) 100%);
    background-size: 200% 100%;
    animation: shimmer 1.6s linear infinite;
    border-radius: 8px;
    display: block;
}
.sk-line { height: 14px; margin: 8px 0; }
.sk-card { height: 92px; margin: 12px 0; }
.sk-orb  { width: 56px; height: 56px; border-radius: 50%; }
</style>"""

st.markdown(_CSS_UX, unsafe_allow_html=True)

# ─── Ambient gold-dust layer ────────────────────────────────────────────────
# Six gold motes drifting across the viewport. Sits below content, never
# intercepts pointer events. Fixed-position so it persists across scrolls.
st.markdown(
    '<div class="dust" aria-hidden="true">'
    '<span class="dust__mote"></span><span class="dust__mote"></span>'
    '<span class="dust__mote"></span><span class="dust__mote"></span>'
    '<span class="dust__mote"></span><span class="dust__mote"></span>'
    '</div>',
    unsafe_allow_html=True,
)


# ─── CSS: micro-interactions + delight layer ─────────────────────────────────
# Final flourish — focused on the small details that make the UI feel
# alive: hover ripples, focus halos, command-bar feel, real-time sparkle
# on freshly-arrived data, success confetti for action completions.

_CSS_DELIGHT = """<style>
/* ──── Hover ripple on cards (subtle inner glow follow) ────────────────── */
.card { background-clip: padding-box; }
.card::before {
    content: "";
    position: absolute; inset: 0;
    border-radius: 14px;
    background: radial-gradient(
        450px circle at var(--mx, 50%) var(--my, 50%),
        rgba(221,194,105,.07),
        transparent 35%
    );
    opacity: 0;
    transition: opacity .25s;
    pointer-events: none;
}
.card:hover::before { opacity: 1; }

/* ──── Command-bar feel for sidebar action buttons ─────────────────────── */
section[data-testid="stSidebar"] .stButton > button {
    text-align: left !important;
    padding-left: 14px !important;
    font-size: .87rem !important;
    letter-spacing: -.005em;
}
section[data-testid="stSidebar"] .stButton > button::before {
    content: "›";
    margin-right: 8px;
    color: var(--mint);
    font-weight: 700;
    transition: transform .2s, margin-right .2s;
    display: inline-block;
}
section[data-testid="stSidebar"] .stButton > button:hover::before {
    transform: translateX(3px);
    color: var(--mint-l);
}

/* ──── Live indicator ───────────────────────────────────────────────────── */
.live-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--mint);
    margin-right: 6px;
    box-shadow: 0 0 0 0 var(--mint);
    animation: liveBlink 1.6s infinite;
}
@keyframes liveBlink {
    0%, 60% { box-shadow: 0 0 0 0 rgba(221,194,105,.6); }
    100%    { box-shadow: 0 0 0 10px rgba(221,194,105,0); }
}

/* ──── Score badge sparkles for HOT leads ──────────────────────────────── */
.badge-hot {
    position: relative;
    overflow: visible;
}
.badge-hot::before {
    content: "✦";
    position: absolute;
    top: -6px; left: -8px;
    color: rgba(251,113,133,.9);
    font-size: .55rem;
    animation: sparkle 2.2s ease-in-out infinite;
}
@keyframes sparkle {
    0%, 100% { opacity: 0;   transform: scale(.5) rotate(0deg); }
    50%      { opacity: .9;  transform: scale(1) rotate(180deg); }
}

/* ──── Focus halos with brand colour ───────────────────────────────────── */
input:focus-visible, select:focus-visible, textarea:focus-visible,
button:focus-visible, [role="radio"]:focus-visible {
    outline: 3px solid rgba(221,194,105,.35) !important;
    outline-offset: 2px;
    border-radius: 8px;
    transition: outline .15s;
}

/* ──── Tab bar: subtle hover gradient ──────────────────────────────────── */
.stTabs [data-baseweb="tab"]:hover {
    background: linear-gradient(135deg, rgba(221,194,105,.08), rgba(56,189,248,.05)) !important;
    color: var(--ice) !important;
}

/* ──── Hero — gradient sweep on load ──────────────────────────────────── */
.hero {
    background-size: 200% 200%;
    animation: heroSweep 14s ease-in-out infinite alternate;
}
@keyframes heroSweep {
    0%   { background-position: 0% 0%; }
    100% { background-position: 100% 100%; }
}

/* ──── Smooth caret on text inputs ─────────────────────────────────────── */
.stTextInput input, .stTextArea textarea {
    caret-color: var(--mint) !important;
}

/* ──── Selection color ─────────────────────────────────────────────────── */
::selection {
    background: rgba(221,194,105,.3);
    color: var(--ice);
}

/* ──── Number transitions on metrics ───────────────────────────────────── */
[data-testid="stMetricValue"] > div {
    transition: color .3s, transform .3s;
}

/* ──── Avatar/initials placeholder for contact_name (when used) ────────── */
.avatar {
    display: inline-flex;
    width: 32px; height: 32px;
    border-radius: 50%;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-family: 'Space Grotesk', sans-serif;
    font-size: .75rem;
    color: var(--ice);
    background: linear-gradient(135deg, var(--violet) 0%, var(--mint) 100%);
    box-shadow: 0 2px 8px -2px rgba(198, 162, 100,.4);
    text-transform: uppercase;
}

/* ──── Data freshness indicator (use class="freshness") ────────────────── */
.freshness {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: .68rem;
    color: var(--mint);
    font-weight: 600;
    padding: 2px 8px;
    background: rgba(221,194,105,.1);
    border: 1px solid rgba(221,194,105,.25);
    border-radius: 999px;
}

/* ──── Toast & notification top-right slide-in (already in UX layer) ──── */

/* ──── Print styles for export-friendly views ─────────────────────────── */
@media print {
    .stApp { background: white !important; color: black !important; }
    section[data-testid="stSidebar"] { display: none !important; }
    .card, .intel-box, .alert-card {
        background: white !important;
        border-color: #e2e8f0 !important;
        color: black !important;
        animation: none !important;
        box-shadow: none !important;
    }
    [data-testid="stMetricValue"] {
        color: black !important;
        -webkit-text-fill-color: black !important;
    }
}
</style>"""

st.markdown(_CSS_DELIGHT, unsafe_allow_html=True)


# ─── Helper functions ──────────────────────────────────────────────────────────

def label_emoji(label: str) -> str:
    """Plain-text emoji — safe for st.expander, st.radio, etc."""
    return {"HOT": "🔴", "WARM": "🟡", "COLD": "🔵"}.get(label, "⚪")


def _humanise_delta(td) -> str:
    """timedelta → 'há 3 min' / 'há 2h' / 'há 1d' style."""
    secs = int(td.total_seconds())
    if secs < 60:
        return "agora"
    if secs < 3600:
        return f"há {secs // 60} min"
    if secs < 86_400:
        return f"há {secs // 3600}h"
    return f"há {secs // 86_400}d"


def empty_state(icon: str = "◆", title: str = "Sem dados",
                hint: str = "Corre o pipeline para alimentar o sistema.") -> None:
    """Render an animated empty-state card. Drop-in for `st.caption`."""
    st.markdown(
        f'<div class="empty-state">'
        f'  <div class="icon">{icon}</div>'
        f'  <div class="title">{title}</div>'
        f'  <div class="hint">{hint}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_photo_gallery(lead) -> None:
    """
    Show the listing's primary image inline. Falls back gracefully when
    the lead has no image_url or the URL is unreachable. Streamlit caches
    the byte payload via @st.cache_data with a 1h TTL so repeated views
    of the same lead don't re-download.
    """
    if not getattr(lead, "image_url", None):
        return

    @st.cache_data(ttl=3600, show_spinner=False)
    def _fetch_image_bytes(url: str) -> bytes | None:
        try:
            import httpx
            with httpx.Client(timeout=10.0, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"}) as c:
                r = c.get(url)
                if r.status_code == 200 and r.content:
                    return r.content
        except Exception:
            return None
        return None

    img = _fetch_image_bytes(lead.image_url)
    if img:
        st.image(img, use_container_width=True)


@st.dialog(" ", width="large")
def show_lead_dialog(lead_id: int) -> None:
    """Magazine-style lead detail modal — the moment-of-truth surface
    of the product. When the agent clicks a lead card on Top Accionáveis,
    this modal opens with: editorial header (eyebrow · serif italic gold
    price · spec strip · phone CTA), photo (if any), notes timeline,
    and CRM stage move-buttons. All in one focused view."""
    from sqlalchemy import select
    from storage.database import get_db
    from storage.models import Lead, CRMNote
    from datetime import datetime as _dt, timezone as _tz

    with get_db() as db:
        lead = db.execute(select(Lead).where(Lead.id == lead_id)).scalar_one_or_none()
        if not lead:
            st.error("Lead não encontrado.")
            return
        notes = db.execute(
            select(CRMNote).where(CRMNote.lead_id == lead_id)
                           .order_by(CRMNote.created_at.desc())
                           .limit(8)
        ).scalars().all()

        # Detach so we can use after the session closes
        lead_data = {
            "id":          lead.id,
            "title":       lead.title or "—",
            "price":       lead.price,
            "area_m2":     lead.area_m2,
            "bedrooms":    getattr(lead, "bedrooms", None),
            "bathrooms":   getattr(lead, "bathrooms", None),
            "typology":    lead.typology or "—",
            "zone":        lead.zone or "—",
            "score":       lead.score or 0,
            "score_label": lead.score_label or "COLD",
            "owner_type":  lead.owner_type or "",
            "agency_name": lead.agency_name,
            "phone":       lead.contact_phone,
            "email":       lead.contact_email,
            "url":         lead.url,
            "source":      lead.source or "—",
            "image_url":   getattr(lead, "image_url", None),
            "first_seen":  lead.first_seen_at,
            "days_market": getattr(lead, "days_on_market", 0) or 0,
            "crm_stage":   lead.crm_stage or "novo",
            "description": (lead.description or "")[:600],
        }
        notes_data = [
            {
                "body":       n.note,
                "type":       n.note_type or "internal",
                "created_at": n.created_at,
            }
            for n in notes
        ]

    # ── Header strip — score + tier + close hint ─────────────────────
    tier_color_class = (
        "dlg-tier--hot"  if lead_data["score_label"] == "HOT"  else
        "dlg-tier--warm" if lead_data["score_label"] == "WARM" else
        "dlg-tier--cold"
    )
    own_chip = ""
    own = (lead_data["owner_type"] or "").lower()
    if own == "fsbo":
        own_chip = '<span class="dlg-chip dlg-chip--fsbo">PROPRIETÁRIO DIRECTO</span>'
    elif own == "agency":
        own_chip = '<span class="dlg-chip dlg-chip--agency">AGÊNCIA</span>'

    price_str = (
        f"{int(lead_data['price']):,} €".replace(",", " ")
        if lead_data["price"] else "Preço sob consulta"
    )

    spec_items = []
    if lead_data["area_m2"]:
        spec_items.append(f'<b>{int(lead_data["area_m2"])}</b> m²')
    if lead_data["bedrooms"]:
        spec_items.append(f'<b>{lead_data["bedrooms"]}</b> qtos')
    if lead_data["bathrooms"]:
        spec_items.append(f'<b>{lead_data["bathrooms"]}</b> wc')
    spec_items.append(f'<b>{lead_data["days_market"]}</b> dias no mercado')
    spec_strip = " · ".join(spec_items)

    # ── Two-column layout: photo left, editorial right ─────────────────
    col_img, col_info = st.columns([1, 1.05], gap="medium")

    with col_img:
        st.markdown('<div class="dlg-photo-wrap">', unsafe_allow_html=True)
        if lead_data["image_url"]:
            try:
                st.image(lead_data["image_url"], use_container_width=True)
            except Exception:
                st.markdown('<div class="dlg-photo-stub">📷</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="dlg-photo-stub">📷  Sem foto</div>',
                        unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        # Source + URL
        st.markdown(
            f'<div class="dlg-source">'
            f'  <span class="dlg-source__lbl">FONTE</span>'
            f'  <span class="dlg-source__val">{lead_data["source"].upper()}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if lead_data["url"]:
            st.markdown(
                f'<div class="dlg-source"><a href="{lead_data["url"]}" target="_blank" '
                f'class="dlg-source__link">↗  abrir anúncio original</a></div>',
                unsafe_allow_html=True,
            )

    with col_info:
        st.markdown(
            f'<div class="dlg-eyebrow">{lead_data["typology"].upper()}'
            f'<span class="dlg-sep">·</span>{lead_data["zone"].upper()}{own_chip}</div>'
            f'<div class="dlg-title">{lead_data["title"][:90]}</div>'
            f'<div class="dlg-price">{price_str}</div>'
            f'<div class="dlg-spec">{spec_strip}</div>'
            f'<div class="dlg-rule"></div>'
            f'<div class="dlg-tier {tier_color_class}">'
            f'  <span class="dlg-tier__num">{lead_data["score"]}</span>'
            f'  <span class="dlg-tier__lbl">{lead_data["score_label"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── CTAs: WhatsApp BIG GOLD + tel + email ────────────────────
        if lead_data["phone"]:
            wa = lead_data["phone"].replace("+", "").replace(" ", "")
            phone_disp = lead_data["phone"]
            st.markdown(
                f'<div class="dlg-cta">'
                f'  <a href="https://wa.me/{wa}" target="_blank" '
                f'     class="dlg-cta__wa">📱  WhatsApp · {phone_disp}</a>'
                f'  <a href="tel:{lead_data["phone"]}" class="dlg-cta__call">'
                f'     📞  Ligar</a>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="dlg-cta dlg-cta--empty">Sem contacto telefónico ainda</div>',
                unsafe_allow_html=True,
            )
        if lead_data["email"]:
            st.markdown(
                f'<a href="mailto:{lead_data["email"]}" class="dlg-email">'
                f'  ✉  {lead_data["email"]}</a>',
                unsafe_allow_html=True,
            )

    # ── Description (full width) ──────────────────────────────────────
    if lead_data["description"]:
        st.markdown(
            f'<div class="dlg-desc-lbl">DESCRIÇÃO</div>'
            f'<div class="dlg-desc">{lead_data["description"]}</div>',
            unsafe_allow_html=True,
        )

    # ── CRM stage move buttons ────────────────────────────────────────
    st.markdown('<div class="dlg-section-lbl">PIPELINE</div>', unsafe_allow_html=True)
    stage_now = lead_data["crm_stage"]
    cl1, cl2, cl3, cl4, cl5 = st.columns(5)
    stages = [("novo", "📥 Novo"), ("contactado", "📞 Contactado"),
              ("negociacao", "🤝 Negociação"), ("ganho", "✅ Ganho"),
              ("perdido", "❌ Perdido")]
    for col, (key, label) in zip([cl1, cl2, cl3, cl4, cl5], stages):
        with col:
            is_now = (stage_now == key)
            if st.button(
                label, key=f"dlg_stage_{key}_{lead_data['id']}",
                use_container_width=True,
                type="primary" if is_now else "secondary",
                disabled=is_now,
            ):
                from crm.manager import CRMManager
                CRMManager().move_to_stage(lead_data["id"], key)
                st.cache_data.clear()
                st.rerun()

    # ── Notes timeline ────────────────────────────────────────────────
    if notes_data:
        st.markdown(
            '<div class="dlg-section-lbl">HISTÓRICO</div>',
            unsafe_allow_html=True,
        )
        notes_html = '<div class="dlg-notes">'
        for n in notes_data:
            ts = n["created_at"]
            ts_str = ts.strftime("%d %b · %H:%M") if ts else "—"
            notes_html += (
                f'<div class="dlg-note">'
                f'  <div class="dlg-note__time">{ts_str}</div>'
                f'  <div class="dlg-note__body">{n["body"]}</div>'
                f'</div>'
            )
        notes_html += "</div>"
        st.markdown(notes_html, unsafe_allow_html=True)

    # ── Quick note add ─────────────────────────────────────────────────
    nk = f"dlg_note_input_{lead_data['id']}"
    new_note = st.text_input(
        "Adicionar nota",
        placeholder="Ex: Ligou, aceita visita sábado às 16h",
        key=nk,
        label_visibility="collapsed",
    )
    nc1, nc2 = st.columns([5, 1])
    with nc2:
        if st.button("💾  Guardar", key=f"dlg_note_save_{lead_data['id']}",
                     use_container_width=True):
            if new_note.strip():
                from crm.manager import CRMManager
                CRMManager().add_note(lead_data["id"], new_note.strip())
                st.toast("✓ Nota guardada", icon="💾")
                st.rerun()


def _render_lead_magazine_header(lead) -> None:
    """Editorial "magazine spread" header for a lead — appears above the
    tabbed extras. Conceptually: an auction catalogue lot description.

    Layout:
      [eyebrow: TIPOLOGIA · ZONA · LOT N°]
      [price huge italic Fraunces gold gradient]   [spec strip]
      [hairline rule]
      [phone CTA chip + WhatsApp link]
    """
    if not lead:
        return
    typ   = (getattr(lead, "typology", None) or "—").upper()
    zone  = (getattr(lead, "zone", None) or "—").upper()
    price = getattr(lead, "price", None)
    area  = getattr(lead, "area_m2", None)
    beds  = getattr(lead, "bedrooms", None)
    baths = getattr(lead, "bathrooms", None)
    days  = getattr(lead, "days_on_market", 0) or 0
    src   = (getattr(lead, "source", None) or "—").upper()
    own   = (getattr(lead, "owner_type", None) or "")
    phone = getattr(lead, "contact_phone", None)
    score = getattr(lead, "score", 0) or 0

    own_chip = ""
    if own == "fsbo":
        own_chip = '<span class="lot-chip lot-chip--fsbo">PROPRIETÁRIO DIRECTO</span>'
    elif own == "agency":
        own_chip = '<span class="lot-chip lot-chip--agency">AGÊNCIA</span>'

    price_str = f"{int(price):,} €".replace(",", " ") if price else "Preço sob consulta"

    spec_items = []
    if area:  spec_items.append(f'<span><b>{int(area)}</b> m²</span>')
    if beds:  spec_items.append(f'<span><b>{beds}</b> qtos</span>')
    if baths: spec_items.append(f'<span><b>{baths}</b> wc</span>')
    spec_items.append(f'<span><b>{days}</b> dias</span>')
    spec_items.append(f'<span><b>{score}</b> score</span>')
    spec_strip = "<div class='lot-spec'>" + " · ".join(spec_items) + "</div>"

    phone_html = ""
    if phone:
        wa = phone.replace("+", "").replace(" ", "")
        phone_html = (
            f'<div class="lot-cta">'
            f'<a href="tel:{phone}" class="lot-cta__call">📞 {phone}</a>'
            f'<a href="https://wa.me/{wa}" target="_blank" class="lot-cta__wa">WhatsApp ›</a>'
            f'</div>'
        )

    st.markdown(
        f'<article class="lot-page">'
        f'  <div class="lot-page__eyebrow">{typ} <span class="lot-page__sep">·</span> {zone} {own_chip}</div>'
        f'  <div class="lot-page__title">{(getattr(lead, "title", None) or "Listing sem título")[:80]}</div>'
        f'  <div class="lot-page__row">'
        f'    <div class="lot-page__price">{price_str}</div>'
        f'    {spec_strip}'
        f'  </div>'
        f'  <div class="lot-page__rule"></div>'
        f'  {phone_html}'
        f'  <div class="lot-page__source">FONTE · {src}</div>'
        f'</article>',
        unsafe_allow_html=True,
    )


def render_lead_extras(lead, *, show_photo: bool = True,
                       show_similar: bool = True,
                       show_edit: bool = True,
                       show_merge: bool = True) -> None:
    """
    Drop-in addon for any detail expander. Renders the four advanced
    panels in tabs so the operator can browse without scrolling:

      🖼  Foto    — listing image (cached 1h)
      🔗  Similar — top 5 comparáveis
      ✎   Editar  — inline form to fix fields
      ⇆   Fundir  — merge with another lead by id

    All tabs are best-effort — any failure logs and fades quietly so
    the rest of the expander UI keeps rendering.
    """
    if not lead:
        return
    _render_lead_magazine_header(lead)
    tabs = []
    if show_photo:   tabs.append("🖼")
    if show_similar: tabs.append("🔗 Similar")
    if show_edit:    tabs.append("✎ Editar")
    if show_merge:   tabs.append("⇆ Fundir")
    if not tabs:
        return

    rendered = st.tabs(tabs)
    idx = 0

    if show_photo:
        with rendered[idx]:
            if getattr(lead, "image_url", None):
                render_photo_gallery(lead)
            else:
                st.caption("Sem imagem para este lead.")
        idx += 1

    if show_similar:
        with rendered[idx]:
            render_similar_leads(lead.id, top_n=5)
        idx += 1

    if show_edit:
        with rendered[idx]:
            _render_edit_form(lead)
        idx += 1

    if show_merge:
        with rendered[idx]:
            _render_merge_form(lead)
        idx += 1


def _render_edit_form(lead) -> None:
    """Inline editor for the most-frequently-corrected fields."""
    from storage.database import get_db
    from storage.models import Lead

    with st.form(f"edit_form_{lead.id}", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            n_title = st.text_input("Título", value=lead.title or "")
            n_zone  = st.text_input("Zona",   value=lead.zone or "")
            n_typ   = st.text_input("Tipologia", value=lead.typology or "")
            n_phone = st.text_input("Telefone", value=lead.contact_phone or "")
        with c2:
            n_price = st.number_input(
                "Preço (€)",
                value=float(lead.price or 0.0),
                step=1000.0, format="%.0f",
            )
            n_email = st.text_input("Email", value=lead.contact_email or "")
            n_name  = st.text_input("Nome contacto", value=lead.contact_name or "")
            n_addr  = st.text_input("Morada", value=lead.address or "")
        n_note = st.text_area(
            "Razão da edição (vai para CRMNote)",
            placeholder="Ex: Confirmei com proprietário, preço correcto é 285k.",
        )
        submitted = st.form_submit_button("💾 Guardar alterações", use_container_width=True)
        if submitted:
            try:
                with get_db() as db:
                    row = db.query(Lead).get(lead.id)
                    if not row:
                        st.error("Lead já não existe.")
                        return
                    row.title         = n_title or None
                    row.zone          = n_zone or None
                    row.typology      = n_typ or None
                    row.price         = float(n_price) if n_price else None
                    row.contact_phone = n_phone or None
                    row.contact_email = (n_email or None) and n_email.lower()
                    row.contact_name  = n_name or None
                    row.address       = n_addr or None
                    if n_note.strip():
                        from storage.models import CRMNote
                        from datetime import datetime as _dt
                        db.add(CRMNote(
                            lead_id=row.id,
                            note=f"✎ Manual edit\n{n_note.strip()}",
                            note_type="manual_edit",
                            created_by="dashboard",
                            created_at=_dt.utcnow(),
                        ))
                    db.commit()
                st.toast("✓ Alterações guardadas", icon="💾")
                st.cache_data.clear()
                # Drop similarity index — title/zone may have changed
                try:
                    from utils.similarity import invalidate as _inv
                    _inv()
                except Exception:
                    pass
                st.rerun()
            except Exception as e:
                st.error(f"Falhou: {e}")


def _render_merge_form(lead) -> None:
    """Manual merge: input a duplicate lead id, archive it, append sources."""
    from storage.database import get_db
    from storage.models import Lead, CRMNote
    from datetime import datetime as _dt

    st.caption(
        "Funde este lead com outro: o outro fica arquivado, "
        "e os contactos do outro são adicionados aqui se estiverem em falta."
    )
    cm1, cm2 = st.columns([3, 1])
    with cm1:
        dup_id = st.number_input(
            "ID do lead duplicado",
            min_value=0, step=1, value=0,
            key=f"merge_id_{lead.id}",
        )
    with cm2:
        st.write("")
        if st.button("⇆ Fundir", key=f"merge_btn_{lead.id}",
                     use_container_width=True, type="primary"):
            if not dup_id or dup_id == lead.id:
                st.warning("Indica um ID diferente.")
                return
            try:
                with get_db() as db:
                    canonical = db.query(Lead).get(lead.id)
                    duplicate = db.query(Lead).get(int(dup_id))
                    if not canonical or not duplicate:
                        st.error("Lead não encontrado.")
                        return
                    if duplicate.archived:
                        st.info("Esse lead já está arquivado.")
                        return
                    # Merge sources
                    can_src = canonical.sources
                    seen = {(s.get("source"), s.get("url")) for s in can_src}
                    for s in duplicate.sources:
                        key = (s.get("source"), s.get("url"))
                        if key not in seen:
                            can_src.append(s); seen.add(key)
                    canonical.sources = can_src
                    # Promote missing contact fields
                    for f in ("contact_phone", "contact_email",
                              "contact_whatsapp", "contact_name", "agency_name"):
                        if not getattr(canonical, f) and getattr(duplicate, f):
                            setattr(canonical, f, getattr(duplicate, f))
                    duplicate.archived  = True
                    duplicate.crm_stage = "merged"
                    db.add(CRMNote(
                        lead_id=canonical.id,
                        note=f"⇆ Fusão manual: lead #{duplicate.id} arquivado e fontes propagadas.",
                        note_type="manual_merge",
                        created_by="dashboard",
                        created_at=_dt.utcnow(),
                    ))
                    db.commit()
                st.toast(f"✓ Fundido com #{dup_id}", icon="⇆")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Falhou: {e}")


def render_similar_leads(lead_id: int, top_n: int = 5) -> None:
    """
    Show 'similar to this' inline list. Best-effort — silently no-ops
    when the similarity index can't be built (eg. sklearn missing).
    """
    try:
        from utils.similarity import similar_to
    except Exception:
        return
    try:
        rows = similar_to(lead_id, top_n=top_n)
    except Exception as e:
        st.caption(f"⚠ similar lookup falhou: {e}")
        return
    if not rows:
        st.caption("Sem comparáveis suficientes.")
        return
    st.markdown('<div class="lbl-section">Comparáveis</div>', unsafe_allow_html=True)
    for r in rows:
        st.markdown(
            f'<div style="display:flex;gap:10px;padding:6px 8px;'
            f'background:rgba(29,39,71,.3);border-radius:8px;margin-bottom:5px;'
            f'font-size:.78rem;">'
            f'  <span style="color:var(--smoke);font-family:Space Grotesk;'
            f'                font-weight:700;">#{r.id}</span>'
            f'  <span style="color:var(--fog);">{r.typology or "?"} {r.zone or "?"}</span>'
            f'  <span style="margin-left:auto;color:var(--mint);font-weight:700;">'
            f'    {fmt_price(r.price)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def quick_actions_bar(phone: str | None, email: str | None,
                      url: str | None = None, whatsapp: str | None = None) -> None:
    """One-tap outreach buttons: call, WhatsApp, e-mail, portal listing."""
    parts: list[str] = []
    if phone:
        digits = phone.lstrip("+").replace(" ", "")
        parts.append(
            f'<a class="qa-phone" href="tel:{phone}" title="Ligar">'
            f'📞 {phone}</a>'
        )
        wa_target = whatsapp or f"+{digits}" if digits else None
        if wa_target:
            wa_digits = wa_target.lstrip("+").replace(" ", "")
            parts.append(
                f'<a class="qa-whatsapp" href="https://wa.me/{wa_digits}" '
                f'target="_blank" title="WhatsApp">💬 WhatsApp</a>'
            )
    if email:
        parts.append(
            f'<a class="qa-email" href="mailto:{email}" title="Email">'
            f'✉ {email}</a>'
        )
    if url:
        parts.append(
            f'<a class="qa-portal" href="{url}" target="_blank" '
            f'rel="noopener" title="Abrir anúncio">🔗 Anúncio</a>'
        )
    if parts:
        st.markdown(
            f'<div class="quick-bar">{"".join(parts)}</div>',
            unsafe_allow_html=True,
        )

def badge_html(label: str) -> str:
    """HTML badge — only inside st.markdown(unsafe_allow_html=True)."""
    cls = {"HOT": "badge-hot", "WARM": "badge-warm", "COLD": "badge-cold"}.get(label, "badge-cold")
    return f'<span class="badge {cls}">{label}</span>'

def score_orb(score: int, label: str) -> str:
    cls = {"HOT": "orb-hot", "WARM": "orb-warm"}.get(label, "orb-cold")
    return f'<span class="score-orb {cls}">{score}</span>'

def fmt_price(p) -> str:
    if not p:
        return "—"
    return f"{float(p):,.0f} €".replace(",", ".")

def delta_html(delta) -> str:
    if delta is None:
        return ""
    if delta > 0:
        return f'<span class="delta-pos">&#9660; {delta:.1f}% abaixo mercado</span>'
    return f'<span class="delta-neg">&#9650; {abs(delta):.1f}% acima mercado</span>'

def owner_chip(is_owner, agency, owner_type: str = None) -> str:
    """Render owner type chip — uses owner_type when available, falls back to is_owner."""
    ot = owner_type or ("fsbo" if is_owner else "agency")
    if ot == "fsbo":
        return '<span class="chip" style="color:#a8861a;border-color:rgba(168,134,26,.2);">&#128100; Particular</span>'
    if ot == "developer":
        return '<span class="chip" style="color:#f59e0b;border-color:rgba(245,158,11,.2);">&#127959; Promotor</span>'
    if ot == "unknown":
        return '<span class="chip" style="color:#a89c80;border-color:rgba(148,163,184,.2);">&#10067; Desconhecido</span>'
    # agency (default)
    return f'<span class="chip">&#127970; {(agency or "Agência")[:20]}</span>'

def contact_chip(phone, email, contact_source: str = None) -> str:
    """
    Contact chip with optional source-type suffix.

    contact_source governs a small muted label appended to the chip:
      • "website:*"      → · Site    (agency homepage, generic office contact)
      • "cross_portal:*" → · Cross   (propagated from a matching listing on another portal)
      • anything else    → no suffix (direct listing contact — most trustworthy)
      • None             → no suffix (source unknown, treat as direct)
    """
    _src = contact_source or ""
    if _src.startswith("website:"):
        _suffix = (
            '<span style="font-size:.56rem;font-weight:700;opacity:.5;'
            'letter-spacing:.2px;margin-left:3px;">· Site</span>'
        )
    elif _src.startswith("cross_portal:"):
        _suffix = (
            '<span style="font-size:.56rem;font-weight:700;opacity:.5;'
            'letter-spacing:.2px;margin-left:3px;">· Cross</span>'
        )
    else:
        _suffix = ""

    if phone:
        return f'<span class="chip">&#128222; {phone}{_suffix}</span>'
    if email:
        return f'<span class="chip">&#9993; {email}{_suffix}</span>'
    return '<span class="chip" style="color:#33485e;">Sem contacto</span>'

def contact_badge(phone, email) -> str:
    """Distinctive badge showing contact availability — for card headers."""
    if phone:
        return '<span class="badge badge-phone">&#128222; TELEFONE</span>'
    if email:
        return '<span class="badge badge-email">&#9993; EMAIL</span>'
    return '<span class="badge badge-nocontact">SEM CONTACTO</span>'

def src_pill(source: str) -> str:
    return f'<span style="background:#16202f;border:1px solid #243450;border-radius:4px;font-size:.58rem;font-weight:800;padding:1px 5px;color:#56697e;text-transform:uppercase;">{source}</span>'

def confidence_chip(confidence) -> str:
    """Contact confidence chip: 100=Alta, 70+=Boa, 30+=Média, 0=Sem conf. Safe for None."""
    c = confidence or 0
    if c >= 100:
        return '<span class="chip" style="font-size:.65rem;color:#a8861a;border-color:rgba(168,134,26,.2);">&#9679; Alta</span>'
    if c >= 70:
        return '<span class="chip" style="font-size:.65rem;color:#60a5fa;border-color:rgba(96,165,250,.2);">&#9679; Boa</span>'
    if c >= 30:
        return '<span class="chip" style="font-size:.65rem;color:#f59e0b;border-color:rgba(245,158,11,.2);">&#9679; Media</span>'
    return '<span class="chip" style="font-size:.65rem;color:#5c5240;border-color:rgba(148,163,184,.12);">&#9675; Sem conf.</span>'

def lead_type_chip(lead_type: str | None) -> str:
    """Visual chip for lead_type — fsbo / frbo / agency_listing / developer_listing / unknown."""
    lt = (lead_type or "unknown").lower()
    if lt == "fsbo":
        return '<span class="chip" style="color:#a8861a;border-color:rgba(168,134,26,.2);font-size:.65rem;">&#128100; FSBO</span>'
    if lt == "frbo":
        return '<span class="chip" style="color:#60a5fa;border-color:rgba(96,165,250,.2);font-size:.65rem;">&#128273; FRBO</span>'
    if lt == "agency_listing":
        return '<span class="chip" style="color:#a89c80;border-color:rgba(148,163,184,.15);font-size:.65rem;">&#127970; Agência</span>'
    if lt == "developer_listing":
        return '<span class="chip" style="color:#f59e0b;border-color:rgba(245,158,11,.2);font-size:.65rem;">&#127959; Promotor</span>'
    return '<span class="chip" style="color:#5c5240;border-color:rgba(148,163,184,.1);font-size:.65rem;">&#10067; —</span>'


def lead_quality_chip(lead_quality: str | None) -> str:
    """Visual chip for lead quality tier — high / medium / low."""
    lq = (lead_quality or "low").lower()
    if lq == "high":
        return '<span class="chip" style="color:#a8861a;border-color:rgba(168,134,26,.25);font-size:.65rem;font-weight:700;">&#11088; Alta</span>'
    if lq == "medium":
        return '<span class="chip" style="color:#f59e0b;border-color:rgba(245,158,11,.2);font-size:.65rem;font-weight:700;">&#9679; Média</span>'
    return '<span class="chip" style="color:#5c5240;border-color:rgba(148,163,184,.1);font-size:.65rem;">&#9675; Baixa</span>'


def _gen_outreach_msg(typology, zone, price, owner_type, contact_name=None, first_name=None) -> str:
    """
    Generate a short outreach message using existing lead fields.
    Adapts tone to owner_type: fsbo (direct), agency, developer, unknown.
    """
    typ  = typology or "imóvel"
    z    = zone or "zona"
    prx  = f"{int(price):,}€".replace(",", " ") if price else "valor a confirmar"
    # Use first_name directly when available; fall back to splitting contact_name
    fname = first_name or ((contact_name or "").strip().split()[0] if contact_name else None)

    if owner_type == "fsbo":
        greet = f"Bom dia{f', {fname}' if fname else ''},"
        body  = (
            f"Vi o seu anúncio de {typ} em {z} pelo valor de {prx}.\n"
            f"Tenho interesse genuíno neste imóvel e gostaria de saber mais.\n"
            f"Poderia dar-me mais informações? Tenho disponibilidade para visita."
        )
    elif owner_type == "developer":
        greet = "Bom dia,"
        body  = (
            f"Venho manifestar interesse no {typ} disponível em {z} ({prx}).\n"
            f"Poderiam enviar-me informações adicionais ou documentação disponível?\n"
            f"Estou disponível para reunião ou visita conforme conveniência."
        )
    else:  # agency / unknown
        greet = "Bom dia,"
        body  = (
            f"Gostaria de obter mais informações sobre o {typ} em {z} anunciado por {prx}.\n"
            f"Tenho interesse e disponibilidade para visita breve.\n"
            f"Agradeço a atenção."
        )
    # Signature pulled from settings.contact_signature (configurable per
    # client — defaults to a neutral closing if unset).
    from config.settings import settings
    sig = (getattr(settings, "contact_signature", "") or "").strip()
    if not sig:
        sig = "Cumprimentos"
    return f"{greet}\n\n{body}\n\n{sig}"


def action_links(phone: str | None, email: str | None, sources: list | None = None) -> str:
    """
    Anchor-button links for immediate outreach — no JS, works in all browsers.
      tel:    → opens dialler on mobile / system phone app on desktop
      mailto: → opens default mail client
      source  → opens original listing in new tab (max 2)
    Returns empty string when nothing is available.
    """
    _BTN = (
        "display:inline-block;background:#111827;border:1px solid #243450;"
        "border-radius:6px;padding:3px 10px;font-size:.68rem;font-weight:700;"
        "text-decoration:none;"
    )
    parts = []
    if phone:
        tel = phone.replace(" ", "").replace("-", "")
        parts.append(f'<a href="tel:{tel}" style="{_BTN}color:#a8861a;">&#128222; Ligar</a>')
    if email:
        parts.append(f'<a href="mailto:{email}" style="{_BTN}color:#60a5fa;">&#9993; Email</a>')
    if sources:
        for s in sources[:2]:
            url = (s.get("url") or "").strip()
            src = (s.get("source") or "").upper()
            if url:
                parts.append(
                    f'<a href="{url}" target="_blank" style="{_BTN}color:#56697e;">&#8599; {src}</a>'
                )
    if not parts:
        return ""
    return (
        '<div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:6px;">'
        + "".join(parts)
        + "</div>"
    )

def source_label_pill(label: str, source: str) -> str:
    """Labeled source pill: 'LABEL [pill]'. Returns empty string if source is None/empty."""
    if not source:
        return ""
    return (
        f'<span style="font-size:.58rem;font-weight:700;color:#33485e;text-transform:uppercase;'
        f'letter-spacing:.4px;margin-right:2px;">{label} </span>'
        + src_pill(source)
    )

_MOTIV_RULES = [
    ("Heranca",   ["heranca", "herdeiro", "herdeiros", "herdar"],        "&#127968;"),
    ("Divorcio",  ["divorcio", "separacao", "separada", "separado"],     "&#128148;"),
    ("Emigracao", ["emigr", "mudar de pais", "partir para"],             "&#9992;"),
    ("Urgencia",  ["urgente", "urgencia", "venda rapida", "30 dias"],    "&#9889;"),
    ("Obras",     ["obra", "remodelar", "remodelacao", "restauro"],      "&#128296;"),
    ("Partilhas", ["partilha", "partilhas", "co-proprietario"],          "&#9878;"),
    ("Mudanca",   ["mudanca de cidade", "transferi", "relocac"],         "&#128230;"),
]

def detect_motivation(description: str) -> list[tuple[str, str]]:
    if not description:
        return []
    d = description.lower()
    # normalise accented chars for matching
    import unicodedata
    d_norm = ''.join(c for c in unicodedata.normalize('NFD', d) if unicodedata.category(c) != 'Mn')
    found = []
    for label, keywords, emoji in _MOTIV_RULES:
        if any(kw in d_norm for kw in keywords):
            found.append((label, emoji))
    return found

def generate_alerts(leads: list) -> list[dict]:
    alerts = []
    for lead in leads:
        lbl   = lead.get("label", "")
        score = lead.get("score", 0)
        zone  = lead.get("zone", "?")
        typo  = lead.get("typology", "?")
        price = fmt_price(lead.get("price"))
        delta = lead.get("price_delta_pct") or 0
        dom   = lead.get("days_on_market", 0)
        desc  = lead.get("description", "")

        if lbl == "HOT" and score >= 80:
            alerts.append({
                "type": "hot", "icon": "&#128308;",
                "title": f"HOT detectada — {score} pts",
                "body": f"{typo} em {zone} · {price} · {delta:.1f}% abaixo mercado",
                "meta": f"{dom} dias no mercado",
            })
        elif lead.get("is_owner") and delta > 12 and lbl in ("HOT", "WARM"):
            alerts.append({
                "type": "grn", "icon": "&#128100;",
                "title": f"Proprietario directo — {zone}",
                "body": f"{typo} · {price} · sem mediadora",
                "meta": f"Score {score} · {delta:.1f}% abaixo benchmark",
            })
        elif (lead.get("price_changes") or 0) > 0 and delta > 8:
            alerts.append({
                "type": "warm", "icon": "&#128201;",
                "title": f"Reducao de preco — {zone}",
                "body": f"{typo} · {price} · {lead.get('price_changes', 0)} reducao(oes)",
                "meta": f"Score {score} · {delta:.1f}% abaixo mercado",
            })

        motives = detect_motivation(desc)
        if motives and lbl in ("HOT", "WARM"):
            alerts.append({
                "type": "blue", "icon": motives[0][1],
                "title": f"Motivo de venda — {motives[0][0]}",
                "body": f"{typo} em {zone} · {price}",
                "meta": f"Score {score}",
            })

        if len(alerts) >= 8:
            break
    return alerts[:8]

def alert_card_html(a: dict) -> str:
    cls = {"hot": "alert-hot", "warm": "alert-warm", "grn": "alert-grn"}.get(a["type"], "")
    return (
        f'<div class="alert-card {cls}">'
        f'<div style="font-size:1rem;flex-shrink:0;">{a["icon"]}</div>'
        f'<div>'
        f'<div style="font-weight:700;color:#f1f5f9;font-size:.84rem;margin-bottom:2px;">{a["title"]}</div>'
        f'<div style="color:#a89c80;font-size:.75rem;">{a["body"]}</div>'
        f'<div style="color:#56697e;font-size:.66rem;margin-top:3px;">{a["meta"]}</div>'
        f'</div></div>'
    )


# ─── Data loaders ──────────────────────────────────────────────────────────────

def _match_csource(src: str | None, csource_type: str) -> bool:
    """Return True when a lead's contact_source matches the requested category."""
    s = src or ""
    if csource_type == "website":
        return s.startswith("website:")
    if csource_type == "cross_portal":
        return s.startswith("cross_portal:")
    if csource_type == "direto":
        # Direct = has a non-empty source that is NOT website: or cross_portal:
        return bool(s) and not s.startswith(("website:", "cross_portal:"))
    return True  # unknown type — pass through


@st.cache_data(ttl=60)
def load_leads(zone=None, typology=None, score_min=0, stage=None, label=None,
               is_demo=None, contact=None, owner_type=None, csource_type=None,
               fts_query: str = ""):
    from storage.database import init_db, get_db
    from storage.repository import LeadRepo
    init_db()

    # Full-text search shortcut: when the operator typed a query in the
    # sidebar, pull matching ids first, then pass them as a hard filter to
    # the repo's standard listing query so the rest of the UI's filters
    # (zone, score, stage…) keep working on top of FTS results.
    fts_ids: list[int] | None = None
    fts_query = (fts_query or "").strip()
    if fts_query:
        try:
            from storage.fts import search_lead_ids
            fts_ids = search_lead_ids(fts_query, limit=300)
        except Exception:
            fts_ids = None

    with get_db() as db:
        repo = LeadRepo(db)
        leads = repo.list_active(
            zone=zone, typology=typology,
            score_min=score_min, crm_stage=stage,
            label=label, is_demo=is_demo, contact=contact,
            owner_type=owner_type, limit=500,
        )
        if fts_ids is not None:
            keep = set(fts_ids)
            leads = [l for l in leads if l.id in keep]
        rows = [{
            "id":               l.id,
            "is_demo":          l.is_demo,
            "score":            l.score,
            "label":            l.score_label,
            "title":            l.title,
            "typology":         l.typology,
            "zone":             l.zone,
            "price":            l.price,
            "area_m2":          l.area_m2,
            "price_per_m2":     l.price_per_m2,
            "price_benchmark":  l.price_benchmark,
            "price_delta_pct":  l.price_delta_pct,
            "is_owner":         l.is_owner,
            "owner_type":       l.owner_type,
            "contact_name":     l.contact_name,
            "first_name":       getattr(l, "first_name", None),
            "last_name":        getattr(l, "last_name", None),
            "birthday":         getattr(l, "birthday", None),
            "contact_phone":    l.contact_phone,
            "phone_type":       getattr(l, "phone_type", "unknown"),
            "contact_email":    l.contact_email,
            "has_phone":        bool(l.contact_phone),
            "has_email":        bool(l.contact_email),
            "has_contact":      bool(l.contact_phone or l.contact_email),
            "agency_name":      l.agency_name,
            "days_on_market":   l.days_on_market,
            "price_changes":    l.price_changes,
            "crm_stage":        l.crm_stage,
            "condition":        l.condition,
            "description":      (l.description or "")[:300],
            "address":          l.address,
            "first_seen_at":    l.first_seen_at.strftime("%d/%m/%Y") if l.first_seen_at else "—",
            "sources":          l.sources,
            "score_breakdown":  l.get_score_breakdown(),
            "discovery_source":   l.discovery_source,
            "contact_source":     getattr(l, "contact_source", None),
            "contact_confidence": l.contact_confidence,
            "lead_type":          getattr(l, "lead_type",    None),
            "lead_quality":       getattr(l, "lead_quality", None),
            "parish":             getattr(l, "parish",       None),
        } for l in leads]
        if csource_type:
            rows = [r for r in rows if _match_csource(r.get("contact_source"), csource_type)]
        return rows

@st.cache_data(ttl=60)
def load_stats():
    from storage.database import init_db
    from reports.generator import ReportGenerator
    init_db()
    return ReportGenerator().get_summary_stats()


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Language toggle (PT / EN) — appears above the brand mark ──────────
    if "__lang" not in st.session_state:
        st.session_state["__lang"] = "pt"
    st.markdown('<div class="lang-toggle">', unsafe_allow_html=True)
    _l1, _l2 = st.columns(2)
    with _l1:
        if st.button("🇵🇹  PT", key="lang_pt_btn", use_container_width=True,
                     type="primary" if st.session_state["__lang"] == "pt" else "secondary"):
            st.session_state["__lang"] = "pt"
            st.rerun()
    with _l2:
        if st.button("🇬🇧  EN", key="lang_en_btn", use_container_width=True,
                     type="primary" if st.session_state["__lang"] == "en" else "secondary"):
            st.session_state["__lang"] = "en"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    _logo_uri = _asset_b64(_LOGO2X_PATH if _LOGO2X_PATH.exists() else _LOGO_PATH)
    _logo_html = (
        f'<img src="{_logo_uri}" alt="Patabrava" class="patabrava-logo-img" />'
        if _logo_uri else
        '<div class="patabrava-logo">◆</div>'
    )
    _tag_pt = "Lead intelligence imobiliária"
    _tag_en = "Real-estate lead intelligence"
    _tag = _tag_en if st.session_state["__lang"] == "en" else _tag_pt
    st.markdown(
        '<div class="patabrava-mark" style="padding:0 16px 14px;margin:14px 0 12px;">'
        f'  {_logo_html}'
        f'  <div class="patabrava-tag">{_tag}</div>'
        f'  <div class="patabrava-version">{datetime.now().strftime("%d %b · %H:%M")}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Network status widget ─────────────────────────────────────────────
    # Cached for 60s by the utility; we show it on every render but the
    # actual network probes only fire when the cache expires.
    try:
        from utils.network_status import overall_status
        _net = overall_status()
    except Exception:
        _net = None

    if _net:
        ip_info  = _net["ip"]
        blocked  = _net["blocked_portals"]
        clean    = _net["clean_portals"]
        unknown  = _net["unknown_portals"]
        all_ok   = _net["all_clean"]
        ip_kind  = (
            "vpn"     if ip_info.is_known_vpn else
            "mobile"  if ip_info.is_mobile    else
            "unknown"
        )
        kind_label = t(f"net.kind.{ip_kind}")
        ip_str  = ip_info.ip or "—"
        country = ip_info.country or "—"
        org     = (ip_info.org or "—")[:32]

        # Status pill
        if all_ok:
            pill_class = "net-pill net-pill--ok"
            pill_txt   = "✓ " + t("net.portal.clean").upper()
        elif blocked:
            pill_class = "net-pill net-pill--err"
            pill_txt   = f"✗ {len(blocked)}/{len(blocked) + len(clean) + len(unknown)} " + t("net.portal.blocked").upper()
        else:
            pill_class = "net-pill net-pill--warn"
            pill_txt   = "? " + t("net.portal.unknown").upper()

        portal_chips_html = ""
        for p in (clean + blocked + unknown):
            status = (
                "ok"  if p in clean   else
                "err" if p in blocked else
                "wn"
            )
            portal_chips_html += f'<span class="net-portal net-portal--{status}">{p}</span>'

        st.markdown(
            f'<div class="net-card">'
            f'  <div class="net-card__head">'
            f'    <span class="net-card__title">{t("net.header")}</span>'
            f'    <span class="{pill_class}">{pill_txt}</span>'
            f'  </div>'
            f'  <div class="net-card__row"><span class="net-card__lbl">{t("net.ip")}</span><span class="net-card__val">{ip_str}</span></div>'
            f'  <div class="net-card__row"><span class="net-card__lbl">{t("net.country")}</span><span class="net-card__val">{country}</span></div>'
            f'  <div class="net-card__row"><span class="net-card__lbl">{t("net.org")}</span><span class="net-card__val">{org}</span></div>'
            f'  <div class="net-card__kind">{kind_label}</div>'
            f'  <div class="net-card__portals-lbl">{t("net.portals.title")}</div>'
            f'  <div class="net-card__portals">{portal_chips_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Recommendation panel — only when something is blocked
        if blocked:
            st.markdown(
                f'<div class="net-tip">'
                f'  <div class="net-tip__title">{t("net.tip.heading")}</div>'
                f'  <div class="net-tip__line">{t("net.tip.line1")}</div>'
                f'  <div class="net-tip__line">{t("net.tip.line2")}</div>'
                f'  <div class="net-tip__line">{t("net.tip.line3")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        if st.button(t("net.refresh"), key="net_refresh_btn", use_container_width=True):
            from utils.network_status import overall_status as _ovr
            try:
                _ovr.__globals__["_ip_cache"]    = None
                _ovr.__globals__["_block_cache"] = {}
            except Exception:
                pass
            st.rerun()

    # ── Persona health expander ─────────────────────────────────────────────
    # Shows win-rate per (host, persona) so the operator can see which
    # identities are passing through and which are sleeping in cooldown.
    try:
        from scrapers.anti_block.persona_health import all_entries, reset_all
        _ph_entries = all_entries()
    except Exception:
        _ph_entries = {}
    with st.expander(t("ph.header"), expanded=False):
        if not _ph_entries:
            st.caption(t("ph.empty"))
        else:
            # Aggregate: group by host, show top 5 personas sorted by total req
            by_host: dict[str, list[tuple[str, dict]]] = {}
            for k, e in _ph_entries.items():
                if "::" not in k:
                    continue
                h, p = k.split("::", 1)
                by_host.setdefault(h, []).append((p, e))
            for host, rows in sorted(by_host.items()):
                rows.sort(key=lambda r: -(r[1]["ok"] + r[1]["blocked"]))
                st.markdown(
                    f'<div class="ph-host">{host}</div>',
                    unsafe_allow_html=True,
                )
                for persona_name, e in rows[:5]:
                    total = e["ok"] + e["blocked"]
                    win = (e["ok"] / total * 100) if total else 0
                    cool = max(0, e["cooldown_until"] - time.time())
                    klass = (
                        "ph-row ph-row--cool" if cool > 0
                        else "ph-row ph-row--ok" if win >= 70
                        else "ph-row ph-row--warn" if win >= 40
                        else "ph-row ph-row--bad"
                    )
                    if cool > 0:
                        sub = t("ph.cooldown", m=int(cool // 60))
                    else:
                        sub = f"{e['ok']} ok · {e['blocked']} bl"
                    st.markdown(
                        f'<div class="{klass}">'
                        f'  <span class="ph-row__name">{persona_name}</span>'
                        f'  <span class="ph-row__rate">{int(win)}%</span>'
                        f'  <span class="ph-row__sub">{sub}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        if st.button(t("ph.reset"), key="ph_reset_btn", use_container_width=True):
            try:
                reset_all()
                st.toast("✓  reset", icon="🧹")
                st.rerun()
            except Exception as e:
                st.error(f"reset failed: {e}")

    # ── Navigation: grouped by purpose, not flat (i18n-aware) ─────────────
    # Each item carries a stable page_id (used by the if/elif chain) and
    # translation keys for the displayed label + caption.
    NAV_GROUPS: list[tuple[str, str, str, list[tuple[str, str, str, str]]]] = [
        ("I",   "nav.hunt.title",   "nav.hunt.caption", [
            # (page_id,                   emoji,        label_key,                caption_key)
            ("&#128202;  Dashboard",      "&#128202;",  "nav.dashboard.label",    "nav.dashboard.caption"),
            ("&#128293;  HOT Focus",      "&#128293;",  "nav.hot.label",          "nav.hot.caption"),
            ("&#128268;  Pre-Market",     "&#128268;",  "nav.premarket.label",    "nav.premarket.caption"),
        ]),
        ("II",  "nav.sell.title",   "nav.sell.caption", [
            ("&#127919;  Oportunidades",  "&#127919;",  "nav.opportunities.label","nav.opportunities.caption"),
            ("&#128203;  CRM",            "&#128203;",  "nav.crm.label",          "nav.crm.caption"),
            ("&#128240;  Atividade",      "&#128240;",  "nav.activity.label",     "nav.activity.caption"),
        ]),
        ("III", "nav.intel.title",  "nav.intel.caption", [
            ("&#128205;  Mapa & BI",      "&#128205;",  "nav.map.label",          "nav.map.caption"),
        ]),
        ("IV",  "nav.engine.title", "nav.engine.caption", [
            ("&#129518;  Sistema",        "&#129518;",  "nav.system.label",       "nav.system.caption"),
            ("&#9881;  Motor",            "&#9881;",    "nav.engine_page.label",  "nav.engine_page.caption"),
            ("&#128228;  Exportar",       "&#128228;",  "nav.export.label",       "nav.export.caption"),
        ]),
    ]

    # Initialise current page in session state
    if "__page" not in st.session_state:
        st.session_state["__page"] = NAV_GROUPS[0][3][0][0]
    page = st.session_state["__page"]

    st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
    for roman, group_title_key, group_caption_key, items in NAV_GROUPS:
        st.markdown(
            f'<div class="nav-group">'
            f'  <div class="nav-group__roman">{roman}</div>'
            f'  <div class="nav-group__meta">'
            f'    <div class="nav-group__title">{t(group_title_key)}</div>'
            f'    <div class="nav-group__caption">{t(group_caption_key)}</div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        for page_id, emoji, label_key, caption_key in items:
            is_active = (page_id == page)
            btn_label = f"{emoji}  {t(label_key)}"
            if st.button(
                btn_label,
                key=f"nav_{page_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
                help=t(caption_key),
            ):
                st.session_state["__page"] = page_id
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown(f'<div class="lbl-section">{t("sb.search.header")}</div>', unsafe_allow_html=True)
    fts_query = st.text_input(
        t("sb.search.header"),
        placeholder=t("sb.search.placeholder"),
        label_visibility="collapsed",
        key="fts_query_input",
        value=st.session_state.get("__fts_query_preset", ""),
        help=t("sb.search.help"),
    )

    # Saved searches dropdown — load + delete
    try:
        from storage.saved_searches import (
            list_searches as _ss_list, save_search as _ss_save,
            delete_search as _ss_del, touch as _ss_touch,
        )
        searches = _ss_list()
    except Exception:
        searches = []

    if searches:
        names = ["—"] + [f"{s['name']}" for s in searches]
        chosen = st.selectbox(
            t("sb.bookmarks"), names,
            label_visibility="collapsed",
            help=t("sb.bookmarks.help"),
            key="saved_search_pick",
        )
        if chosen and chosen != "—":
            picked = next((s for s in searches if s["name"] == chosen), None)
            if picked and st.session_state.get("__last_loaded_search") != picked["id"]:
                st.session_state["__fts_query_preset"] = picked["query"]
                st.session_state["__last_loaded_search"] = picked["id"]
                try: _ss_touch(picked["id"])
                except Exception: pass
                st.rerun()

    sscol1, sscol2 = st.columns([3, 1])
    with sscol1:
        new_name = st.text_input(
            t("sb.bookmarks.save_as"),
            placeholder=t("sb.bookmarks.save_as"),
            label_visibility="collapsed", key="ss_new_name",
        )
    with sscol2:
        if st.button("💾", help=t("sb.bookmarks.save_btn"), use_container_width=True, key="ss_save_btn"):
            if new_name and fts_query:
                try:
                    _ss_save(new_name, fts_query, {})
                    st.toast(f"✓ '{new_name}' guardada", icon="💾")
                    st.rerun()
                except Exception as e:
                    st.error(f"Falhou: {e}")

    st.divider()
    st.markdown(f'<div class="lbl-section">{t("sb.presets.header")}</div>', unsafe_allow_html=True)
    # ─── Smart filter presets ───────────────────────────────────────────
    # Each preset writes a deterministic set of session_state keys that
    # the standard filter widgets pick up on rerun. Click → all filters
    # snap to the preset, no manual selection needed.
    PRESETS: list[tuple[str, dict]] = [
        (t("sb.presets.fsbo_hot"),    {"score_floor": 60,  "owner": "&#128100; Particular (FSBO)", "fts": ""}),
        (t("sb.presets.banks"),       {"score_floor": 0,   "fts": "banco OR caixa OR millennium OR santander OR novobanco"}),
        (t("sb.presets.auctions"),    {"score_floor": 0,   "fts": "leil*"}),
        (t("sb.presets.urgent"),      {"score_floor": 50,  "fts": "urgente OR negociavel OR aceitamos"}),
        (t("sb.presets.with_phone"),  {"contact": "&#128222; Com telefone", "score_floor": 50}),
        (t("sb.presets.with_email"),  {"contact": "&#9993; Com email",      "score_floor": 50}),
        (t("sb.presets.sea_view"),    {"fts": '"vista mar" OR "vista para o mar"'}),
        (t("sb.presets.clear"),       {"clear": True}),
    ]

    def _apply_preset(p: dict) -> None:
        if p.get("clear"):
            for k in (
                "__fts_query_preset", "__preset_score", "__preset_owner",
                "__preset_contact", "__preset_zone", "__preset_typology",
            ):
                st.session_state.pop(k, None)
            return
        if "fts" in p:
            st.session_state["__fts_query_preset"] = p["fts"]
        if "score_floor" in p:
            st.session_state["__preset_score"] = p["score_floor"]
        if "owner" in p:
            st.session_state["__preset_owner"] = p["owner"]
        if "contact" in p:
            st.session_state["__preset_contact"] = p["contact"]

    pcols = st.columns(2)
    for i, (label, payload) in enumerate(PRESETS):
        with pcols[i % 2]:
            if st.button(label, use_container_width=True, key=f"preset_{i}"):
                _apply_preset(payload)
                st.cache_data.clear()
                st.rerun()

    st.divider()
    with st.expander(t("sb.advanced"), expanded=False):
        st.markdown(f'<div class="lbl-section" style="margin-top:0;">{t("sb.advanced.data_origin")}</div>', unsafe_allow_html=True)
        # Canonical PT identifiers used by downstream filters; format_func translates display only.
        _DATA_MODES = ["Todos", "&#128994; Apenas reais", "&#128993; Apenas demo"]
        _DATA_LABEL = {"Todos": "opt.all", "&#128994; Apenas reais": "opt.real_only", "&#128993; Apenas demo": "opt.demo_only"}
        data_mode = st.radio("data_mode", _DATA_MODES, label_visibility="collapsed",
                             format_func=lambda v: t(_DATA_LABEL.get(v, "opt.all")))

        st.markdown(f'<div class="lbl-section">{t("sb.advanced.contact")}</div>', unsafe_allow_html=True)
        _CONTACT_MODES = ["Todos", "&#128222; Com telefone", "&#128241; Só telemóvel real", "&#9993; Com email", "&#9989; Qualquer contacto", "&#10060; Sem contacto"]
        _CONTACT_LABEL = {
            "Todos": "opt.all",
            "&#128222; Com telefone": "opt.with_phone",
            "&#128241; Só telemóvel real": "opt.mobile_only",
            "&#9993; Com email": "opt.with_email",
            "&#9989; Qualquer contacto": "opt.any_contact",
            "&#10060; Sem contacto": "opt.no_contact",
        }
        contact_mode = st.radio("contact_mode", _CONTACT_MODES, label_visibility="collapsed",
                                format_func=lambda v: t(_CONTACT_LABEL.get(v, "opt.all")))
        exclude_relay = st.checkbox(t("sb.advanced.exclude_relay"), value=False,
                                    help=t("sb.advanced.exclude_relay.help"))

        st.markdown(f'<div class="lbl-section">{t("sb.advanced.geo_typology")}</div>', unsafe_allow_html=True)
        ZONES = ["Todas as zonas", "Lisboa", "Cascais", "Sintra", "Almada", "Seixal", "Sesimbra"]
        _ZONE_LABEL = {"Todas as zonas": "opt.zone.all"}  # zone names stay literal
        sel_zone = st.selectbox(t("opt.zone.label"), ZONES,
                                format_func=lambda v: t(_ZONE_LABEL[v]) if v in _ZONE_LABEL else v)
        TYPOS = ["Todas as tipologias", "T0", "T1", "T2", "T3", "T4+", "Moradia"]
        _TYPO_LABEL = {"Todas as tipologias": "opt.typology.all"}
        _typo_extra = {"Moradia": {"pt": "Moradia", "en": "House"}}
        sel_typology = st.selectbox(
            t("opt.typology.label"), TYPOS,
            format_func=lambda v: (t(_TYPO_LABEL[v]) if v in _TYPO_LABEL
                                   else (_typo_extra[v].get(st.session_state.get("__lang", "pt"), v)
                                         if v in _typo_extra else v)),
        )
        _OWNER_MODES = ["Todos", "&#128100; Particular (FSBO)", "&#127970; Agência", "&#127959; Promotor", "&#10067; Desconhecido"]
        _OWNER_LABEL = {
            "Todos": "opt.all",
            "&#128100; Particular (FSBO)": "opt.owner.fsbo",
            "&#127970; Agência": "opt.owner.agency",
            "&#127959; Promotor": "opt.owner.developer",
            "&#10067; Desconhecido": "opt.owner.unknown",
        }
        _owner_default = _OWNER_MODES.index(st.session_state.get("__preset_owner", "Todos")) \
            if st.session_state.get("__preset_owner") in _OWNER_MODES else 0
        owner_mode = st.selectbox(t("opt.owner.label"), _OWNER_MODES, index=_owner_default,
                                  format_func=lambda v: t(_OWNER_LABEL.get(v, "opt.all")))
        _LEAD_TYPE_MODES = ["Todos", "&#127968; FSBO (venda)", "&#128273; FRBO (arrendamento)", "&#128101; Active Owner", "&#127970; Agência", "&#128679; Promotor"]
        _LEAD_TYPE_LABEL = {
            "Todos": "opt.all",
            "&#127968; FSBO (venda)": "opt.lead_type.fsbo",
            "&#128273; FRBO (arrendamento)": "opt.lead_type.frbo",
            "&#128101; Active Owner": "opt.lead_type.active",
            "&#127970; Agência": "opt.lead_type.agency",
            "&#128679; Promotor": "opt.lead_type.dev",
        }
        lead_type_mode = st.selectbox(t("opt.lead_type.label"), _LEAD_TYPE_MODES,
                                      format_func=lambda v: t(_LEAD_TYPE_LABEL.get(v, "opt.all")))
        _CSOURCE_MODES = ["Todos", "Direto", "Agência / Site", "Cross-portal"]
        _CSOURCE_LABEL = {"Todos": "opt.all", "Direto": "opt.csource.direct",
                          "Agência / Site": "opt.csource.agency_site", "Cross-portal": "opt.csource.cross"}
        csource_mode = st.selectbox(t("opt.csource.label"), _CSOURCE_MODES,
                                    format_func=lambda v: t(_CSOURCE_LABEL.get(v, "opt.all")))
        score_floor = st.slider(
            t("opt.score_min"), 0, 100,
            st.session_state.get("__preset_score", 0),
        )
    st.divider()
    if st.button(t("sb.refresh_btn"), use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.button(t("sb.market_run_btn"), use_container_width=True):
        with st.spinner(t("qa.update.spinner")):
            try:
                from pipeline.runner import PipelineRunner
                from scoring.scorer import Scorer
                r = PipelineRunner().run_full()
                Scorer().score_all_pending()
                st.cache_data.clear()
                st.success(f"+{r.leads_created} novas · {r.leads_updated} actualizadas")
            except Exception as e:
                st.error(f"Erro: {e}")
    st.markdown(
        '<div style="font-size:.62rem;color:var(--dust);text-align:center;'
        'padding:14px 0 8px;letter-spacing:.6px;">'
        '<span style="color:var(--mint);">◆</span> Patabrava &middot; v2.0'
        '</div>',
        unsafe_allow_html=True,
    )

zone_filter = None if sel_zone == "Todas as zonas" else sel_zone
typo_filter = None if sel_typology == "Todas as tipologias" else sel_typology
# Map radio selection → is_demo filter value passed to load_leads / LeadRepo
_demo_filter: bool | None = None
if data_mode == "&#128994; Apenas reais":
    _demo_filter = False
elif data_mode == "&#128993; Apenas demo":
    _demo_filter = True

# Map contact radio → contact filter string passed to LeadRepo
_contact_filter: str | None = None
_mobile_only: bool = False
if contact_mode == "&#128222; Com telefone":
    _contact_filter = "phone"
elif contact_mode == "&#128241; Só telemóvel real":
    _contact_filter = "phone"
    _mobile_only = True
elif contact_mode == "&#9993; Com email":
    _contact_filter = "email"
elif contact_mode == "&#9989; Qualquer contacto":
    _contact_filter = "any"
elif contact_mode == "&#10060; Sem contacto":
    _contact_filter = "none"

# Map owner_mode → owner_type filter string passed to LeadRepo
_owner_filter: str | None = None
if owner_mode == "&#128100; Particular (FSBO)":
    _owner_filter = "fsbo"
elif owner_mode == "&#127970; Agência":
    _owner_filter = "agency"
elif owner_mode == "&#127959; Promotor":
    _owner_filter = "developer"
elif owner_mode == "&#10067; Desconhecido":
    _owner_filter = "unknown"

# Map lead_type_mode → lead_type filter (applied post-load in-memory)
_lead_type_filter: str | None = None
if lead_type_mode == "&#127968; FSBO (venda)":
    _lead_type_filter = "fsbo"
elif lead_type_mode == "&#128273; FRBO (arrendamento)":
    _lead_type_filter = "frbo"
elif lead_type_mode == "&#128101; Active Owner":
    _lead_type_filter = "active_owner"
elif lead_type_mode == "&#127970; Agência":
    _lead_type_filter = "agency_listing"
elif lead_type_mode == "&#128679; Promotor":
    _lead_type_filter = "developer_listing"

# Map csource_mode → contact source category filter (applied post-load in load_leads)
_csource_filter: str | None = None
if csource_mode == "Direto":
    _csource_filter = "direto"
elif csource_mode == "Agência / Site":
    _csource_filter = "website"
elif csource_mode == "Cross-portal":
    _csource_filter = "cross_portal"


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "&#128202;  Dashboard":

    stats = load_stats()
    leads = load_leads(zone=zone_filter, typology=typo_filter, score_min=score_floor, is_demo=_demo_filter, contact=_contact_filter, owner_type=_owner_filter, csource_type=_csource_filter, fts_query=fts_query)
    if _lead_type_filter:
        leads = [l for l in leads if l.get("lead_type") == _lead_type_filter]
    if _mobile_only:
        leads = [l for l in leads if l.get("phone_type") == "mobile"]
    elif exclude_relay:
        leads = [l for l in leads if l.get("phone_type") != "relay"]
    df    = pd.DataFrame(leads) if leads else pd.DataFrame()

    hot_n  = stats.get("hot_count", 0)
    warm_n = stats.get("warm_count", 0)
    total  = stats.get("total_active", 0)
    avg_s  = stats.get("avg_score", 0)

    # ── Maison hero — editorial luxury opening (replaces legacy banner) ────
    _hot_today  = stats.get("hot_today",   0)
    _added_today = stats.get("added_today", 0)
    _phone_n    = stats.get("with_phone_count", 0)
    _edition_label = datetime.now().strftime("Edição de %d %b %Y").upper()
    # PT month-name normalisation (Python returns en/locale-dependent abbreviations)
    _pt_months = {"JAN":"JAN","FEB":"FEV","MAR":"MAR","APR":"ABR","MAY":"MAI","JUN":"JUN",
                  "JUL":"JUL","AUG":"AGO","SEP":"SET","OCT":"OUT","NOV":"NOV","DEC":"DEZ"}
    for en, pt in _pt_months.items():
        _edition_label = _edition_label.replace(en, pt)
    _hot_sub  = (t("maison.figure.sub.new",  n=_hot_today) if _hot_today
                 else t("maison.figure.sub.none"))

    st.markdown(
        f"""
        <section class="maison">
          <div class="maison-watermark"><span class="maison-watermark__text">Patabrava</span></div>
          <div class="maison-rule-top"></div>
          <div class="maison-rule-bot"></div>
          <div class="maison-grid">
            <div class="maison-col-left">
              <div class="maison-eyebrow">{t("maison.eyebrow")}</div>
              <h1 class="maison-title">{t("maison.title.line1")}<br/><em>{t("maison.title.line2")}</em></h1>
              <p class="maison-deck has-dropcap">{t("maison.deck")}</p>
              <div class="maison-byline">
                <span>{_edition_label}</span>
                <span>OLX &middot; Imovirtual</span>
                <span>{t("maison.byline.opps", n=total)}</span>
              </div>
            </div>
            <div class="maison-numerals">
              <div class="maison-figure">
                <div class="maison-figure-num is-hot has-shimmer">{hot_n}</div>
                <div class="maison-figure-meta">
                  <div class="maison-figure-lbl">{t("maison.figure.lbl")}</div>
                  <div class="maison-figure-sub">{_hot_sub}</div>
                </div>
              </div>
              <div class="maison-asterism">⁂</div>
              <div class="maison-stats">
                <div>
                  <div class="maison-stat-num is-warm">{warm_n}</div>
                  <div class="maison-stat-lbl">{t("maison.stat.warm")}</div>
                </div>
                <div>
                  <div class="maison-stat-num is-mint">{_phone_n}</div>
                  <div class="maison-stat-lbl">{t("maison.stat.with_phone")}</div>
                </div>
                <div>
                  <div class="maison-stat-num">{avg_s}</div>
                  <div class="maison-stat-lbl">{t("maison.stat.avg_score")}</div>
                </div>
              </div>
            </div>
          </div>
        </section>
        <div class="section-marker">
          <div class="section-marker__num">I</div>
          <div class="section-marker__title">{t("marker.daily_view")}</div>
          <div class="section-marker__rule"></div>
          <div class="section-marker__fleuron">❦</div>
          <div class="section-marker__caption">{t("marker.daily_view.caption")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Live run-progress strip (async pipeline) ──────────────────────────
    # When a scrape is in flight, the strip below replaces the quick-action
    # CTAs and shows live counters. The pipeline is a real OS subprocess —
    # the dashboard never blocks, even on a 30-min full run.
    from utils import run_state as _run_state
    _run_state.cleanup_stale()
    _run_info = _run_state.status()

    if _run_info.alive:
        # ── LIVE: editorial progress strip ────────────────────────────────
        elapsed_min, elapsed_sec = divmod(int(_run_info.elapsed_s), 60)
        elapsed_str = f"{elapsed_min:02d}:{elapsed_sec:02d}"
        zones_str = (
            f"{_run_info.zones_done}/{_run_info.zones_total}"
            if _run_info.zones_total else f"{_run_info.zones_done}"
        )
        last_zone = _run_info.last_zone or "—"
        st.markdown(
            f'<div class="run-live">'
            f'  <div class="run-live__pulse"></div>'
            f'  <div class="run-live__head">'
            f'    <span class="run-live__eyebrow">{t("run.live.eyebrow")}</span>'
            f'    <span class="run-live__sources">{" · ".join(_run_info.sources) or "—"}</span>'
            f'  </div>'
            f'  <div class="run-live__grid">'
            f'    <div><div class="run-live__num">{elapsed_str}</div><div class="run-live__lbl">{t("run.live.elapsed")}</div></div>'
            f'    <div><div class="run-live__num">{zones_str}</div><div class="run-live__lbl">{t("run.live.zones")}</div></div>'
            f'    <div><div class="run-live__num">{_run_info.listings}</div><div class="run-live__lbl">{t("run.live.listings")}</div></div>'
            f'    <div><div class="run-live__num run-live__num--zone">{last_zone}</div><div class="run-live__lbl">{t("run.live.last_zone")}</div></div>'
            f'    <div><div class="run-live__num {"run-live__num--err" if _run_info.blocked_hits else ""}">{_run_info.blocked_hits}</div><div class="run-live__lbl">{t("run.live.blocks")}</div></div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        rl1, rl2 = st.columns([2, 1])
        with rl1:
            st.caption("⟳  " + t("run.live.refresh"))
        with rl2:
            if st.button(f"⏹  {t('run.live.stop')}", key="run_stop_btn",
                         use_container_width=True):
                _run_state.stop()
                st.toast("✓  stop signal sent", icon="⏹")
                st.rerun()
        # Auto-refresh every 5 seconds while alive
        try:
            import time as _time
            _time.sleep(5)
            st.rerun()
        except Exception:
            pass

    elif _run_info.finished_at and (time.time() - _run_info.finished_at) < 60:
        # ── DONE: status banner for 60 seconds, then auto-collapse ────────
        # Also handles the "preflight rejected" case — we persist the
        # rejection in the same state file so it surfaces here.
        _pf = _run_state.get_preflight()
        if _pf and not _pf.ok and _pf.reason == "ip_blocked":
            portals_str = ", ".join(_pf.blocked_portals or [])
            st.markdown(
                f'<div class="run-done run-done--ko">'
                f'  <div class="run-done__eyebrow">⛔  {t("run.preflight.rejected")}</div>'
                f'  <div class="run-done__row" style="font-style:italic;">'
                f'    {t("run.preflight.ip_blocked", ip=_pf.public_ip or "?", portals=portals_str)}'
                f'  </div>'
                f'  <div class="run-done__row" style="font-size:11px;color:var(--smoke);">'
                f'    {t("run.preflight.suggestion")}'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(t("run.preflight.force"), key="run_force_btn"):
                _run_state.start(force=True)
                st.rerun()
        else:
            ok = _run_info.finished_ok is True
            eyebrow = t("run.done.eyebrow.ok") if ok else t("run.done.eyebrow.ko")
            klass = "run-done" if ok else "run-done run-done--ko"
            diff_html = ""
            if _run_info.leads_new:
                diff_html = (
                    f'<span style="color:#86d4a8;font-weight:600;">'
                    f'{t("run.diff.new", n=_run_info.leads_new)}</span>'
                )
            elif ok:
                diff_html = (
                    f'<span style="color:var(--smoke);">'
                    f'{t("run.diff.zero")}</span>'
                )
            st.markdown(
                f'<div class="{klass}">'
                f'  <div class="run-done__eyebrow">{eyebrow}</div>'
                f'  <div class="run-done__row">'
                f'    <span><b>{_run_info.zones_done}</b> zonas</span>'
                f'    <span><b>{_run_info.listings}</b> anúncios</span>'
                f'    <span>{int(_run_info.elapsed_s // 60)} min</span>'
                f'    {diff_html}'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Quick actions strip — the operator's "next step" toolbar ──────────
    # 4 columns of compact CTAs that map to the most common daily actions.
    # All buttons hook into existing flows (page change / pipeline run / export).
    st.markdown(f'<div class="qa-strip" data-eyebrow="{t("qa.heading")}">', unsafe_allow_html=True)
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button(t("qa.hot"), key="qa_hot", use_container_width=True, type="primary"):
            st.session_state["__page"] = "&#128293;  HOT Focus"
            st.rerun()
    with qa2:
        if st.button(t("qa.update"), key="qa_run", use_container_width=True,
                     disabled=_run_info.alive):
            if _run_info.alive:
                st.toast(t("run.already_running"), icon="⏳")
            else:
                _run_state.start()
                st.toast(t("run.starting"), icon="🚀")
                st.rerun()
    with qa3:
        if st.button(t("qa.export"), key="qa_export", use_container_width=True):
            try:
                from reports.generator import ReportGenerator
                path = ReportGenerator().export_csv(score_min=70)
                st.toast(t("qa.export.toast", p=path), icon="📋")
            except Exception as e:
                st.error(f"Erro: {e}")
    with qa4:
        if st.button(t("qa.map"), key="qa_map", use_container_width=True):
            st.session_state["__page"] = "&#128205;  Mapa & BI"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Empty state — guided onboarding when there's no real data yet ────
    if total == 0:
        st.markdown(
            f"""
            <section class="empty-stage">
              <div class="empty-stage__eyebrow">{t("empty.eyebrow")}</div>
              <h2 class="empty-stage__title">{t("empty.title.before")}<em>{t("empty.title.em")}</em>{t("empty.title.after")}</h2>
              <p class="empty-stage__deck">{t("empty.deck")}</p>
              <div class="empty-stage__steps">
                <div class="empty-stage__step">
                  <div class="empty-stage__step-num">i</div>
                  <div class="empty-stage__step-title">{t("empty.step1.title")}</div>
                  <div class="empty-stage__step-body">{t("empty.step1.body")}</div>
                </div>
                <div class="empty-stage__step">
                  <div class="empty-stage__step-num">ii</div>
                  <div class="empty-stage__step-title">{t("empty.step2.title")}</div>
                  <div class="empty-stage__step-body">{t("empty.step2.body")}</div>
                </div>
                <div class="empty-stage__step">
                  <div class="empty-stage__step-num">iii</div>
                  <div class="empty-stage__step-title">{t("empty.step3.title")}</div>
                  <div class="empty-stage__step-body">{t("empty.step3.body")}</div>
                </div>
              </div>
            </section>
            """,
            unsafe_allow_html=True,
        )

    # KPI metrics
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: st.metric(t("kpi.hot"),  hot_n,  delta=t("kpi.hot.delta", n=stats.get('hot_today', 0)),  help=t("kpi.hot.help"))
    with k2: st.metric(t("kpi.warm"), warm_n, help=t("kpi.warm.help"))
    with k3: st.metric(t("kpi.today"), stats.get("added_today", 0), help=t("kpi.today.help"))
    with k4:
        act = sum(v for k, v in stats.get("by_stage", {}).items() if k not in ("ganho", "perdido", "arquivado"))
        st.metric(t("kpi.in_negotiation"), act, help=t("kpi.in_negotiation.help"))
    with k5: st.metric(t("kpi.avg_score"), avg_s, help=t("kpi.avg_score.help"))

    # ── Contact availability row ───────────────────────────────────────────────
    ck1, ck2, ck3 = st.columns(3)
    with ck1: st.metric(t("kpi.with_phone"), stats.get("with_phone_count", 0), help=t("kpi.with_phone.help"))
    with ck2: st.metric(t("kpi.with_email"), stats.get("with_email_count", 0), help=t("kpi.with_email.help"))
    with ck3: st.metric(t("kpi.no_contact"), stats.get("no_contact_count", 0), help=t("kpi.no_contact.help"))

    # ── Contact confidence tier breakdown (from loaded leads, respects active filters) ──
    n_conf_high = sum(1 for l in leads if (l.get("contact_confidence") or 0) >= 70)
    n_conf_med  = sum(1 for l in leads if (l.get("contact_confidence") or 0) == 30)
    n_conf_zero = sum(1 for l in leads if (l.get("contact_confidence") or 0) == 0)
    ck4, ck5, ck6 = st.columns(3)
    with ck4: st.metric("🟢 Conf. Alta",    n_conf_high, help="contact_confidence >= 70 — telefone ou email confirmado")
    with ck5: st.metric("🟡 Conf. Media",   n_conf_med,  help="contact_confidence = 30 — nome disponivel, sem contacto directo")
    with ck6: st.metric("⚫ Sem Confianca",  n_conf_zero, help="contact_confidence = 0 — sem qualquer dado de contacto")

    # ── Contact source type breakdown (respects active filters) ──────────────
    n_src_direto  = sum(1 for l in leads if _match_csource(l.get("contact_source"), "direto"))
    n_src_website = sum(1 for l in leads if _match_csource(l.get("contact_source"), "website"))
    n_src_cross   = sum(1 for l in leads if _match_csource(l.get("contact_source"), "cross_portal"))
    ck7, ck8, ck9 = st.columns(3)
    with ck7: st.metric("📋 Direto",         n_src_direto,  help="Contacto do próprio anúncio — fonte mais fiável")
    with ck8: st.metric("🌐 Agência / Site",  n_src_website, help="Contacto obtido via website da agência (contact_source: website:*)")
    with ck9: st.metric("🔀 Cross-portal",    n_src_cross,   help="Contacto propagado de imóvel equivalente noutro portal (contact_source: cross_portal:*)")

    # ── Lead quality + type breakdown ─────────────────────────────────────────
    n_lq_high   = sum(1 for l in leads if l.get("lead_quality") == "high")
    n_lq_mid    = sum(1 for l in leads if l.get("lead_quality") == "medium")
    n_lt_fsbo   = sum(1 for l in leads if l.get("lead_type") == "fsbo")
    n_lt_frbo   = sum(1 for l in leads if l.get("lead_type") == "frbo")
    n_lt_agency = sum(1 for l in leads if l.get("lead_type") == "agency_listing")
    qk1, qk2, qk3, qk4, qk5 = st.columns(5)
    with qk1: st.metric("⭐ Alta qualidade", n_lq_high,   help="Telefone/WA + proprietário directo (FSBO/FRBO) — máxima accionabilidade")
    with qk2: st.metric("🟡 Média qualidade",n_lq_mid,    help="Email/site disponível, ou proprietário sem contacto directo")
    with qk3: st.metric("🏠 FSBO",          n_lt_fsbo,   help="For Sale By Owner — proprietário vende directamente")
    with qk4: st.metric("🔑 FRBO",          n_lt_frbo,   help="For Rent By Owner — proprietário arrenda directamente")
    with qk5: st.metric("🏢 Agências",       n_lt_agency, help="Anúncios de imobiliárias / mediadoras")

    st.divider()

    # ── Top Acionáveis ────────────────────────────────────────────────────────
    # Ranked by: contact_confidence → source quality → score → owner_type
    # Only leads with contact_confidence > 0 (i.e. at least one contact field)
    def _src_quality(src):
        s = src or ""
        if not s:                              return 0
        if s.startswith("website:"):           return 1
        if s.startswith("cross_portal:"):      return 2
        return 3   # direct portal source — most trustworthy

    _OT_QUALITY = {"fsbo": 2, "developer": 1, "unknown": 1, "agency": 0}

    _actionable = sorted(
        [l for l in leads if (l.get("contact_confidence") or 0) > 0],
        key=lambda l: (
            l.get("contact_confidence") or 0,
            _src_quality(l.get("contact_source")),
            l.get("score") or 0,
            _OT_QUALITY.get(l.get("owner_type") or "unknown", 1),
        ),
        reverse=True,
    )[:5]

    if _actionable:
        st.markdown(
            '<div class="section-marker" style="margin-top:var(--sp-5);">'
            '<div class="section-marker__num">II</div>'
            '<div class="section-marker__title">Lots du jour</div>'
            '<div class="section-marker__rule"></div>'
            '<div class="section-marker__fleuron">❦</div>'
            '<div class="section-marker__caption">Top accionáveis · ordem de prioridade</div>'
            '</div>'
            '<div class="lot-list">',
            unsafe_allow_html=True,
        )
        for rank, row in enumerate(_actionable, 1):
            lbl      = row.get("label", "COLD")
            area     = row.get("area_m2")
            area_txt = f' &middot; {area:.0f} m²' if area else ''
            days     = row.get("days_on_market", 0)
            st.markdown(
                f'<div class="card lot">'
                f'<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;">'
                f'{score_orb(row["score"], lbl)}'
                f'<div style="flex:1;min-width:160px;">'
                f'<div class="lot-title">{(row.get("title") or "—")[:65]}</div>'
                f'<div class="lot-meta">{row.get("typology") or "?"}'
                f' &middot; <em>{row.get("zone") or "?"}</em>{area_txt}</div>'
                f'</div>'
                f'<span class="price" style="font-size:1.05rem;">{fmt_price(row.get("price"))}</span>'
                f'{contact_chip(row.get("contact_phone"), row.get("contact_email"), row.get("contact_source"))}'
                f'{confidence_chip(row.get("contact_confidence"))}'
                f'{owner_chip(row.get("is_owner"), row.get("agency_name"), row.get("owner_type"))}'
                f'{lead_type_chip(row.get("lead_type"))}'
                f'{lead_quality_chip(row.get("lead_quality"))}'
                f'<span class="chip lot-days">⏱ {days}d</span>'
                f'</div>'
                f'{action_links(row.get("contact_phone"), row.get("contact_email"), row.get("sources"))}'
                f'</div>',
                unsafe_allow_html=True,
            )
            # ── Open detail magazine modal ───────────────────────────────
            _open_col, _mk_col = st.columns([1, 1])
            with _open_col:
                if st.button("✦  Abrir detalhe", key=f"dlg_open_{row['id']}",
                             use_container_width=True):
                    show_lead_dialog(row["id"])
            with _mk_col:
                if row.get("crm_stage") == "novo":
                    if st.button("📞 Marcar contactado", key=f"mk_{row['id']}",
                                 use_container_width=True):
                        from crm.manager import CRMManager
                        CRMManager().move_to_stage(row["id"], "contactado")
                        st.cache_data.clear()
                        st.rerun()
            _, _gm_col = st.columns([4, 2])
            with _gm_col:
                if st.button("💬 Mensagem", key=f"gb_{row['id']}", use_container_width=True):
                    _k = f"_gmsg_{row['id']}"
                    _was = st.session_state.get(_k, False)
                    st.session_state[_k] = not _was
                    if not _was:  # toggled ON → log once
                        from crm.manager import CRMManager
                        CRMManager().add_note(row["id"], "Mensagem de contacto sugerida gerada", "internal")
            if st.session_state.get(f"_gmsg_{row['id']}"):
                st.code(
                    _gen_outreach_msg(
                        row.get("typology"), row.get("zone"), row.get("price"),
                        row.get("owner_type"), row.get("contact_name"),
                        first_name=row.get("first_name"),
                    ),
                    language="",
                )
            with st.expander("📝 Nota rápida", expanded=False):
                _nk = st.session_state.get(f"_nk_{row['id']}", 0)
                _na, _nb = st.columns([5, 1])
                with _na:
                    _nota = st.text_input(
                        "nota", label_visibility="collapsed",
                        placeholder="Ex: Ligou, aceita visita. Pedir documentos...",
                        key=f"qn_{row['id']}_{_nk}",
                    )
                with _nb:
                    if st.button("💾", key=f"qnb_{row['id']}", use_container_width=True):
                        if _nota.strip():
                            from crm.manager import CRMManager
                            CRMManager().add_note(row["id"], _nota.strip())
                            st.session_state[f"_nk_{row['id']}"] = _nk + 1
                            st.toast("Nota guardada ✓")
                            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)  # close .lot-list
        st.divider()

    # ─── Batch actions panel ──────────────────────────────────────────────
    # Operator selects rows from the table below and runs one of:
    #   move CRM stage · mass-tag · export selection
    if not df.empty and "id" in df.columns:
        with st.expander("⚡ Batch actions (multi-selecção)", expanded=False):
            st.caption(
                "Marca leads na tabela abaixo (até 100), depois aplica uma "
                "ação de massa. As ações respeitam todos os filtros do sidebar."
            )
            # Compact selection grid
            df_pick = df[[
                "id", "score", "label", "typology", "zone",
                "price", "is_owner",
            ]].head(100).copy()
            df_pick.insert(0, "✓", False)
            edited = st.data_editor(
                df_pick,
                hide_index=True,
                use_container_width=True,
                disabled=[c for c in df_pick.columns if c != "✓"],
                key="batch_picker",
                height=320,
            )
            picked_ids = edited.loc[edited["✓"] == True, "id"].tolist()  # noqa: E712

            if picked_ids:
                st.success(f"{len(picked_ids)} leads selecionados")
                bcol1, bcol2, bcol3 = st.columns(3)

                with bcol1:
                    new_stage = st.selectbox(
                        "Mover para fase",
                        ["—", "novo", "contactado", "negociacao", "ganho", "perdido"],
                        key="batch_stage",
                    )
                    if new_stage != "—" and st.button(
                        "Aplicar fase", use_container_width=True, key="batch_apply_stage",
                    ):
                        from crm.manager import CRMManager
                        crm = CRMManager()
                        moved = 0
                        for lid in picked_ids:
                            try:
                                if crm.move_to_stage(int(lid), new_stage):
                                    moved += 1
                            except Exception:
                                pass
                        st.toast(f"✓ {moved} leads movidos", icon="📦")
                        st.cache_data.clear()
                        st.rerun()

                with bcol2:
                    if st.button("🔥 Marcar URGENTE",
                                 use_container_width=True, key="batch_priority"):
                        from storage.database import get_db
                        from storage.models import Lead
                        with get_db() as db:
                            db.query(Lead).filter(Lead.id.in_(picked_ids)).update(
                                {"priority_flag": True}, synchronize_session=False,
                            )
                            db.commit()
                        st.toast(f"✓ {len(picked_ids)} marcados", icon="🔥")
                        st.cache_data.clear()
                        st.rerun()
                    if st.button("🗄 Arquivar",
                                 use_container_width=True, key="batch_archive"):
                        from storage.database import get_db
                        from storage.models import Lead
                        with get_db() as db:
                            db.query(Lead).filter(Lead.id.in_(picked_ids)).update(
                                {"archived": True}, synchronize_session=False,
                            )
                            db.commit()
                        st.toast(f"✓ {len(picked_ids)} arquivados", icon="🗄")
                        st.cache_data.clear()
                        st.rerun()

                with bcol3:
                    csv_data = (
                        df[df["id"].isin(picked_ids)]
                        .to_csv(index=False)
                        .encode("utf-8")
                    )
                    st.download_button(
                        "⬇ Exportar selecção (CSV)",
                        data=csv_data,
                        file_name=f"selection_{len(picked_ids)}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="batch_export",
                    )
            st.divider()

    # Top HOT leads
    st.markdown('<div class="lbl-section">Oportunidades Prioritarias</div>', unsafe_allow_html=True)

    if df.empty:
        st.info("Sem oportunidades. Execute `python main.py seed-demo` para carregar dados de demonstracao.")
    else:
        # Leads with contact first (phone > email > none), then by score
        hot_with_contact    = [l for l in leads if l["label"] == "HOT" and l.get("has_contact")]
        hot_without_contact = [l for l in leads if l["label"] == "HOT" and not l.get("has_contact")]
        # Prioritise: HOT com contacto → HOT sem contacto → qualquer lead com contacto → fallback
        show = (hot_with_contact[:6] or hot_without_contact[:6] or
                [l for l in leads if l.get("has_contact")][:4] or leads[:4])
        ca, cb = st.columns(2, gap="medium")
        for i, row in enumerate(show):
            lbl  = row["label"]
            days = row.get("days_on_market", 0)
            area = row.get("area_m2")
            cond = f" · {row['condition']}" if row.get("condition") else ""
            sources_html = " ".join(src_pill(s["source"]) for s in (row.get("sources") or []))
            extras = ""
            if row.get("is_demo"):
                extras += '<span class="badge badge-demo">DEMO</span>'
            if (row.get("price_delta_pct") or 0) > 10:
                extras += '<span class="badge badge-drop">Reducao</span>'
            if row.get("is_owner"):
                extras += '<span class="badge badge-owner">Owner</span>'
            extras += contact_badge(row.get("contact_phone"), row.get("contact_email"))
            area_txt = f' · {area:.0f} m²' if area else ''
            demo_cls = " card-demo" if row.get("is_demo") else ""
            with (ca if i % 2 == 0 else cb):
                st.markdown(
                    f'<div class="card card-{lbl.lower()}{demo_cls}">'
                    f'<div style="display:flex;gap:12px;align-items:flex-start;">'
                    f'{score_orb(row["score"], lbl)}'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="margin-bottom:6px;">{badge_html(lbl)}{extras} '
                    f'<span style="font-size:.72rem;color:#56697e;">{row.get("typology","?")} · {row.get("zone","?")}{cond}</span> {sources_html}</div>'
                    f'<div style="font-size:.86rem;font-weight:600;color:#a89c80;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:8px;">{(row.get("title") or "—")[:70]}</div>'
                    f'<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:8px;">'
                    f'<span class="price">{fmt_price(row.get("price"))}</span>'
                    f'{delta_html(row.get("price_delta_pct"))}</div>'
                    f'<div>{owner_chip(row.get("is_owner"), row.get("agency_name"), row.get("owner_type"))} '
                    f'{lead_type_chip(row.get("lead_type"))} '
                    f'{lead_quality_chip(row.get("lead_quality"))} '
                    f'{contact_chip(row.get("contact_phone"), row.get("contact_email"), row.get("contact_source"))} '
                    f'{confidence_chip(row.get("contact_confidence"))} '
                    f'<span class="chip">&#9201; {days}d{area_txt}</span> '
                    f'{source_label_pill("via", row.get("discovery_source"))}</div>'
                    f'</div></div></div>',
                    unsafe_allow_html=True,
                )

    st.divider()

    if not df.empty:
        # Patabrava chart palette — synced with the CSS tokens above
        BG  = "rgba(11,16,32,0)"          # transparent — let the CSS frame show through
        GRD = "rgba(255,255,255,.05)"
        TXT = "#a89c80"                   # smoke
        FNT = dict(family="Inter", color=TXT, size=11)
        # Brand-coordinated mint→sky→violet palette for histogram + bars
        BRAND_MINT   = "#ddc269"
        BRAND_SKY    = "#38bdf8"
        BRAND_VIOLET = "#a78bfa"
        BRAND_ROSE   = "#fb7185"
        BRAND_AMBER  = "#fbbf24"

        # ─── TRENDS: 4 small charts over the last 30 days ─────────────────
        st.markdown('<div class="lbl-section">Tendência (últimos 30 dias)</div>', unsafe_allow_html=True)
        try:
            from reports.trends import (
                avg_score_per_day, contact_rate_per_day,
                hot_share_per_day, leads_per_day,
            )

            def _line_chart(data: list[dict], y_key: str, color: str,
                            title: str, suffix: str = "") -> go.Figure:
                xs = [d["date"] for d in data]
                ys = [d[y_key] for d in data]
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines+markers",
                    line=dict(color=color, width=2.5, shape="spline"),
                    marker=dict(size=5, color=color,
                                line=dict(width=1, color="rgba(255,255,255,.2)")),
                    fill="tozeroy",
                    fillcolor=color.replace(")", ",.12)").replace("rgb", "rgba")
                              if color.startswith("rgb") else f"{color}1f",
                    hovertemplate=f"{title}: <b>%{{y}}{suffix}</b><br>%{{x}}<extra></extra>",
                ))
                fig.update_layout(
                    paper_bgcolor=BG, plot_bgcolor=BG,
                    margin=dict(l=0, r=8, t=24, b=0),
                    height=170, font=FNT, showlegend=False,
                    title=dict(text=f"<b>{title}</b>", x=0.02, y=0.94,
                               font=dict(size=12, color="#d6cdb8")),
                    hoverlabel=dict(bgcolor="#141008",
                                    bordercolor="rgba(255,255,255,.12)",
                                    font=dict(family="Inter", color="#f5efe0")),
                    xaxis=dict(gridcolor=GRD, showgrid=False, tickformat="%d %b"),
                    yaxis=dict(gridcolor=GRD, showgrid=True, zeroline=False),
                )
                return fig

            tcol1, tcol2 = st.columns(2)
            with tcol1:
                st.plotly_chart(
                    _line_chart(leads_per_day(30), "count", BRAND_SKY,
                                "Leads novos por dia"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
                st.plotly_chart(
                    _line_chart(avg_score_per_day(30), "avg_score", BRAND_VIOLET,
                                "Score médio dos novos"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
            with tcol2:
                st.plotly_chart(
                    _line_chart(hot_share_per_day(30), "hot_pct", BRAND_ROSE,
                                "% HOT entre novos", suffix="%"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
                st.plotly_chart(
                    _line_chart(contact_rate_per_day(30), "contact_pct", BRAND_MINT,
                                "% com telefone", suffix="%"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
        except Exception as _trend_err:
            st.caption(f"⚠ Trend charts indisponíveis: {_trend_err}")

        st.divider()

        ch1, ch2 = st.columns(2, gap="large")
        with ch1:
            st.markdown('<div class="lbl-section">Distribuicao de Pontuacoes</div>', unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=df["score"], nbinsx=20,
                marker=dict(
                    color=BRAND_SKY,
                    opacity=.85,
                    line=dict(width=1, color="rgba(56,189,248,.4)"),
                ),
                hovertemplate="<b>Score</b> %{x}<br>%{y} leads<extra></extra>",
            ))
            fig.add_vline(x=75, line_dash="dot", line_color=BRAND_ROSE, line_width=1.6,
                          annotation_text="HOT", annotation_font_color=BRAND_ROSE, annotation_font_size=10)
            fig.add_vline(x=50, line_dash="dot", line_color=BRAND_AMBER, line_width=1.6,
                          annotation_text="WARM", annotation_font_color=BRAND_AMBER, annotation_font_size=10)
            fig.update_layout(
                paper_bgcolor=BG, plot_bgcolor=BG,
                margin=dict(l=0, r=8, t=8, b=0),
                height=210, font=FNT, showlegend=False,
                hoverlabel=dict(bgcolor="#141008", bordercolor="rgba(255,255,255,.12)",
                                font=dict(family="Inter", color="#f5efe0", size=11)),
                xaxis=dict(gridcolor=GRD, linecolor=GRD, zerolinecolor=GRD,
                           tickfont=dict(color=TXT)),
                yaxis=dict(gridcolor=GRD, linecolor=GRD, zerolinecolor=GRD,
                           tickfont=dict(color=TXT)),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        with ch2:
            st.markdown('<div class="lbl-section">Oportunidades por Zona</div>', unsafe_allow_html=True)
            zd = stats.get("by_zone", {})
            if zd:
                sz  = sorted(zd.items(), key=lambda x: x[1])
                mx  = max(v for _, v in sz) if sz else 1
                # Top zone gets mint accent, others fade through sky → violet → muted
                def _zone_color(idx: int, total: int) -> str:
                    if idx == total - 1:
                        return BRAND_MINT
                    if idx >= total - 3:
                        return BRAND_SKY
                    if idx >= total - 6:
                        return BRAND_VIOLET
                    return "rgba(198, 162, 100,.35)"
                clrs = [_zone_color(i, len(sz)) for i in range(len(sz))]
                fig2 = go.Figure(go.Bar(
                    x=[v for _, v in sz], y=[k for k, _ in sz], orientation="h",
                    marker=dict(color=clrs, line=dict(width=0)),
                    text=[str(v) for _, v in sz], textposition="outside",
                    textfont=dict(color="#f5efe0", size=11, family="Space Grotesk"),
                    hovertemplate="<b>%{y}</b><br>%{x} leads<extra></extra>",
                ))
                fig2.update_layout(
                    paper_bgcolor=BG, plot_bgcolor=BG,
                    margin=dict(l=0, r=40, t=8, b=0),
                    height=210, font=FNT, showlegend=False,
                    bargap=0.35,
                    hoverlabel=dict(bgcolor="#141008", bordercolor="rgba(255,255,255,.12)",
                                    font=dict(family="Inter", color="#f5efe0", size=11)),
                    xaxis=dict(gridcolor=GRD, showticklabels=False, zerolinecolor=GRD),
                    yaxis=dict(gridcolor="rgba(0,0,0,0)",
                               tickfont=dict(color="#d6cdb8", size=11, family="Inter")),
                )
                st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

        # Alertas + Funil
        st.divider()
        al_col, fu_col = st.columns([3, 2], gap="large")
        with al_col:
            st.markdown('<div class="lbl-section">Alertas Comerciais</div>', unsafe_allow_html=True)
            alerts = generate_alerts(leads)
            if alerts:
                for a in alerts[:5]:
                    st.markdown(alert_card_html(a), unsafe_allow_html=True)
            else:
                st.caption("Sem alertas activos.")
        with fu_col:
            st.markdown('<div class="lbl-section">Funil de Negociacao</div>', unsafe_allow_html=True)
            stage_cfg = [
                ("novo",        "📥 Novo",        "#3b82f6"),
                ("contactado",  "📞 Contactado",  "#8b5cf6"),
                ("negociacao",  "🤝 Negociacao",  "#f59e0b"),
                ("ganho",       "✅ Ganho",        "#a8861a"),
                ("perdido",     "❌ Perdido",      "#5c5240"),
            ]
            sd = stats.get("by_stage", {})
            for sk, sl, sc in stage_cfg:
                cnt = sd.get(sk, 0)
                st.markdown(
                    f'<div class="kanban-card" style="border-top:3px solid {sc};margin-bottom:8px;'
                    f'display:flex;justify-content:space-between;align-items:center;">'
                    f'<div style="font-size:.72rem;font-weight:700;color:#56697e;text-transform:uppercase;letter-spacing:.5px;">{sl}</div>'
                    f'<div style="font-size:1.8rem;font-weight:900;color:{sc};letter-spacing:-1.5px;">{cnt}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: OPORTUNIDADES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#127919;  Oportunidades":

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.opportunities.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.opportunities.title.before")}<em>{t("page.opportunities.title.em")}</em>{t("page.opportunities.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.opportunities.deck")}</p>'
        f'  <div class="maison-byline"><span>III &middot; {t("nav.opportunities.label")}</span><span>{t("page.opportunities.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    fa, fb, fc, fd = st.columns([1.2, 1.2, 1, 1])
    with fa: sel_label = st.selectbox("Classificacao", ["Todas", "🔴 HOT", "🟡 WARM", "🔵 COLD"])
    with fb: sel_stage = st.selectbox("Fase", ["Todas as fases", "novo", "contactado", "negociacao", "ganho", "perdido"])
    with fc: only_owner = st.checkbox("So proprietarios directos")
    with fd: only_drop  = st.checkbox("So com reducao de preco")

    lmap = {"Todas": None, "🔴 HOT": "HOT", "🟡 WARM": "WARM", "🔵 COLD": "COLD"}
    leads = load_leads(
        zone=zone_filter, typology=typo_filter, score_min=score_floor,
        stage=None if sel_stage == "Todas as fases" else sel_stage,
        label=lmap.get(sel_label),
        is_demo=_demo_filter,
        contact=_contact_filter,
        owner_type=_owner_filter,
        csource_type=_csource_filter,
        fts_query=fts_query,
    )
    if only_owner: leads = [l for l in leads if l.get("owner_type") in ("fsbo", None) or l.get("is_owner")]
    if only_drop:  leads = [l for l in leads if (l.get("price_delta_pct") or 0) > 0]
    if _lead_type_filter:
        leads = [l for l in leads if l.get("lead_type") == _lead_type_filter]
    if _mobile_only:
        leads = [l for l in leads if l.get("phone_type") == "mobile"]
    elif exclude_relay:
        leads = [l for l in leads if l.get("phone_type") != "relay"]

    hn = sum(1 for l in leads if l["label"] == "HOT")
    wn = sum(1 for l in leads if l["label"] == "WARM")
    cn = sum(1 for l in leads if l["label"] == "COLD")
    n_mobile = sum(1 for l in leads if l.get("phone_type") == "mobile")
    st.caption(f"{len(leads)} oportunidades · 🔴 {hn} HOT · 🟡 {wn} WARM · 🔵 {cn} COLD · 📱 {n_mobile} telemóvel real")

    if leads:
        df = pd.DataFrame(leads)
        dc = ["score", "label", "typology", "zone", "price", "price_delta_pct",
              "area_m2", "is_owner", "price_changes", "days_on_market", "crm_stage", "contact_phone"]
        dd = df[dc].copy()
        dd.columns = ["Pontuacao", "Class.", "Tipo", "Zona", "Preco (EUR)", "vs. Mercado %",
                      "Area m2", "Owner", "Reducoes", "Dias", "Fase", "Telefone"]
        st.dataframe(dd, use_container_width=True, height=420,
            column_config={
                "Pontuacao":     st.column_config.ProgressColumn("Pontuacao", min_value=0, max_value=100, format="%d pts"),
                "Class.":        st.column_config.TextColumn("Class.", width="small"),
                "Preco (EUR)":   st.column_config.NumberColumn("Preco", format="%.0f EUR"),
                "vs. Mercado %": st.column_config.NumberColumn("vs. Mercado", format="%.1f%%"),
                "Owner":         st.column_config.CheckboxColumn("Owner"),
                "Reducoes":      st.column_config.NumberColumn("Reducoes", format="%d"),
                "Dias":          st.column_config.NumberColumn("Dias", format="%d"),
            }, hide_index=True)

        # Intelligence detail
        st.divider()
        st.markdown('<div class="lbl-section">Relatorio de Inteligencia</div>', unsafe_allow_html=True)
        opts = [
            f"#{l['id']}  {l['score']}pts  [{l['label']}]  {l.get('typology','?')} {l.get('zone','?')}  —  {(l.get('title') or '')[:40]}"
            for l in leads[:60]
        ]
        sel = st.selectbox("Seleccionar oportunidade:", opts)

        if sel:
            sid = int(sel.split()[0].lstrip("#"))
            ld  = next((l for l in leads if l["id"] == sid), None)
            if ld:
                lbl   = ld["label"]
                area  = ld.get("area_m2")
                ppm2  = ld.get("price_per_m2")
                bench = ld.get("price_benchmark")
                sources_html = " ".join(src_pill(s["source"]) for s in (ld.get("sources") or []))

                motives = detect_motivation(ld.get("description", ""))
                motiv_html = " ".join(
                    f'<span style="background:rgba(139,92,246,.1);color:#a78bfa;border:1px solid rgba(139,92,246,.2);'
                    f'border-radius:20px;font-size:.64rem;font-weight:700;padding:2px 8px;">{e} {lb}</span>'
                    for lb, e in motives
                ) if motives else ""

                _demo_card_cls = " card-demo" if ld.get("is_demo") else ""
                _demo_badge    = '<span class="badge badge-demo">DEMO</span> ' if ld.get("is_demo") else ""
                _contact_bdg   = contact_badge(ld.get("contact_phone"), ld.get("contact_email"))
                # Confidence vars for intel-box
                _conf_c   = ld.get("contact_confidence") or 0
                _conf_lbl = "Alta" if _conf_c >= 100 else ("Boa" if _conf_c >= 70 else ("Media" if _conf_c >= 30 else "Sem conf."))
                _conf_clr = "#a8861a" if _conf_c >= 100 else ("#60a5fa" if _conf_c >= 70 else ("#f59e0b" if _conf_c >= 30 else "#5c5240"))
                # Nome / Apelido / Aniversario row (shown when first_name exists)
                _name_row = ""
                if ld.get("first_name"):
                    _bday = ld.get("birthday") or "—"
                    _name_row = (
                        '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px;">'
                        f'<div class="intel-box"><div class="intel-lbl">Nome</div><div class="intel-val" style="font-size:.85rem;">{ld["first_name"]}</div></div>'
                        f'<div class="intel-box"><div class="intel-lbl">Apelido</div><div class="intel-val" style="font-size:.85rem;">{ld.get("last_name") or "—"}</div></div>'
                        f'<div class="intel-box"><div class="intel-lbl">Aniversario</div><div class="intel-val" style="font-size:.85rem;">{_bday}</div></div>'
                        '</div>'
                    )
                st.markdown(
                    f'<div class="card{_demo_card_cls}" style="border-color:#243450;">'
                    f'<div style="display:flex;gap:14px;align-items:flex-start;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #1a2640;">'
                    f'{score_orb(ld["score"], lbl)}'
                    f'<div style="flex:1;">'
                    f'<div style="margin-bottom:5px;">{_demo_badge}{badge_html(lbl)} {_contact_bdg} '
                    f'<span style="font-size:.72rem;color:#56697e;">{ld.get("typology","?")} · {ld.get("zone","?")}</span> {sources_html}</div>'
                    f'<div style="font-size:.92rem;font-weight:700;color:#f1f5f9;">{(ld.get("title") or "—")[:80]}</div>'
                    f'{"<div style=font-size:.72rem;color:#56697e;margin-top:3px;>📍 "+ld["address"]+"</div>" if ld.get("address") else ""}'
                    f'{"<div style=margin-top:6px;>"+motiv_html+"</div>" if motiv_html else ""}'
                    f'</div></div>'
                    f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:12px;">'
                    f'<div class="intel-box"><div class="intel-lbl">Preco Pedido</div><div class="intel-val" style="font-size:.95rem;">{fmt_price(ld.get("price"))}</div></div>'
                    f'<div class="intel-box"><div class="intel-lbl">Preco/m2</div><div class="intel-val" style="font-size:.95rem;">{fmt_price(ppm2)}</div><div style="font-size:.6rem;color:#33485e;">bench {fmt_price(bench)}</div></div>'
                    f'<div class="intel-box"><div class="intel-lbl">Area</div><div class="intel-val" style="font-size:.95rem;">{f"{area:.0f} m2" if area else "—"}</div></div>'
                    f'<div class="intel-box"><div class="intel-lbl">Dias Mercado</div><div class="intel-val" style="font-size:.95rem;">{ld.get("days_on_market",0)}</div></div>'
                    f'<div class="intel-box"><div class="intel-lbl">Confianca</div>'
                    f'<div class="intel-val" style="font-size:.95rem;color:{_conf_clr};">{_conf_c}</div>'
                    f'<div style="font-size:.6rem;color:{_conf_clr};">{_conf_lbl}</div></div>'
                    f'</div>'
                    f'{_name_row}'
                    f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">'
                    f'{owner_chip(ld.get("is_owner"), ld.get("agency_name"), ld.get("owner_type"))}'
                    f'{lead_type_chip(ld.get("lead_type"))}'
                    f'{lead_quality_chip(ld.get("lead_quality"))}'
                    f'{contact_chip(ld.get("contact_phone"), ld.get("contact_email"), ld.get("contact_source"))}'
                    f'{source_label_pill("contacto", ld.get("contact_source"))}'
                    f'{source_label_pill("descoberta", ld.get("discovery_source"))}'
                    f'{"<span class=chip style=font-size:.62rem;color:#56697e;>📍 "+ld["parish"]+"</span>" if ld.get("parish") and ld["parish"] != ld.get("zone") else ""}'
                    f'</div>'
                    f'{action_links(ld.get("contact_phone"), ld.get("contact_email"))}'
                    f'{"<div style=margin-top:10px;background:#16202f;border:1px solid #1a2640;border-radius:8px;padding:10px 14px;font-size:.8rem;color:#a89c80;line-height:1.6;>"+ld["description"]+"</div>" if ld.get("description") else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if ld.get("crm_stage") == "novo":
                    _, _btn_col = st.columns([4, 2])
                    with _btn_col:
                        if st.button("📞 Marcar contactado", key=f"mkd_{ld['id']}", use_container_width=True):
                            from crm.manager import CRMManager
                            CRMManager().move_to_stage(ld["id"], "contactado")
                            st.cache_data.clear()
                            st.rerun()

                _, _gmd_col = st.columns([4, 2])
                with _gmd_col:
                    if st.button("💬 Mensagem", key=f"gbd_{ld['id']}", use_container_width=True):
                        _dk = f"_gmsgd_{ld['id']}"
                        _dwas = st.session_state.get(_dk, False)
                        st.session_state[_dk] = not _dwas
                        if not _dwas:  # toggled ON → log once
                            from crm.manager import CRMManager
                            CRMManager().add_note(ld["id"], "Mensagem de contacto sugerida gerada", "internal")
                if st.session_state.get(f"_gmsgd_{ld['id']}"):
                    st.code(
                        _gen_outreach_msg(
                            ld.get("typology"), ld.get("zone"), ld.get("price"),
                            ld.get("owner_type"), ld.get("contact_name"),
                        ),
                        language="",
                    )

                st.markdown('<div style="font-size:.7rem;color:#56697e;margin:8px 0 4px;">📝 Nota rápida</div>', unsafe_allow_html=True)
                _dnk = st.session_state.get(f"_dnk_{ld['id']}", 0)
                _da, _db = st.columns([5, 1])
                with _da:
                    _dnota = st.text_input(
                        "nota_d", label_visibility="collapsed",
                        placeholder="Ex: Proprietário confirmado. Visita agendada...",
                        key=f"qnd_{ld['id']}_{_dnk}",
                    )
                with _db:
                    if st.button("💾", key=f"qnbd_{ld['id']}", use_container_width=True):
                        if _dnota.strip():
                            from crm.manager import CRMManager
                            CRMManager().add_note(ld["id"], _dnota.strip())
                            st.session_state[f"_dnk_{ld['id']}"] = _dnk + 1
                            st.toast("Nota guardada ✓")
                            st.rerun()

                bd = ld.get("score_breakdown") or {}
                if bd:
                    st.markdown('<div class="lbl-section" style="margin-top:14px;">Composicao da Pontuacao</div>', unsafe_allow_html=True)
                    dims = [
                        ("price_opportunity",        "Oportunidade de Preco",   30),
                        ("urgency_signals",          "Sinais de Urgencia",      25),
                        ("owner_direct",             "Proprietario Directo",    25),
                        ("days_on_market",           "Tempo no Mercado",        15),
                        ("data_quality",             "Qualidade da Ficha",       5),
                        ("zone_priority",            "Prioridade de Zona",       5),
                        ("contact_quality",          "Qualidade do Contacto",   20),
                        ("phone_type_bonus",         "Tipo de Telefone",         8),
                        ("contact_confidence_bonus", "Confianca no Contacto",    3),
                        ("agency_penalty",           "Penalizacao Agencia",     10),
                        ("repeated_phone_penalty",   "Telefone Repetido",       10),
                    ]
                    for key, dlbl, mx in dims:
                        v    = bd.get(key, 0)
                        # contact_quality can be negative — clamp bar to 0, show red
                        pct  = max(0, int(v / mx * 100)) if mx else 0
                        if v < 0:
                            clr = "#ef4444"   # penalty → red
                        elif lbl == "HOT" and pct >= 70:
                            clr = "#f43f5e"
                        elif pct >= 50:
                            clr = "#3b82f6"
                        else:
                            clr = "#2e4268"
                        # show sign (+/-) for contact_quality to make penalty explicit
                        score_txt = (f"{v:+d}/{mx}" if key == "contact_quality" else f"{v}/{mx}")
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:10px;padding:4px 0;">'
                            f'<span style="font-size:.72rem;color:#a89c80;width:180px;flex-shrink:0;">{dlbl}</span>'
                            f'<div style="flex:1;background:#16202f;border-radius:4px;height:6px;overflow:hidden;">'
                            f'<div style="width:{pct}%;height:6px;border-radius:4px;background:{clr};"></div></div>'
                            f'<span style="font-size:.7rem;font-weight:700;color:{clr};width:40px;text-align:right;">{score_txt}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                if ld.get("sources"):
                    links = " ".join(
                        f'<a href="{s["url"]}" target="_blank" style="display:inline-block;background:#111827;border:1px solid #243450;'
                        f'border-radius:6px;padding:4px 12px;font-size:.72rem;color:#60a5fa;text-decoration:none;font-weight:700;">'
                        f'Ver em {s["source"].upper()} &rarr;</a>'
                        for s in ld["sources"]
                    )
                    st.markdown(f'<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">{links}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: CRM
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#128203;  CRM":

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.crm.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.crm.title.before")}<em>{t("page.crm.title.em")}</em>{t("page.crm.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.crm.deck")}</p>'
        f'  <div class="maison-byline"><span>IV &middot; CRM</span><span>{t("page.crm.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    from crm.manager import CRMManager, STAGES
    crm     = CRMManager()
    summary = crm.get_pipeline_summary()
    stage_cfg = {
        "novo":       ("📥 Novo",          "#3b82f6"),
        "contactado": ("📞 Contactado",    "#8b5cf6"),
        "negociacao": ("🤝 Em Negociacao", "#f59e0b"),
        "ganho":      ("✅ Ganho",          "#a8861a"),
        "perdido":    ("❌ Perdido",        "#5c5240"),
    }
    stage_keys = list(stage_cfg.keys())

    # Nurture pending counts per stage — small red dot on cards that need
    # follow-up. Cached for 60s to avoid re-querying on every interaction.
    @st.cache_data(ttl=60)
    def _nurture_pending_cached() -> dict:
        try:
            from pipeline.nurture import pending_per_stage
            return pending_per_stage()
        except Exception:
            return {}

    nurture_pending = _nurture_pending_cached()

    kcols = st.columns(len(stage_cfg), gap="small")
    for col, (sk, (sl, sc)) in zip(kcols, stage_cfg.items()):
        with col:
            pending_n = nurture_pending.get(sk, 0)
            badge_html_str = (
                f'<div style="position:absolute;top:8px;right:10px;'
                f'background:rgba(251,113,133,.18);color:#fb7185;'
                f'border:1px solid rgba(251,113,133,.4);border-radius:999px;'
                f'padding:1px 7px;font-size:.62rem;font-weight:800;'
                f'animation: glowPulse 2s infinite;">'
                f'⏰ {pending_n}'
                f'</div>'
                if pending_n else ''
            )
            st.markdown(
                f'<div class="kanban-card" style="border-top:3px solid {sc};position:relative;">'
                f'{badge_html_str}'
                f'<div style="font-size:2rem;font-weight:900;color:{sc};letter-spacing:-2px;">{summary.get(sk, 0)}</div>'
                f'<div style="font-size:.66rem;font-weight:700;color:#56697e;text-transform:uppercase;letter-spacing:.5px;margin-top:2px;">{sl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ─── View toggle: Kanban (drag-drop) | Lista detalhada ────────────────
    view_mode = st.radio(
        "view_mode_label",
        ["📌 Kanban (arrastar)", "📋 Lista detalhada"],
        index=0, horizontal=True, label_visibility="collapsed",
    )

    if view_mode.startswith("📌"):
        # ─── KANBAN drag-drop board ──────────────────────────────────────
        try:
            from streamlit_sortables import sort_items
        except ImportError:
            st.warning(
                "Drag-drop precisa de `streamlit-sortables`. "
                "Corre `pip install -r requirements.txt`."
            )
            st.stop()

        # Build column data — capped at 30 leads per column for snappy DnD.
        # Each item label is "ID#nnn · score · typology · zone · price"
        # so the user keeps context while dragging.
        items_per_stage: list[dict] = []
        id_to_lead: dict[int, object] = {}
        for sk, (sl, _sc) in stage_cfg.items():
            stage_leads = crm.get_leads_by_stage(sk)
            if _demo_filter is not None:
                stage_leads = [l for l in stage_leads if l.is_demo == _demo_filter]
            stage_leads = stage_leads[:30]   # bound DOM size for performance
            labels: list[str] = []
            for lead in stage_leads:
                emoji = label_emoji(lead.score_label or "COLD")
                tag = (
                    f"#{lead.id} {emoji} {lead.score}pts · "
                    f"{(lead.typology or '?'):>3} {(lead.zone or '?')[:14]:<14} · "
                    f"{fmt_price(lead.price)}"
                )
                labels.append(tag)
                id_to_lead[lead.id] = lead
            items_per_stage.append({"header": sl, "items": labels})

        st.caption(
            "Arrasta cartões entre colunas para mover de fase. "
            "Atualizações são guardadas automaticamente."
        )

        # Render the sortable multi-container — labels are unique by lead.id
        new_state = sort_items(
            items_per_stage,
            multi_containers=True,
            direction="vertical",
            key="crm_kanban_sort",
        )

        # Detect any item that moved → persist the new stage
        if new_state:
            moves = 0
            new_index: dict[str, str] = {}   # label → stage_key
            for col, sk in zip(new_state, stage_keys):
                for label in col["items"]:
                    new_index[label] = sk

            # Compare against original layout
            for col, sk in zip(items_per_stage, stage_keys):
                for label in col["items"]:
                    new_sk = new_index.get(label)
                    if new_sk and new_sk != sk:
                        # Parse lead.id from "#nnn ..."
                        try:
                            lead_id = int(label.split()[0].lstrip("#"))
                        except Exception:
                            continue
                        try:
                            crm.move_to_stage(lead_id, new_sk)
                            moves += 1
                        except Exception as e:
                            st.error(f"#{lead_id} → {new_sk}: {e}")
            if moves:
                st.toast(
                    f"✓ {moves} {'lead movido' if moves == 1 else 'leads movidos'}",
                    icon="✅",
                )
                st.cache_data.clear()
                st.rerun()

        st.divider()
        # Continue rendering the legacy "Detalhe por fase" section below
        # (inside the same elif branch) so the operator can drill into a card
    nav_col, detail_col = st.columns([1, 3])
    with nav_col:
        sel_stage = st.radio("Fase:", stage_keys, format_func=lambda s: stage_cfg[s][0])
    with detail_col:
        stage_leads = crm.get_leads_by_stage(sel_stage)
        if _demo_filter is not None:
            stage_leads = [l for l in stage_leads if l.is_demo == _demo_filter]
        sl_color    = stage_cfg[sel_stage][1]
        st.caption(f"{len(stage_leads)} oportunidades em {stage_cfg[sel_stage][0]}")

        if not stage_leads:
            st.info(f"Sem oportunidades em '{stage_cfg[sel_stage][0]}'.")
        else:
            for lead in stage_leads[:20]:
                lbl       = lead.score_label or "COLD"
                exp_title = f"{label_emoji(lbl)} #{lead.id} · {lead.score} pts · {lead.typology or '?'} {lead.zone or '?'} · {fmt_price(lead.price)}"
                with st.expander(exp_title, expanded=False):
                    # Badge + title (use markdown for HTML)
                    owner_badge = '<span class="badge badge-owner">Owner</span>' if lead.is_owner else ""
                    demo_badge  = '<span class="badge badge-demo">DEMO</span> '  if lead.is_demo  else ""
                    ct_badge    = contact_badge(lead.contact_phone, lead.contact_email)
                    st.markdown(
                        f'<div style="margin-bottom:8px;">{demo_badge}{badge_html(lbl)} {ct_badge} {owner_badge}</div>'
                        f'<div style="font-weight:600;color:#a89c80;font-size:.88rem;margin-bottom:10px;">{lead.title or "—"}</div>',
                        unsafe_allow_html=True,
                    )
                    # Motivation tags
                    desc = getattr(lead, "description", "") or ""
                    motives = detect_motivation(desc)
                    if motives:
                        motiv_html = " ".join(
                            f'<span style="background:rgba(139,92,246,.1);color:#a78bfa;border:1px solid rgba(139,92,246,.2);'
                            f'border-radius:20px;font-size:.64rem;font-weight:700;padding:2px 8px;">{e} {lb}</span>'
                            for lb, e in motives
                        )
                        st.markdown(f'<div style="margin-bottom:8px;">{motiv_html}</div>', unsafe_allow_html=True)
                    # Chips row
                    price_changes_chip = (
                        f'<span class="chip badge-drop" style="background:rgba(249,115,22,.08);color:#f97316;border-color:rgba(249,115,22,.2);">'
                        f'📉 {lead.price_changes} red.</span>'
                        if lead.price_changes else ""
                    )
                    st.markdown(
                        f'<div style="margin-bottom:8px;">'
                        f'{contact_chip(lead.contact_phone, lead.contact_email, getattr(lead, "contact_source", None))}'
                        f'{confidence_chip(getattr(lead, "contact_confidence", 0))}'
                        f'{source_label_pill("contacto", getattr(lead, "contact_source", None))}'
                        f'{owner_chip(lead.is_owner, lead.agency_name, getattr(lead, "owner_type", None))}'
                        f'<span class="chip">⏱ {lead.days_on_market} dias</span>'
                        f'{price_changes_chip}'
                        f'{source_label_pill("via", getattr(lead, "discovery_source", None))}</div>',
                        unsafe_allow_html=True,
                    )
                    if lead.address:
                        st.caption(f"📍 {lead.address}")
                    # Move stage + note
                    ea, eb = st.columns([3, 1])
                    with eb:
                        others = [s for s in stage_keys if s != sel_stage]
                        new_s  = st.selectbox("Mover para:", others,
                                               format_func=lambda s: stage_cfg[s][0],
                                               key=f"ss_{lead.id}")
                        if st.button("Mover", key=f"mv_{lead.id}", use_container_width=True):
                            if crm.move_to_stage(lead.id, new_s):
                                st.success(f"Movido para {stage_cfg[new_s][0]}")
                                st.cache_data.clear()
                                st.rerun()
                    nc1, nc2 = st.columns([3, 1])
                    with nc1:
                        note_txt = st.text_area(
                            "Registar interaccao:", height=72, key=f"nt_{lead.id}",
                            placeholder="Ex: Proprietario confirmado. Aceita 270k. Visita marcada para sexta...",
                        )
                    with nc2:
                        note_type = st.selectbox(
                            "Tipo:", ["call", "email", "visit", "whatsapp", "internal"],
                            key=f"ntype_{lead.id}",
                            format_func=lambda t: {
                                "call": "📞 Chamada", "email": "✉️ Email",
                                "visit": "🏠 Visita", "whatsapp": "💬 WhatsApp",
                                "internal": "📝 Nota",
                            }[t],
                        )
                        st.write("")
                        if st.button("💾 Guardar", key=f"sv_{lead.id}", use_container_width=True):
                            if note_txt.strip():
                                crm.add_note(lead.id, note_txt.strip(), note_type)
                                st.success("Interaccao registada ✓")

                    # Photo / Similar / Edit / Merge tabs
                    st.divider()
                    render_lead_extras(lead)

    st.divider()
    st.markdown('<div class="lbl-section">Historico de Interaccoes</div>', unsafe_allow_html=True)
    recent = crm.get_recent_activity(limit=15)
    if not recent:
        st.caption("Sem interaccoes registadas.")
    for note in recent:
        ic = {"call": "📞", "email": "✉️", "visit": "🏠", "whatsapp": "💬", "internal": "📝"}.get(note.note_type, "📝")
        dt = note.created_at.strftime("%d/%m  %H:%M") if note.created_at else "—"
        st.markdown(
            f'<div class="activity-row">'
            f'<div style="font-size:.9rem;flex-shrink:0;">{ic}</div>'
            f'<div><div style="font-size:.7rem;color:#56697e;margin-bottom:2px;">Lead #{note.lead_id} · {dt}</div>'
            f'<div>{note.note[:160]}</div></div></div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: HOT FOCUS — top 50 ordered by urgency, action-oriented
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#128293;  HOT Focus":

    from sqlalchemy import desc as _desc
    from storage.database import get_db as _get_db
    from storage.models import Lead as _Lead

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.hot.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.hot.title.before")}<em>{t("page.hot.title.em")}</em>{t("page.hot.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.hot.deck")}</p>'
        f'  <div class="maison-byline"><span>II &middot; HOT Focus</span><span>{t("page.hot.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    # ─── Filters bar ──────────────────────────────────────────────────────
    fcol1, fcol2, fcol3 = st.columns([1, 1, 2])
    with fcol1:
        hot_score_min = st.slider("Score mínimo", 50, 100, 60, key="hot_score_min")
    with fcol2:
        hot_owner_only = st.checkbox(
            "Só FSBO", value=True, key="hot_owner_only",
            help="Excluir agências (cobertura cheia em 'Oportunidades').",
        )
    with fcol3:
        st.caption(
            f"Filtros adicionais herdados da sidebar: zona={zone_filter or 'Todas'} · "
            f"tipologia={typo_filter or 'Todas'}"
        )

    with _get_db() as db:
        q = (
            db.query(_Lead)
            .filter(_Lead.archived == False)            # noqa: E712
            .filter(_Lead.is_demo  == False)            # noqa: E712
            .filter(_Lead.score    >= hot_score_min)
        )
        if zone_filter:
            q = q.filter(_Lead.zone == zone_filter)
        if typo_filter:
            q = q.filter(_Lead.typology == typo_filter)
        if hot_owner_only:
            q = q.filter(_Lead.owner_type == "fsbo")
        # Ordering: priority_flag first (price drops), then score, then
        # days_on_market (proxy for "the seller is impatient")
        leads_hot = (
            q.order_by(
                _desc(_Lead.priority_flag),
                _desc(_Lead.score),
                _desc(_Lead.days_on_market),
                _desc(_Lead.last_seen_at),
            )
            .limit(50)
            .all()
        )

    if not leads_hot:
        empty_state(
            icon="🔥",
            title="Nenhum lead HOT acima do critério.",
            hint="Baixa o score mínimo ou desliga 'Só FSBO' para ver mais.",
        )
    else:
        # Counter row + quick-stats
        with_phone = sum(1 for l in leads_hot if l.contact_phone)
        with_email = sum(1 for l in leads_hot if l.contact_email)
        with_wa    = sum(1 for l in leads_hot if l.contact_whatsapp)
        avg_score  = sum(l.score or 0 for l in leads_hot) / max(len(leads_hot), 1)
        kp1, kp2, kp3, kp4, kp5 = st.columns(5)
        with kp1: st.metric("Total",      len(leads_hot))
        with kp2: st.metric("Telefone",   f"{with_phone}/{len(leads_hot)}")
        with kp3: st.metric("Email",      f"{with_email}/{len(leads_hot)}")
        with kp4: st.metric("WhatsApp",   f"{with_wa}/{len(leads_hot)}")
        with kp5: st.metric("Score médio", f"{avg_score:.0f}")

        st.divider()
        # Compact action-rows — one card per lead with quick actions
        for lead in leads_hot:
            urgent_dot = (
                '<span class="live-dot" style="margin-right:6px;"></span>'
                if lead.priority_flag else ''
            )
            badges = []
            if lead.priority_flag:
                badges.append('<span class="badge badge-drop">🔻 PRICE DROP</span>')
            if lead.owner_type == "fsbo":
                badges.append('<span class="badge badge-owner">👤 FSBO</span>')
            if lead.seller_super_flag:
                badges.append('<span class="badge badge-warm">⚠ SUPER-SELLER</span>')
            badges.append(badge_html(lead.score_label or "COLD"))
            badges_html_str = " ".join(badges)

            st.markdown(
                f'<div class="card card-hot">'
                f'  <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">'
                f'    <span class="score-orb orb-hot">{lead.score or 0}</span>'
                f'    <div style="flex:1;">'
                f'      <div style="font-size:.95rem;font-weight:700;color:var(--ice);'
                f'                  margin-bottom:4px;line-height:1.3;">{urgent_dot}{(lead.title or "—")[:90]}</div>'
                f'      <div style="font-size:.78rem;color:var(--smoke);">'
                f'        #{lead.id} · {lead.typology or "?"} · {lead.zone or "?"} · '
                f'        <span class="price">{fmt_price(lead.price)}</span>'
                f'        {(" · " + str(lead.days_on_market) + "d on-market") if lead.days_on_market else ""}'
                f'      </div>'
                f'      <div style="margin-top:6px;">{badges_html_str}</div>'
                f'    </div>'
                f'  </div>',
                unsafe_allow_html=True,
            )
            quick_actions_bar(
                phone=lead.contact_phone,
                email=lead.contact_email,
                url=(lead.sources[0]["url"] if lead.sources else None),
                whatsapp=lead.contact_whatsapp or lead.contact_phone,
            )
            st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: SISTEMA — health, runs, backups, scheduler
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#129518;  Sistema":

    import os as _os
    from pathlib import Path as _Path
    from datetime import datetime as _dt

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.system.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.system.title.before")}<em>{t("page.system.title.em")}</em>{t("page.system.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.system.deck")}</p>'
        f'  <div class="maison-byline"><span>VIII &middot; {t("nav.system.label")}</span><span>{t("page.system.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    # ─── Run logs ─────────────────────────────────────────────────────────
    st.markdown('<div class="lbl-section">Últimos runs</div>', unsafe_allow_html=True)
    log_dir = _Path(__file__).resolve().parent.parent / "logs"
    log_files = sorted(
        log_dir.glob("run_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:8] if log_dir.exists() else []

    if log_files:
        rows = []
        for f in log_files:
            st_ = f.stat()
            mtime = _dt.fromtimestamp(st_.st_mtime)
            rows.append({
                "Ficheiro":  f.name,
                "Tamanho":   f"{st_.st_size / 1024:.0f} KB",
                "Modificado": mtime.strftime("%d/%m %H:%M"),
                "Idade":     _humanise_delta(_dt.now() - mtime),
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True, hide_index=True, height=240,
        )

        # Tail viewer for the most recent log
        latest = log_files[0]
        with st.expander(f"Tail · {latest.name}", expanded=False):
            try:
                content = latest.read_text(encoding="utf-8", errors="replace")
                # Keep the last ~120 lines for readability
                tail = "\n".join(content.splitlines()[-120:])
                st.code(tail, language="log")
            except Exception as e:
                st.error(f"Falhou a ler log: {e}")
    else:
        empty_state(
            icon="📂",
            title="Sem logs ainda",
            hint="Corre `python main.py run` para gerar atividade.",
        )

    st.divider()

    # ─── Backups ──────────────────────────────────────────────────────────
    st.markdown('<div class="lbl-section">Backups da base de dados</div>', unsafe_allow_html=True)
    bcol1, bcol2 = st.columns([1, 3])
    with bcol1:
        if st.button("Criar snapshot agora", use_container_width=True):
            try:
                from storage.backup import backup_now, prune_old_backups
                with st.spinner("Snapshotting..."):
                    res = backup_now(label="manual")
                    prune_old_backups(keep=14)
                if res.get("skipped"):
                    st.warning(f"Skipped: {res.get('reason') or res.get('error')}")
                else:
                    st.toast(f"✓ Snapshot {res['size_mb']} MB", icon="💾")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"Falhou: {e}")

    with bcol2:
        try:
            from storage.backup import list_backups
            backups = list_backups()
        except Exception:
            backups = []
        if backups:
            st.dataframe(
                pd.DataFrame([{
                    "Ficheiro":  b["name"],
                    "Tamanho":   f"{b['size_mb']} MB",
                    "Criado":    b["mtime"].strftime("%d/%m/%Y %H:%M"),
                } for b in backups[:14]]),
                use_container_width=True, hide_index=True, height=240,
            )
        else:
            st.caption("Sem snapshots ainda. Cria o primeiro com o botão.")

    st.divider()

    # ─── DB stats ─────────────────────────────────────────────────────────
    st.markdown('<div class="lbl-section">Base de dados</div>', unsafe_allow_html=True)
    try:
        from storage.database import get_db as _gdb
        from storage.models import Lead as _L, RawListing as _R, CRMNote as _N
        with _gdb() as db:
            n_leads  = db.query(_L).count()
            n_raw    = db.query(_R).count()
            n_notes  = db.query(_N).count()
            n_demo   = db.query(_L).filter(_L.is_demo == True).count()  # noqa: E712
            n_arch   = db.query(_L).filter(_L.archived == True).count() # noqa: E712
            n_phone  = db.query(_L).filter(
                _L.contact_phone.isnot(None), _L.contact_phone != ""
            ).count()
        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1: st.metric("Leads",        n_leads)
        with kc2: st.metric("Raw listings", n_raw)
        with kc3: st.metric("CRM notes",    n_notes)
        with kc4: st.metric("Com telefone", n_phone)
    except Exception as e:
        st.error(f"Falha ao obter stats: {e}")

    # DB file size
    try:
        from config.settings import settings as _s
        if _s.is_sqlite:
            db_path = _Path(_s.database_url.replace("sqlite:///", "", 1)).resolve()
            if db_path.exists():
                st.caption(
                    f"📁 {db_path.name} · {db_path.stat().st_size / (1024*1024):.1f} MB · {db_path}"
                )
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: ATIVIDADE — chronological feed of every interesting event
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#128240;  Atividade":

    from sqlalchemy import desc as _d
    from datetime import datetime as _dt, timedelta as _td

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.activity.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.activity.title.before")}<em>{t("page.activity.title.em")}</em>{t("page.activity.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.activity.deck")}</p>'
        f'  <div class="maison-byline"><span>V &middot; {t("nav.activity.label")}</span><span>{t("page.activity.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    feed_window = st.select_slider(
        "Janela",
        options=["24h", "3 dias", "7 dias", "30 dias"],
        value="7 dias",
    )
    hours_map = {"24h": 24, "3 dias": 72, "7 dias": 168, "30 dias": 720}
    cutoff = _dt.utcnow() - _td(hours=hours_map[feed_window])

    from storage.database import get_db as _gdb
    from storage.models import Lead as _L, CRMNote as _N
    with _gdb() as db:
        recent_leads = (
            db.query(_L)
            .filter(_L.first_seen_at >= cutoff)
            .filter(_L.is_demo == False)        # noqa: E712
            .order_by(_d(_L.first_seen_at))
            .limit(200).all()
        )
        recent_notes = (
            db.query(_N, _L)
            .join(_L, _L.id == _N.lead_id)
            .filter(_N.created_at >= cutoff)
            .order_by(_d(_N.created_at))
            .limit(300).all()
        )

    # Build a unified timeline: lead-arrived events + note events
    events: list[dict] = []
    for l in recent_leads:
        events.append({
            "ts":    l.first_seen_at,
            "kind":  "new_lead",
            "icon":  "🆕",
            "color": "var(--mint)",
            "title": f"Novo lead · {l.typology or '?'} {l.zone or ''}",
            "body":  (l.title or "")[:130],
            "lead":  l,
        })
    NOTE_ICONS = {
        "change_detected": ("✏️",  "var(--violet)"),
        "listing_dropped": ("❌",  "var(--rose)"),
        "nurture":         ("⏰",  "var(--amber)"),
        "call":            ("📞", "var(--mint)"),
        "email":           ("✉",  "var(--sky)"),
        "whatsapp":        ("💬", "var(--mint)"),
        "visit":           ("📍", "var(--violet)"),
        "internal":        ("📝", "var(--smoke)"),
    }
    for n, l in recent_notes:
        ic, col = NOTE_ICONS.get(n.note_type, ("•", "var(--smoke)"))
        # Strip the JSON tail of change_detected notes for the feed
        body = n.note or ""
        if "[changeset]" in body:
            body = body.split("[changeset]")[0].strip()
        events.append({
            "ts":    n.created_at,
            "kind":  n.note_type,
            "icon":  ic,
            "color": col,
            "title": f"{n.note_type.replace('_', ' ').title()} · #{l.id}",
            "body":  body[:200],
            "lead":  l,
        })

    events.sort(key=lambda e: e["ts"], reverse=True)

    if not events:
        empty_state(
            icon="📭",
            title="Sem atividade ainda",
            hint="Lança o pipeline ou aumenta a janela acima.",
        )
    else:
        st.caption(f"{len(events)} eventos nos últimos {feed_window}")
        for ev in events[:200]:
            ts_str = ev["ts"].strftime("%d %b %H:%M") if ev["ts"] else "—"
            st.markdown(
                f'<div class="card" style="padding:12px 16px;margin-bottom:8px;'
                f'border-left:3px solid {ev["color"]};">'
                f'  <div style="display:flex;align-items:center;gap:10px;'
                f'              margin-bottom:4px;">'
                f'    <span style="font-size:1.05rem;">{ev["icon"]}</span>'
                f'    <span style="font-weight:700;color:var(--ice);'
                f'                  font-size:.88rem;">{ev["title"]}</span>'
                f'    <span style="margin-left:auto;color:var(--smoke);'
                f'                  font-size:.72rem;font-family:Space Grotesk;">{ts_str}</span>'
                f'  </div>'
                f'  <div style="color:var(--fog);font-size:.82rem;'
                f'              line-height:1.4;">{ev["body"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: MAPA & BI — heatmap + funnel + agency leaderboard
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#128205;  Mapa & BI":

    from reports.bi import (
        agency_leaderboard,
        conversion_funnel,
        recent_signal_summary,
        zone_heatmap_data,
    )

    summary = recent_signal_summary(window_days=7)

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.map.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.map.title.before")}<em>{t("page.map.title.em")}</em>{t("page.map.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.map.deck")}</p>'
        f'  <div class="maison-stats" style="grid-template-columns:repeat(5,minmax(0,1fr));margin-top:var(--sp-4);">'
        f'    <div><div class="maison-stat-num">{summary["new_leads_7d"]}</div><div class="maison-stat-lbl">{t("page.map.stat.new7d")}</div></div>'
        f'    <div><div class="maison-stat-num is-rose">{summary["new_hot_7d"]}</div><div class="maison-stat-lbl">{t("page.map.stat.newhot")}</div></div>'
        f'    <div><div class="maison-stat-num is-warm">{summary["price_drops_7d"]}</div><div class="maison-stat-lbl">{t("page.map.stat.drops")}</div></div>'
        f'    <div><div class="maison-stat-num">{summary["super_sellers"]}</div><div class="maison-stat-lbl">{t("page.map.stat.super")}</div></div>'
        f'    <div><div class="maison-stat-num is-mint">{summary["contacted"]}</div><div class="maison-stat-lbl">{t("page.map.stat.contacted")}</div></div>'
        f'  </div>'
        f'  <div class="maison-byline"><span>VI &middot; {t("nav.map.label")}</span><span>{t("page.map.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    # ─── Heatmap (luxury monochrome cartography) ──────────────────────────
    st.markdown(
        '<div class="section-marker" style="margin-top:var(--sp-5);">'
        '<div class="section-marker__num">i</div>'
        '<div class="section-marker__title">Carta geográfica</div>'
        '<div class="section-marker__rule"></div>'
        '<div class="section-marker__fleuron">❦</div>'
        '<div class="section-marker__caption">Densidade · score · €/m²</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    try:
        import folium
        from streamlit_folium import st_folium

        zone_data = zone_heatmap_data(min_count=1)
        if zone_data:
            avg_lat = sum(z["lat"] for z in zone_data) / len(zone_data)
            avg_lon = sum(z["lon"] for z in zone_data) / len(zone_data)
            # Pure cartography — no labels — gives an editorial monochrome plate
            # feel. Labels removed via the `_no_labels` variant of CartoDB
            # dark; we'll re-add labels selectively only when zoomed in.
            m = folium.Map(
                location=[avg_lat, avg_lon],
                zoom_start=10,
                tiles=None,
                control_scale=False,
                zoom_control=True,
            )
            folium.TileLayer(
                tiles="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}@2x.png",
                attr="© OpenStreetMap · © CARTO",
                name="Carto monochrome",
                control=False,
                max_zoom=20,
            ).add_to(m)
            folium.TileLayer(
                tiles="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png",
                attr="© OpenStreetMap · © CARTO",
                name="labels",
                control=False,
                opacity=0.4,
            ).add_to(m)

            mx = max(z["count"] for z in zone_data) or 1
            for z in zone_data:
                radius = 12 + 32 * (z["count"] / mx)
                avg = z["avg_score"]
                # Tier-aware palette — keep semantic intent but warmer hues
                if avg >= 60:
                    stroke, fill, glow = "#ffb4be", "rgba(251,113,133,.45)", "#fb7185"
                    tier = "HOT"
                elif avg >= 40:
                    stroke, fill, glow = "#ffe6c2", "rgba(238,218,160,.45)", "#ddc269"
                    tier = "WARM"
                else:
                    stroke, fill, glow = "#a89c80", "rgba(120,108,82,.30)", "#786c52"
                    tier = "COLD"
                pm2 = int(z["avg_price_per_m2"] or 0)
                pm2_fmt = f"{pm2:,}".replace(",", " ") if pm2 else "—"
                folium.CircleMarker(
                    location=[z["lat"], z["lon"]],
                    radius=radius,
                    color=stroke,
                    fill=True,
                    fill_color=fill,
                    fill_opacity=0.55,
                    weight=1.4,
                    popup=folium.Popup(
                        f"<div style='font-family:Inter,sans-serif;color:#1a1106;'>"
                        f"<div style='font-size:9.5px;font-weight:600;letter-spacing:.22em;"
                        f"text-transform:uppercase;color:{glow};margin-bottom:6px;'>{tier}</div>"
                        f"<div style='font-family:Fraunces,Georgia,serif;font-size:20px;"
                        f"font-weight:420;letter-spacing:-.012em;line-height:1;color:#1a1106;"
                        f"margin-bottom:10px;'>{z['zone']}</div>"
                        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px 18px;"
                        f"font-size:11px;'>"
                        f"<div><div style='font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;"
                        f"color:#786c52;'>Leads</div><b style='font-family:Fraunces,Georgia,serif;"
                        f"font-style:italic;font-size:18px;font-weight:380;color:#1a1106;'>{z['count']}</b></div>"
                        f"<div><div style='font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;"
                        f"color:#786c52;'>HOT</div><b style='font-family:Fraunces,Georgia,serif;"
                        f"font-style:italic;font-size:18px;font-weight:380;color:#fb7185;'>{z['hot_count']}</b></div>"
                        f"<div><div style='font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;"
                        f"color:#786c52;'>Score</div><b style='font-family:Fraunces,Georgia,serif;"
                        f"font-style:italic;font-size:18px;font-weight:380;color:#1a1106;'>{z['avg_score']:.1f}</b></div>"
                        f"<div><div style='font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;"
                        f"color:#786c52;'>€/m²</div><b style='font-family:Fraunces,Georgia,serif;"
                        f"font-style:italic;font-size:18px;font-weight:380;color:#b89030;'>{pm2_fmt}</b></div>"
                        f"</div></div>",
                        max_width=280,
                    ),
                    tooltip=z["zone"],
                ).add_to(m)
            st_folium(m, height=480, use_container_width=True, returned_objects=[])
        else:
            st.caption("Sem dados geográficos suficientes para desenhar o mapa.")
    except ImportError:
        st.warning(
            "Mapa requer `folium` + `streamlit-folium`. "
            "Corre `pip install -r requirements.txt`."
        )

    st.divider()

    # ─── Funnel + Leaderboard side-by-side ────────────────────────────────
    f_col, l_col = st.columns([2, 3], gap="large")

    with f_col:
        st.markdown('<div class="lbl-section">Funil de conversão</div>', unsafe_allow_html=True)
        funnel = conversion_funnel()
        if funnel:
            top_count = max((r["count"] for r in funnel), default=1)
            for row in funnel:
                pct = row["count"] / top_count if top_count else 0
                bar_w = max(int(100 * pct), 3)
                stage_color = {
                    "captured":   "#38bdf8",
                    "qualified":  "#a78bfa",
                    "contacted":  "#fbbf24",
                    "interested": "#fb923c",
                    "negotiating":"#f472b6",
                    "closed":     "#ddc269",
                }.get(row["key"], "#a89c80")
                st.markdown(
                    f'<div style="margin-bottom:14px;">'
                    f'  <div style="display:flex;justify-content:space-between;'
                    f'              align-items:baseline;margin-bottom:4px;">'
                    f'    <span style="color:var(--fog);font-weight:600;font-size:.88rem;">{row["label"]}</span>'
                    f'    <span style="color:var(--smoke);font-family:\'Space Grotesk\';'
                    f'                  font-weight:700;font-size:.88rem;">{row["count"]}</span>'
                    f'  </div>'
                    f'  <div style="background:rgba(11,16,32,.6);border-radius:6px;height:10px;'
                    f'              overflow:hidden;border:1px solid rgba(255,255,255,.04);">'
                    f'    <div style="height:100%;width:{bar_w}%;'
                    f'                background:linear-gradient(90deg, {stage_color}, transparent 95%);'
                    f'                box-shadow:0 0 8px -1px {stage_color}; border-radius:6px;"></div>'
                    f'  </div>'
                    f'  <div style="font-size:.65rem;color:var(--dust);margin-top:3px;">'
                    f'    {row["pct_of_top"]}% do topo'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Pipeline ainda vazio.")

    with l_col:
        st.markdown('<div class="lbl-section">Top agências por volume</div>', unsafe_allow_html=True)
        leaders = agency_leaderboard(limit=20, min_listings=3)
        if leaders:
            df_leaders = pd.DataFrame(leaders)
            df_leaders.columns = [
                "Agência", "Listings", "HOT", "Score méd.", "Preço méd.",
                "€/m² méd.", "% c/ contacto",
            ]
            st.dataframe(
                df_leaders,
                use_container_width=True,
                height=440,
                hide_index=True,
                column_config={
                    "Listings":      st.column_config.NumberColumn(format="%d"),
                    "HOT":           st.column_config.NumberColumn(format="%d"),
                    "Score méd.":    st.column_config.NumberColumn(format="%.1f"),
                    "Preço méd.":    st.column_config.NumberColumn(format="€%d"),
                    "€/m² méd.":     st.column_config.NumberColumn(format="€%d"),
                    "% c/ contacto": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
                },
            )
        else:
            st.caption("Sem agências com volume mínimo de 3 listagens.")

    st.divider()

    # ─── PDF report download ──────────────────────────────────────────────
    st.markdown('<div class="lbl-section">Relatório PDF semanal</div>', unsafe_allow_html=True)
    rcol1, rcol2 = st.columns([1, 3])
    with rcol1:
        if st.button("Gerar relatório", use_container_width=True):
            try:
                from reports.trend_pdf import generate_trend_report
                with st.spinner("A compor o PDF..."):
                    path = generate_trend_report(days=7)
                st.session_state["__last_trend_pdf"] = str(path)
                st.success(f"Pronto: {path.name}")
            except Exception as e:
                st.error(f"Falha: {e}")
    with rcol2:
        last_path = st.session_state.get("__last_trend_pdf")
        if last_path:
            from pathlib import Path as _P
            p = _P(last_path)
            if p.exists():
                with open(p, "rb") as fh:
                    st.download_button(
                        "Descarregar último PDF",
                        data=fh.read(),
                        file_name=p.name,
                        mime="application/pdf",
                        use_container_width=True,
                    )

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: MOTOR
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#128268;  Pre-Market":

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.premarket.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.premarket.title.before")}<em>{t("page.premarket.title.em")}</em>{t("page.premarket.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.premarket.deck")}</p>'
        f'  <div class="maison-byline"><span>VII &middot; {t("nav.premarket.label")}</span><span>{t("page.premarket.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    # ── Load signals ──────────────────────────────────────────────────────────
    @st.cache_data(ttl=120)
    def load_premarket_signals():
        try:
            from storage.database import get_db
            from storage.models import PremktSignal
            from sqlalchemy import select, desc
            rows = []
            with get_db() as db:
                signals = (
                    db.execute(
                        select(PremktSignal)
                        .order_by(desc(PremktSignal.signal_score), desc(PremktSignal.created_at))
                        .limit(200)
                    ).scalars().all()
                )
                for s in signals:
                    rows.append({
                        "id":           s.id,
                        "signal_type":  s.signal_type,
                        "source":       s.source,
                        "signal_text":  s.signal_text,
                        "name":         s.name,
                        "company":      s.company,
                        "role":         s.role,
                        "location_raw": s.location_raw,
                        "zone":         s.zone,
                        "url":          s.url,
                        "signal_score": s.signal_score,
                        "promoted":     s.promoted,
                        "created_at":   s.created_at,
                    })
            return rows
        except Exception:
            return []

    signals = load_premarket_signals()

    # ── Signal type chip helper ───────────────────────────────────────────────
    _SIG_CHIP_CFG = {
        "building_permit":           ("1a2a3b", "a78bfa", "Licenca Obras",    "FF"),
        "renovation_ad_homeowner":   ("1a2a1a", "4ade80", "Anuncio Remodel.", "FF"),
        "renovation_ad_generic":     ("1a2a1a", "86efac", "Remodelacao",      "90"),
        "linkedin_city_change":      ("1a231f", "34d399", "Mudanca Cidade",   "FF"),
        "linkedin_job_change":       ("1a1f2a", "60a5fa", "Mudanca Prof.",    "AA"),
        "contractor_search_post":    ("211a2a", "c084fc", "Procura Empreit.", "FF"),
    }

    def signal_type_chip(signal_type: str) -> str:
        cfg  = _SIG_CHIP_CFG.get(signal_type, ("1a1a1a", "94a3b8", signal_type, "AA"))
        bg, fg, label, _ = cfg
        return (
            f'<span style="background:#{bg};color:#{fg};border:1px solid #{fg}44;'
            f'border-radius:5px;padding:2px 8px;font-size:.68rem;font-weight:700;'
            f'letter-spacing:.3px;">{label}</span>'
        )

    def source_chip(source: str) -> str:
        labels = {
            "olx":                  ("OLX",       "f97316"),
            "custojusto":           ("CustoJusto", "fb923c"),
            "cm_lisboa":            ("CM Lisboa",  "a78bfa"),
            "duckduckgo_linkedin":  ("LinkedIn",   "60a5fa"),
        }
        label, colour = labels.get(source, (source, "94a3b8"))
        return (
            f'<span style="color:#{colour};font-size:.68rem;font-weight:700;">'
            f'{label}</span>'
        )

    def score_bar(score: int) -> str:
        if score >= 75:
            colour = "a78bfa"
        elif score >= 55:
            colour = "4ade80"
        else:
            colour = "60a5fa"
        pct = min(score, 100)
        return (
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<div style="width:50px;background:#16202f;border-radius:3px;height:5px;">'
            f'<div style="width:{pct}%;height:5px;background:#{colour};border-radius:3px;"></div>'
            f'</div>'
            f'<span style="font-size:.72rem;font-weight:800;color:#{colour};">{score}</span>'
            f'</div>'
        )

    # ── KPI row ───────────────────────────────────────────────────────────────
    total_sigs   = len(signals)
    permits      = sum(1 for s in signals if s["signal_type"] == "building_permit")
    renovations  = sum(1 for s in signals if "renovation" in s["signal_type"])
    linkedin_sig = sum(1 for s in signals if "linkedin" in s["signal_type"])
    promoted     = sum(1 for s in signals if s["promoted"])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Sinais",       total_sigs)
    k2.metric("Licencas Obras",     permits,     help="CM Lisboa building permits (last 90 days)")
    k3.metric("Anuncios Remodel.",  renovations, help="OLX + CustoJusto renovation demand ads")
    k4.metric("Sinais LinkedIn",    linkedin_sig,help="Career/city change signals (DuckDuckGo)")
    k5.metric("Promovidos a Lead",  promoted)

    st.markdown("<hr/>", unsafe_allow_html=True)

    if not signals:
        st.markdown(
            '<div class="card" style="text-align:center;padding:2.5rem;">'
            '<div style="font-size:2rem;margin-bottom:.5rem;">📡</div>'
            '<div style="font-size:.9rem;font-weight:700;color:#f1f5f9;margin-bottom:.4rem;">'
            'Nenhum sinal pre-mercado encontrado</div>'
            '<div style="font-size:.78rem;color:#56697e;">Execute o scan para descobrir proprietarios que podem vender em breve.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("Executar Pre-Market Scan", use_container_width=True):
            with st.spinner("A pesquisar sinais pre-mercado..."):
                try:
                    from premarket.enricher import PremktEnricher
                    result = PremktEnricher().run()
                    st.cache_data.clear()
                    st.success(f"+{result.new_signals} novos sinais encontrados")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
    else:
        # ── Filters ───────────────────────────────────────────────────────────
        fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1])
        with fc1:
            _SIG_TYPES = ["Todos os tipos", "building_permit", "renovation_ad_homeowner",
                          "renovation_ad_generic", "linkedin_city_change",
                          "linkedin_job_change", "contractor_search_post"]
            sig_type_filter = st.selectbox("Tipo de sinal", _SIG_TYPES, key="pm_type")
        with fc2:
            zone_opts = ["Todas as zonas"] + sorted({s["zone"] for s in signals if s["zone"]})
            pm_zone   = st.selectbox("Zona", zone_opts, key="pm_zone")
        with fc3:
            src_opts  = ["Todas as fontes"] + sorted({s["source"] for s in signals})
            pm_src    = st.selectbox("Fonte", src_opts, key="pm_src")
        with fc4:
            pm_score_min = st.slider("Score min.", 0, 100, 0, key="pm_score")

        # Apply filters
        filtered = signals
        if sig_type_filter != "Todos os tipos":
            filtered = [s for s in filtered if s["signal_type"] == sig_type_filter]
        if pm_zone != "Todas as zonas":
            filtered = [s for s in filtered if s["zone"] == pm_zone]
        if pm_src != "Todas as fontes":
            filtered = [s for s in filtered if s["source"] == pm_src]
        filtered = [s for s in filtered if s["signal_score"] >= pm_score_min]

        st.markdown(
            f'<div style="font-size:.72rem;color:#56697e;margin:6px 0 16px;">'
            f'A mostrar <b style="color:#a89c80">{len(filtered)}</b> de {total_sigs} sinais</div>',
            unsafe_allow_html=True,
        )

        # ── Signal cards ──────────────────────────────────────────────────────
        for sig in filtered[:80]:
            promoted_badge = (
                '<span style="background:#16202f;color:#4ade80;border:1px solid #4ade8044;'
                'border-radius:5px;padding:2px 7px;font-size:.62rem;font-weight:700;margin-left:6px;">'
                'PROMOVIDO</span>'
                if sig["promoted"] else ""
            )
            url_link = (
                f'<a href="{sig["url"]}" target="_blank" '
                f'style="font-size:.68rem;color:#60a5fa;text-decoration:none;margin-left:4px;">'
                f'ver fonte</a>'
                if sig["url"] else ""
            )
            person_line = ""
            if sig["name"]:
                person_parts = [f'<b style="color:#f1f5f9">{sig["name"]}</b>']
                if sig["role"]:
                    person_parts.append(f'<span style="color:#a89c80">{sig["role"]}</span>')
                if sig["company"]:
                    person_parts.append(f'<span style="color:#56697e">@ {sig["company"]}</span>')
                person_line = (
                    f'<div style="font-size:.78rem;margin-top:4px;">'
                    + " &middot; ".join(person_parts)
                    + "</div>"
                )
            location_str = sig.get("location_raw") or sig.get("zone") or "—"
            date_str = (
                sig["created_at"].strftime("%d/%m/%Y")
                if sig.get("created_at") else "—"
            )

            st.markdown(
                f'<div class="card" style="margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">'
                f'  <div style="flex:1;min-width:0;">'
                f'    <div style="margin-bottom:5px;">'
                f'      {signal_type_chip(sig["signal_type"])} '
                f'      {source_chip(sig["source"])}'
                f'      {promoted_badge}'
                f'    </div>'
                f'    <div style="font-size:.86rem;font-weight:600;color:#e2e8f0;line-height:1.4;'
                f'      overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                f'      {sig["signal_text"][:120]}'
                f'    </div>'
                f'    {person_line}'
                f'    <div style="margin-top:6px;font-size:.7rem;color:#56697e;">'
                f'      <span style="margin-right:10px;">&#128205; {location_str}</span>'
                f'      <span style="margin-right:10px;">&#128197; {date_str}</span>'
                f'      {url_link}'
                f'    </div>'
                f'  </div>'
                f'  <div style="flex-shrink:0;">{score_bar(sig["signal_score"])}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<hr/>", unsafe_allow_html=True)

        # ── Run scan button ───────────────────────────────────────────────────
        pm_c1, pm_c2 = st.columns(2)
        with pm_c1:
            if st.button("Actualizar Sinais (novo scan)", use_container_width=True):
                with st.spinner("A pesquisar sinais pre-mercado..."):
                    try:
                        from premarket.enricher import PremktEnricher
                        result = PremktEnricher().run(zones=None)
                        st.cache_data.clear()
                        st.success(
                            f"+{result.new_signals} novos sinais | "
                            f"{result.skipped} duplicados ignorados"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
        with pm_c2:
            if st.button("Apenas Licencas de Obras (CM Lisboa)", use_container_width=True):
                with st.spinner("A consultar CM Lisboa open data..."):
                    try:
                        from premarket.enricher import PremktEnricher
                        from premarket.sources.building_permits import BuildingPermitsSource
                        enricher = PremktEnricher()
                        enricher._sources = [BuildingPermitsSource()]
                        result = enricher.run(zones=["Lisboa"])
                        st.cache_data.clear()
                        st.success(
                            f"+{result.new_signals} novas licencas importadas | "
                            f"{result.skipped} ja existentes"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#9881;  Motor":

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.engine_page.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.engine_page.title.before")}<em>{t("page.engine_page.title.em")}</em>{t("page.engine_page.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.engine_page.deck")}</p>'
        f'  <div class="maison-byline"><span>IX &middot; {t("nav.engine_page.label")}</span><span>{t("page.engine_page.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    # ── Schedule editor — recurring run definitions ────────────────────────
    from utils import schedule_store as _sched
    _lang = st.session_state.get("__lang", "pt")

    st.markdown(
        f'<section class="sched-section">'
        f'  <div class="sched-section__eyebrow">{t("sch.section.eyebrow")}</div>'
        f'  <h2 class="sched-section__title">{t("sch.section.title")}</h2>'
        f'  <p class="sched-section__deck">{t("sch.section.deck")}</p>'
        f'</section>',
        unsafe_allow_html=True,
    )

    _schedules = _sched.list_schedules()

    if not _schedules:
        st.markdown(
            f'<div class="sched-empty">{t("sch.empty")}</div>',
            unsafe_allow_html=True,
        )
    else:
        for s in _schedules:
            sid = s["id"]
            name = s.get("name") or "—"
            time_str = f"{s['hour']:02d}:{s['minute']:02d}"
            days_str = _sched.days_label(s.get("days") or [], lang=_lang)
            sources_str = _sched.sources_label(s, lang=_lang)
            zones_str = _sched.zones_label(s, lang=_lang)
            next_in = _sched.next_fire_in_seconds(s)
            if next_in is None:
                next_str = "—"
                next_class = "sched-card__next--off"
            else:
                hh = int(next_in // 3600)
                mm = int((next_in % 3600) // 60)
                next_str = f"{hh}h {mm:02d}m" if hh else f"{mm} min"
                next_class = "sched-card__next--on"

            last = s.get("last_run_at")
            if last:
                from datetime import datetime as _dt
                last_str = _dt.fromtimestamp(last).strftime("%d %b %H:%M")
            else:
                last_str = t("sch.never")

            enabled = bool(s.get("enabled", True))
            card_class = "sched-card" if enabled else "sched-card sched-card--off"
            badge = (
                '<span class="sched-card__badge sched-card__badge--on">ON</span>' if enabled
                else '<span class="sched-card__badge sched-card__badge--off">OFF</span>'
            )

            st.markdown(
                f'<div class="{card_class}">'
                f'  <div class="sched-card__head">'
                f'    <div class="sched-card__time">{time_str}</div>'
                f'    <div class="sched-card__meta">'
                f'      <div class="sched-card__name">{name} {badge}</div>'
                f'      <div class="sched-card__days">{days_str}</div>'
                f'    </div>'
                f'    <div class="sched-card__next-wrap {next_class}">'
                f'      <div class="sched-card__next-lbl">{t("sch.next_in")}</div>'
                f'      <div class="sched-card__next-val">{next_str}</div>'
                f'    </div>'
                f'  </div>'
                f'  <div class="sched-card__detail">'
                f'    <div><span class="sched-card__lbl">FONTES</span> <span class="sched-card__val">{sources_str}</span></div>'
                f'    <div><span class="sched-card__lbl">ZONAS</span> <span class="sched-card__val">{zones_str}</span></div>'
                f'    <div><span class="sched-card__lbl">{t("sch.last_run").upper()}</span> <span class="sched-card__val">{last_str}</span></div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            sc1, sc2, sc3 = st.columns([1, 1, 1])
            with sc1:
                if st.button(("⏸  " if enabled else "▶  ") + ("OFF" if enabled else "ON"),
                             key=f"sch_toggle_{sid}", use_container_width=True):
                    _sched.toggle(sid)
                    st.rerun()
            with sc2:
                if st.button(f"🚀  {t('sch.run_now')}", key=f"sch_runnow_{sid}",
                             use_container_width=True):
                    from utils import run_state as _rs
                    if _rs.is_running():
                        st.toast(t("run.already_running"), icon="⏳")
                    else:
                        _rs.start(sources=s.get("sources"), zones=s.get("zones"))
                        _sched.mark_ran(sid)
                        st.toast(t("run.starting"), icon="🚀")
                        st.rerun()
            with sc3:
                if st.button(f"🗑  {t('sch.delete')}", key=f"sch_del_{sid}",
                             use_container_width=True):
                    _sched.delete(sid)
                    st.toast(t("sch.deleted"), icon="🗑")
                    st.rerun()

    # ── New schedule form ──────────────────────────────────────────────
    with st.expander(t("sch.add.title"), expanded=False):
        f1, f2, f3 = st.columns([2, 1, 1])
        with f1:
            new_name = st.text_input(t("sch.field.name"), placeholder="Manhã Lisboa",
                                     key="sch_new_name")
        with f2:
            new_hour = st.number_input(t("sch.field.hour"), min_value=0, max_value=23,
                                       value=8, step=1, key="sch_new_hour")
        with f3:
            new_min = st.number_input(t("sch.field.minute"), min_value=0, max_value=59,
                                      value=0, step=5, key="sch_new_min")

        st.caption(t("sch.field.days"))
        day_labels_pt = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
        day_labels_en = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        day_labels = day_labels_pt if _lang == "pt" else day_labels_en
        cols = st.columns(7)
        chosen_days = []
        for i, lbl in enumerate(day_labels):
            with cols[i]:
                default = (i < 5)  # mon-fri default
                if st.checkbox(lbl, value=default, key=f"sch_new_day_{i}"):
                    chosen_days.append(i)

        SOURCE_OPTIONS = ["olx", "imovirtual", "olx_marketplace", "standvirtual"]
        new_sources = st.multiselect(t("sch.field.sources"), SOURCE_OPTIONS,
                                     default=["olx", "imovirtual"], key="sch_new_sources")

        ZONE_PRESETS = list(settings.zones)
        new_zones = st.multiselect(t("sch.field.zones"), ZONE_PRESETS,
                                   default=[], key="sch_new_zones")

        if st.button(t("sch.create"), key="sch_create_btn", use_container_width=True,
                     type="primary"):
            if not new_name.strip():
                st.error("Nome obrigatório.")
            elif not chosen_days:
                st.error("Escolhe pelo menos um dia.")
            else:
                _sched.add(
                    name=new_name,
                    hour=new_hour,
                    minute=new_min,
                    days=chosen_days,
                    sources=new_sources or None,
                    zones=new_zones or None,
                )
                st.toast(t("sch.created"), icon="✓")
                st.rerun()

    st.caption(t("sch.daemon.note"))
    st.divider()

    stats = load_stats()
    leads = load_leads(zone=zone_filter, typology=typo_filter, score_min=score_floor, is_demo=_demo_filter, contact=_contact_filter, owner_type=_owner_filter, csource_type=_csource_filter, fts_query=fts_query)

    # Pipeline flow visual
    st.markdown('<div class="lbl-section">Fluxo de Analise Automatica</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pf-wrap">'
        '<div class="pf-step pf-step-active"><span class="pf-icon">&#128375;</span>'
        '<div class="pf-n">Passo 1</div><div class="pf-name">Recolher</div>'
        '<div class="pf-desc">OLX &#183; Imovirtual &#183; Idealista. Rate limiting e rotacao de user-agents.</div></div>'
        '<div class="pf-step"><span class="pf-icon">&#9881;</span>'
        '<div class="pf-n">Passo 2</div><div class="pf-name">Normalizar</div>'
        '<div class="pf-desc">Limpeza e padronizacao. Deduplicacao por fingerprint SHA-256.</div></div>'
        '<div class="pf-step"><span class="pf-icon">&#128100;</span>'
        '<div class="pf-n">Passo 3</div><div class="pf-name">Identificar</div>'
        '<div class="pf-desc">Proprietario directo vs. agencia. Deteccao de FSBO e sinais de urgencia.</div></div>'
        '<div class="pf-step"><span class="pf-icon">&#128202;</span>'
        '<div class="pf-n">Passo 4</div><div class="pf-name">Enriquecer</div>'
        '<div class="pf-desc">Benchmark EUR/m2 por zona. Geocoding. Motivo de venda. Historico de precos.</div></div>'
        '<div class="pf-step"><span class="pf-icon">&#127919;</span>'
        '<div class="pf-n">Passo 5</div><div class="pf-name">Pontuar</div>'
        '<div class="pf-desc">Score 0-100 em 6 dimensoes. HOT &gt;= 75, WARM &gt;= 50, COLD &lt; 50.</div></div>'
        '<div class="pf-step"><span class="pf-icon">&#128276;</span>'
        '<div class="pf-n">Passo 6</div><div class="pf-name">Alertar</div>'
        '<div class="pf-desc">Email + Telegram imediato para HOT. Relatorio diario 08:00.</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Run button
    if st.button("▶  Executar Analise Completa de Mercado (todos os 6 passos)", use_container_width=True, type="primary"):
        prog  = st.progress(0, "A iniciar...")
        steps = [
            "Recolher dados...", "Normalizar e desduplicar...", "Identificar proprietarios...",
            "Enriquecer com benchmarks...", "Calcular pontuacoes...", "Verificar alertas HOT...",
        ]
        try:
            from pipeline.runner import PipelineRunner
            from scoring.scorer import Scorer
            runner = PipelineRunner()
            for i, msg in enumerate(steps[:-1], 1):
                prog.progress(int(i / 6 * 100), msg)
                if i == 1:
                    r = runner.run_full()
            prog.progress(83, "A calcular pontuacoes...")
            n_scored = Scorer().score_all_pending()
            prog.progress(100, "Concluido!")
            st.cache_data.clear()
            st.success(f"Analise concluida — {r.leads_created} novas · {r.leads_updated} actualizadas · {n_scored} pontuadas")
        except Exception as e:
            prog.empty()
            st.error(f"Erro: {e}")

    st.divider()

    # ─── Painel de operações granulares ───────────────────────────────────
    # Cada cartão dispara um passo específico. Útil quando só precisas de
    # re-treinar o classificador, refazer dedup de fotos, etc — sem repetir
    # o pipeline todo.
    st.markdown('<div class="lbl-section">Operações individuais</div>', unsafe_allow_html=True)
    st.caption(
        "Cada botão executa um único passo. Útil para correr o que falta "
        "sem repetir o pipeline completo. Os logs de cada operação ficam "
        "visíveis na aba Sistema."
    )

    OPERATIONS = [
        # (label, descrição, runner-function-name, expected_minutes)
        ("📡 Recolher novos leads",
         "Scrape de OLX, Imovirtual, Idealista, Sapo, Custojusto + bancos + leilões.",
         "scrape", 60),
        ("🔄 Processar raw → leads",
         "Normalize + dedupe + enrich + upsert.",
         "process", 5),
        ("🎯 Recalcular scores",
         "Score 0-100 em 6 dimensões para todos os leads.",
         "score", 2),
        ("🔔 Disparar alertas HOT",
         "Email/Telegram dos leads HOT (acima do threshold).",
         "alerts", 1),
        ("🔗 Cross-portal contact match",
         "Propaga telefone/email entre listings do mesmo imóvel.",
         "cross_match", 5),
        ("🌐 Enrich agências (websites)",
         "Visita os sites das agências para obter telefone+email.",
         "enrich_websites", 10),
        ("👥 Enrich seller profiles (OLX)",
         "Detecta super-sellers e agências camufladas.",
         "enrich_sellers", 8),
        ("🤖 Treinar ML classifier",
         "Re-treina o classificador FSBO/agency (87% accuracy).",
         "train_classifier", 1),
        ("🔁 Reclassificar owners",
         "Aplica o ML em leads incertos (threshold 0.85).",
         "reclassify", 2),
        ("💸 Detectar quedas de preço",
         "Marca leads com queda ≥5% nos últimos 14 dias.",
         "price_drops", 1),
        ("📍 Geocodar leads (Nominatim)",
         "Resolve lat/lng com cache. ~1.1s por novo endereço.",
         "geocode", 5),
        ("🖼 Hash de imagens",
         "Calcula pHash para dedup cross-portal.",
         "hash_images", 5),
        ("🔍 Dedup fotos cross-portal",
         "Funde leads com fotos idênticas em portais diferentes.",
         "dedup_photos", 1),
        ("🏷 Tags de amenities",
         "Extrai piscina/garagem/varanda/etc da descrição.",
         "tag_amenities", 1),
        ("⏰ Nurture tick",
         "Cria reminders para leads parados (3/7/14d por fase).",
         "nurture", 1),
        ("🗄 Auto-archive stale",
         "Arquiva leads sem updates há mais de 60 dias.",
         "archive_stale", 1),
        ("❌ Sweep dropped listings",
         "HEAD-check de URLs — marca 404/410 como dropped.",
         "sweep_dropped", 5),
        ("💾 Snapshot da DB",
         "Backup zipado em data/backups/.",
         "backup", 1),
        ("📰 Trend report PDF",
         "Gera o relatório semanal em PDF.",
         "trend_report", 1),
        ("🔎 Rebuild FTS index",
         "Reconstrói índice de pesquisa full-text.",
         "rebuild_fts", 1),
    ]

    def _run_op(op_key: str) -> tuple[bool, str]:
        """Run a single operation by key. Returns (ok, message)."""
        try:
            if op_key == "scrape":
                from pipeline.runner import PipelineRunner
                r = PipelineRunner().run_full()
                return True, f"+{r.leads_created} novos · ↑{r.leads_updated} updated"
            elif op_key == "process":
                from pipeline.runner import PipelineRunner
                r = PipelineRunner().process_raw(limit=2000)
                return True, f"+{r.leads_created} criados · ↑{r.leads_updated} updated"
            elif op_key == "score":
                from scoring.scorer import Scorer
                n = Scorer().score_all_pending()
                return True, f"{n} leads pontuados"
            elif op_key == "alerts":
                from alerts.notifier import Notifier
                n = Notifier().check_and_alert_hot_leads()
                return True, f"{n} alertas enviados"
            elif op_key == "cross_match":
                from pipeline.runner import PipelineRunner
                stats = PipelineRunner().run_cross_match()
                return True, f"matched={stats.get('matched',0)} phone=+{stats.get('phone',0)}"
            elif op_key == "enrich_websites":
                from pipeline.runner import PipelineRunner
                stats = PipelineRunner().run_website_enrichment()
                return True, f"agencies_ok={stats.get('agencies_ok',0)} +phone={stats.get('phone',0)}"
            elif op_key == "enrich_sellers":
                from pipeline.seller_profile_enricher import SellerProfileEnricher
                stats = SellerProfileEnricher().run()
                return True, f"visited={stats['visited']} super={stats['super_flagged']}"
            elif op_key == "train_classifier":
                from pipeline.owner_classifier import train_and_save
                stats = train_and_save()
                return True, f"accuracy={stats.get('accuracy',0):.1%}" if stats.get("trained") else "Sem amostras suficientes"
            elif op_key == "reclassify":
                from pipeline.owner_classifier import reclassify_uncertain_leads
                stats = reclassify_uncertain_leads(threshold=0.85)
                if not stats.get("trained", True):
                    return False, "Modelo não existe — treina primeiro"
                return True, f"FSBO→agency={stats['fsbo_to_agency']} agency→FSBO={stats['agency_to_fsbo']}"
            elif op_key == "price_drops":
                from pipeline.price_drop_detector import PriceDropDetector
                stats = PriceDropDetector().run()
                return True, f"{stats['newly_flagged']} flagged como urgente"
            elif op_key == "geocode":
                from utils.geocoder import geocode_leads_backfill
                stats = geocode_leads_backfill(limit=1500)
                return True, f"nominatim={stats.get('nominatim',0)} cache={stats.get('cache',0)}"
            elif op_key == "hash_images":
                from utils.image_hasher import backfill_image_hashes
                stats = backfill_image_hashes(limit=1000)
                return True, f"{stats['hashed']} imagens hasheadas"
            elif op_key == "dedup_photos":
                from utils.image_hasher import photo_dedup_sweep
                stats = photo_dedup_sweep(threshold=5)
                return True, f"{stats['merged']} duplicados fundidos"
            elif op_key == "tag_amenities":
                from utils.amenity_tags import backfill_amenity_tags
                stats = backfill_amenity_tags(limit=2000)
                return True, f"{stats['tagged']} leads taggeados"
            elif op_key == "nurture":
                from pipeline.nurture import run_nurture_tick
                stats = run_nurture_tick(min_gap_days=1)
                return True, f"{stats['reminders_added']} reminders adicionados"
            elif op_key == "archive_stale":
                from pipeline.maintenance import auto_archive_stale
                stats = auto_archive_stale(stale_days=60)
                return True, f"{stats['archived']} arquivados"
            elif op_key == "sweep_dropped":
                from pipeline.maintenance import mark_dropped_listings
                stats = mark_dropped_listings(limit=200)
                return True, f"dropped={stats['dropped']} alive={stats['alive']}"
            elif op_key == "backup":
                from storage.backup import backup_now, prune_old_backups
                res = backup_now(label="manual")
                prune_old_backups(keep=14)
                if res.get("skipped"):
                    return False, res.get("error", "skipped")
                return True, f"{res['size_mb']} MB · {res['path'].split('/')[-1]}"
            elif op_key == "trend_report":
                from reports.trend_pdf import generate_trend_report
                path = generate_trend_report(days=7)
                return True, f"PDF: {path.name}"
            elif op_key == "rebuild_fts":
                from storage.fts import rebuild_fts as _rb
                stats = _rb()
                if stats.get("skipped_non_sqlite"):
                    return False, "FTS5 só em SQLite"
                return True, f"{stats['indexed']} rows indexadas"
            else:
                return False, f"Operação desconhecida: {op_key}"
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:120]}"

    # Render operations as a 4-column grid of action cards
    op_cols_per_row = 2
    rows = [OPERATIONS[i:i + op_cols_per_row] for i in range(0, len(OPERATIONS), op_cols_per_row)]
    for row in rows:
        cols = st.columns(op_cols_per_row)
        for col, (label, desc, op_key, est_min) in zip(cols, row):
            with col:
                with st.container(border=False):
                    st.markdown(
                        f'<div class="card" style="padding:14px 16px;margin-bottom:6px;">'
                        f'  <div style="font-weight:700;color:var(--ice);'
                        f'              font-size:.92rem;margin-bottom:4px;">{label}</div>'
                        f'  <div style="color:var(--smoke);font-size:.74rem;'
                        f'              line-height:1.4;margin-bottom:8px;">{desc}</div>'
                        f'  <div style="font-size:.65rem;color:var(--dust);'
                        f'              font-family:Space Grotesk;letter-spacing:.4px;">'
                        f'    ~{est_min} min'
                        f'  </div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(f"Executar", key=f"op_{op_key}",
                                 use_container_width=True):
                        with st.spinner(f"A correr {label.split(' ', 1)[1]}..."):
                            ok, msg = _run_op(op_key)
                        if ok:
                            st.toast(f"✓ {msg}", icon="✅")
                            st.cache_data.clear()
                        else:
                            st.error(f"Falhou: {msg}")

    st.divider()

    # Stats summary
    by_src    = stats.get("by_source", {"olx": 0, "imovirtual": 0, "idealista": 0})
    total_src = sum(by_src.values()) or 1

    res1, res2 = st.columns(2, gap="large")

    with res1:
        st.markdown('<div class="lbl-section">Anuncios por Fonte</div>', unsafe_allow_html=True)
        src_rows = [
            ("OLX",        by_src.get("olx", 0),        "#f59e0b"),
            ("Imovirtual", by_src.get("imovirtual", 0), "#3b82f6"),
            ("Idealista",  by_src.get("idealista", 0),  "#8b5cf6"),
            ("Sapo",       by_src.get("sapo", 0),       "#a8861a"),
        ]
        # Filter out zero-count sources so they don't clutter the bar chart
        src_rows = [(n, c, col) for n, c, col in src_rows if c > 0]
        total_src = sum(c for _, c, _ in src_rows) or 1
        bars_html = '<div style="background:#111827;border:1px solid #1a2640;border-radius:10px;padding:16px 20px;">'
        for name, count, color in src_rows:
            pct = int(count / total_src * 100)
            bars_html += (
                f'<div class="src-bar-row">'
                f'<span class="src-bar-name">{name}</span>'
                f'<div class="src-bar-track"><div class="src-bar-fill" style="width:{pct}%;background:{color};"></div></div>'
                f'<span class="src-bar-count">{count}</span>'
                f'</div>'
            )
        bars_html += (
            f'<div style="margin-top:12px;padding-top:10px;border-top:1px solid #1a2640;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:.72rem;color:#56697e;">Apos deduplicacao</span>'
            f'<span style="font-size:1.05rem;font-weight:900;color:#f1f5f9;">{stats.get("total_active",0)} unicas</span>'
            f'</div></div>'
        )
        st.markdown(bars_html, unsafe_allow_html=True)

    with res2:
        st.markdown('<div class="lbl-section">Resumo de Inteligencia</div>', unsafe_allow_html=True)
        n_phone   = sum(1 for l in leads if l.get("has_phone"))
        n_email   = sum(1 for l in leads if l.get("has_email") and not l.get("has_phone"))
        n_noct    = sum(1 for l in leads if not l.get("has_contact"))
        cells = [
            ("HOT",              stats.get("hot_count", 0),        "#f43f5e"),
            ("WARM",             stats.get("warm_count", 0),       "#f59e0b"),
            ("Owner Directo",    stats.get("owner_count", 0),      "#a8861a"),
            ("Com Reducao",      stats.get("price_drop_count", 0), "#f97316"),
            ("&#128222; Com Telefone",  n_phone,                   "#a8861a"),
            ("&#9993; Com Email",       n_email,                   "#60a5fa"),
            ("&#10060; Sem Contacto",   n_noct,                    "#ef4444"),
            ("Com Urgencia",     stats.get("urgency_count", 0),    "#a78bfa"),
        ]
        grid_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">'
        for lbl, val, clr in cells:
            grid_html += (
                f'<div class="intel-box">'
                f'<div class="intel-lbl">{lbl}</div>'
                f'<div class="intel-val" style="color:{clr};">{val}</div>'
                f'</div>'
            )
        grid_html += '</div>'
        st.markdown(grid_html, unsafe_allow_html=True)

    st.divider()

    # Alerts + Motivations
    al_col, mv_col = st.columns(2, gap="large")
    with al_col:
        st.markdown('<div class="lbl-section">Alertas Comerciais Activos</div>', unsafe_allow_html=True)
        all_leads = load_leads(is_demo=_demo_filter, contact=_contact_filter)
        alerts    = generate_alerts(all_leads)
        if alerts:
            for a in alerts:
                st.markdown(alert_card_html(a), unsafe_allow_html=True)
        else:
            st.caption("Sem alertas activos. Execute a analise de mercado.")

    with mv_col:
        st.markdown('<div class="lbl-section">Motivos de Venda Detectados</div>', unsafe_allow_html=True)
        from collections import Counter
        motive_counts: Counter = Counter()
        for lead in all_leads:
            for lb, _ in detect_motivation(lead.get("description", "")):
                motive_counts[lb] += 1
        if motive_counts:
            for lb, cnt in motive_counts.most_common(8):
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:6px 0;border-bottom:1px solid #1a2640;font-size:.82rem;">'
                    f'<span style="background:rgba(139,92,246,.1);color:#a78bfa;border:1px solid rgba(139,92,246,.2);'
                    f'border-radius:20px;font-size:.64rem;font-weight:700;padding:2px 8px;">{lb}</span>'
                    f'<span style="color:#a89c80;font-weight:700;">{cnt} propriedade{"s" if cnt > 1 else ""}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Nenhum motivo identificado nas descricoes actuais.")

    st.divider()
    with st.expander("Controlo avancado — executar passos individuais"):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            if st.button("Recolher dados (todos os portais)", use_container_width=True):
                with st.spinner("A recolher dados..."):
                    try:
                        from pipeline.runner import PipelineRunner
                        PipelineRunner()._run_scrapers(["olx", "imovirtual", "idealista"], ["Lisboa", "Cascais"])
                        st.success("Recolha concluida")
                    except Exception as e:
                        st.error(str(e))
            if st.button("Normalizar e enriquecer listagens", use_container_width=True):
                with st.spinner("A processar..."):
                    try:
                        from pipeline.runner import PipelineRunner
                        s = PipelineRunner().process_raw()
                        st.success(f"{s.leads_created} novas · {s.leads_updated} actualizadas")
                    except Exception as e:
                        st.error(str(e))
        with col2:
            if st.button("Recalcular todas as pontuacoes", use_container_width=True):
                with st.spinner("A calcular..."):
                    try:
                        from scoring.scorer import Scorer
                        n = Scorer().score_all_pending()
                        st.cache_data.clear()
                        st.success(f"{n} oportunidades actualizadas")
                    except Exception as e:
                        st.error(str(e))
            if st.button("Enviar alertas HOT agora", use_container_width=True):
                with st.spinner("A verificar..."):
                    try:
                        from alerts.notifier import Notifier
                        n = Notifier().check_and_alert_hot_leads()
                        st.success(f"{n} alertas enviados")
                    except Exception as e:
                        st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE: EXPORTAR
# ══════════════════════════════════════════════════════════════════════════════
elif page == "&#128228;  Exportar":

    st.markdown(
        f'<section class="maison maison--mini">'
        f'  <div class="maison-eyebrow">{t("page.export.eyebrow")}</div>'
        f'  <h1 class="maison-title">{t("page.export.title.before")}<em>{t("page.export.title.em")}</em>{t("page.export.title.after")}</h1>'
        f'  <p class="maison-deck">{t("page.export.deck")}</p>'
        f'  <div class="maison-byline"><span>X &middot; {t("nav.export.label")}</span><span>{t("page.export.byline")}</span></div>'
        f'</section>',
        unsafe_allow_html=True,
    )

    # ── CSV Import — bring-your-own-leads ────────────────────────────────
    with st.expander("📥 Importar leads de CSV / Excel exportado", expanded=False):
        st.caption(
            "Aceita qualquer CSV com colunas comuns (nome, telefone, email, "
            "preço, zona, tipologia, etc). Schema-flexível — colunas extra "
            "ficam guardadas no histórico do lead. Dedup automático por "
            "telefone → email → zona+tipologia+preço."
        )
        uploaded = st.file_uploader(
            "Ficheiro CSV", type=["csv", "txt"],
            key="csv_import_uploader",
            label_visibility="collapsed",
        )
        ic1, ic2 = st.columns([1, 3])
        with ic1:
            csv_source = st.text_input(
                "Tag origem", value="csv_import",
                help="Aparece em discovery_source",
            )
        with ic2:
            if uploaded and st.button(
                f"Importar {uploaded.name}", type="primary",
                use_container_width=True, key="csv_import_btn",
            ):
                from pipeline.csv_importer import import_csv as _imp
                with st.spinner("A importar..."):
                    try:
                        stats = _imp(uploaded.getvalue(), source=csv_source or "csv_import")
                        st.toast(
                            f"+{stats['created']} novos · ↑{stats['updated']} atualizados",
                            icon="📥",
                        )
                        st.success(
                            f"Lidos {stats['read']} · "
                            f"{stats['created']} criados · "
                            f"{stats['updated']} atualizados · "
                            f"{stats['skipped_invalid']} skipped · "
                            f"{stats['errors']} erros"
                        )
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Falhou: {e}")

    st.divider()

    # ── Row 1: Client-ready exports ──────────────────────────────────────
    ec1, ec2 = st.columns(2, gap="large")

    with ec1:
        st.markdown(
            '<div class="card" style="border-left:3px solid #a8861a;">'
            '<div style="font-size:.95rem;font-weight:700;color:#a8861a;margin-bottom:6px;">📋 Lista de Contactos</div>'
            '<div style="font-size:.78rem;color:#a89c80;line-height:1.55;">'
            'Lista pronta para o cliente com nome, apelido, telefone, WhatsApp, zona, tipologia, '
            'preco, tipo de lead e insight. <strong>Exclui relay/OLX por defeito.</strong>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        ct_score = st.slider("Score minimo", 0, 100, 0, key="ct_score")
        ct_mobile = st.checkbox("Apenas telemóvel real (9xx)", value=True, key="ct_mobile",
                                help="Exclui relay (6xx) e fixo (2xx) — só números contactáveis")
        ct_no_agency = st.checkbox("Excluir agências", value=True, key="ct_no_agency")

        if st.button("Gerar Lista de Contactos", use_container_width=True, type="primary"):
            with st.spinner("A gerar lista..."):
                try:
                    from reports.contact_export import generate_contact_list, export_contact_xlsx, export_contact_csv
                    from datetime import datetime as _dt

                    contacts = generate_contact_list(
                        score_min=ct_score,
                        zones=[zone_filter] if zone_filter else None,
                        include_agencies=not ct_no_agency,
                        mobile_only=ct_mobile,
                    )
                    if not contacts:
                        st.warning("Nenhum contacto encontrado com esses filtros.")
                    else:
                        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                        # Generate XLSX
                        xlsx_path = f"data/contactos_{ts}.xlsx"
                        export_contact_xlsx(contacts, xlsx_path)
                        csv_path = f"data/contactos_{ts}.csv"
                        export_contact_csv(contacts, csv_path)

                        st.success(f"{len(contacts)} contactos gerados")
                        dl1, dl2 = st.columns(2)
                        with dl1:
                            with open(xlsx_path, "rb") as f:
                                st.download_button(
                                    f"Descarregar Excel ({len(contacts)} leads)",
                                    f, file_name=Path(xlsx_path).name,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True,
                                )
                        with dl2:
                            with open(csv_path, "rb") as f:
                                st.download_button(
                                    f"Descarregar CSV ({len(contacts)} leads)",
                                    f, file_name=Path(csv_path).name,
                                    mime="text/csv",
                                    use_container_width=True,
                                )
                except Exception as e:
                    st.error(f"Erro: {e}")

    with ec2:
        st.markdown(
            '<div class="card" style="border-left:3px solid #f59e0b;">'
            '<div style="font-size:.95rem;font-weight:700;color:#f59e0b;margin-bottom:6px;">⭐ Lista Comercial Premium</div>'
            '<div style="font-size:.78rem;color:#a89c80;line-height:1.55;">'
            'Excel com 3 separadores: <strong>Lista Premium</strong> (top proprietários com telemóvel), '
            '<strong>Lista Expandida</strong> (mais leads), e <strong>Resumo Executivo</strong> (KPIs).'
            '</div></div>',
            unsafe_allow_html=True,
        )
        cm_premium = st.number_input("Leads Premium (top)", value=30, min_value=5, max_value=100, key="cm_prem")
        cm_expanded = st.number_input("Leads Expandidos", value=100, min_value=10, max_value=500, key="cm_exp")

        if st.button("Gerar Lista Comercial", use_container_width=True, type="primary"):
            with st.spinner("A gerar lista comercial..."):
                try:
                    from reports.commercial_export import (
                        generate_premium_list, generate_expanded_list,
                        export_commercial_xlsx,
                    )
                    from datetime import datetime as _dt

                    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                    xlsx_path = f"data/leads_comercial_{ts}.xlsx"
                    premium = generate_premium_list(limit=cm_premium)
                    expanded = generate_expanded_list(
                        premium_phones={r.get("telefone") for r in premium if r.get("telefone")},
                        limit=cm_expanded,
                    )
                    summary = {
                        "premium_count": len(premium),
                        "expanded_count": len(expanded),
                        "generated_at": _dt.now().isoformat(),
                    }
                    export_commercial_xlsx(premium, expanded, summary, xlsx_path)
                    st.success(f"Lista comercial gerada: {len(premium)} premium + {len(expanded)} expandidos")
                    with open(xlsx_path, "rb") as f:
                        st.download_button(
                            f"Descarregar Excel Comercial",
                            f, file_name=Path(xlsx_path).name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )
                except Exception as e:
                    st.error(f"Erro: {e}")

    st.divider()

    # ── Row 2: Technical exports ─────────────────────────────────────────
    st.markdown(
        '<div style="font-size:.82rem;font-weight:700;color:#56697e;margin-bottom:12px;">Exportações técnicas</div>',
        unsafe_allow_html=True,
    )
    ec3, ec4 = st.columns(2, gap="large")

    with ec3:
        st.markdown(
            '<div class="card"><div style="font-size:.85rem;font-weight:600;color:#a89c80;margin-bottom:4px;">Relatório CSV (todos os campos)</div>'
            '<div style="font-size:.72rem;color:#56697e;">Exportação técnica com todos os campos da BD — para análise interna.</div></div>',
            unsafe_allow_html=True,
        )
        min_s = st.slider("Score minimo", 0, 100, 0, key="csv_sl")
        if st.button("Gerar CSV técnico", use_container_width=True):
            with st.spinner("A gerar..."):
                try:
                    from reports.generator import ReportGenerator
                    path = ReportGenerator().export_csv(score_min=min_s)
                    st.success(f"Ficheiro: `{path}`")
                    with open(path, "rb") as f:
                        st.download_button("Descarregar CSV", f,
                                           file_name=Path(path).name,
                                           mime="text/csv",
                                           use_container_width=True)
                except Exception as e:
                    st.error(str(e))

    with ec4:
        st.markdown(
            '<div class="card"><div style="font-size:.85rem;font-weight:600;color:#a89c80;margin-bottom:4px;">JSON (integração)</div>'
            '<div style="font-size:.72rem;color:#56697e;">Formato estruturado para integração com sistemas externos.</div></div>',
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("Exportar WARM + HOT (JSON)", use_container_width=True):
            with st.spinner("A exportar..."):
                try:
                    from reports.generator import ReportGenerator
                    path = ReportGenerator().export_json(score_min=50)
                    st.success(f"Ficheiro: `{path}`")
                    with open(path, "rb") as f:
                        st.download_button("Descarregar JSON", f,
                                           file_name=Path(path).name,
                                           mime="application/json",
                                           use_container_width=True)
                except Exception as e:
                    st.error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  EDITORIAL FOOTER — appears once on every page (outside any if/elif).
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    f'<footer class="maison-footer">'
    f'  <div class="maison-footer__mark">Patabrava</div>'
    f'  <div class="maison-footer__row">'
    f'    <span>Lisboa</span>'
    f'    <span>{t("footer.lemma")}</span>'
    f'    <span>MMXXVI</span>'
    f'  </div>'
    f'  <div class="maison-footer__addr">'
    f'    Praça de Alvalade 6 &middot; Lisboa &middot; AMI 23783 &middot; '
    f'    <em>+351 938 443 833</em> &middot; office@patabrava.pt'
    f'  </div>'
    f'</footer>',
    unsafe_allow_html=True,
)
