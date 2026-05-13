"""
Telegram Bot · interactive lead analyzer for Pata Brava.

A long-polling bot that lets the operator (Susana) interact com a base de
leads do telemóvel. Não precisa de webhooks · não precisa de servidor
público · só precisa de internet.

Comandos disponíveis:
  /start          → mensagem de boas-vindas + lista de comandos
  /help           → lista detalhada de comandos
  /kpi            → KPIs actuais (total · HOT · Tier A+B · premarket)
  /top            → top 10 leads Tier A/B para chamar hoje
  /tier A|B|C|D|E → leads de um tier específico (até 15)
  /zona <nome>    → leads de uma zona (ex: /zona Lisboa)
  /lead <id>      → briefing completo de um lead (com opening WhatsApp)
  /reengage       → fila de re-engagement (leads sem resposta há 30d+)
  /premarket      → sinais premarket por tipo
  /buscar <termo> → procurar por nome ou telefone
  /brief          → enviar o MORNING_BRIEF.txt do dia

Use:
  python main.py telegram-bot
"""
from __future__ import annotations

import html
import json
import time
import traceback
from datetime import datetime
from typing import Callable, Optional

import requests

from config.settings import settings
from storage.database import get_db
from storage.models import Lead, PremktSignal
from utils.logger import get_logger
from reports.commercial_export import (
    _classify_owner_tier, _short_zone, _PT_STAGE_LABELS,
)

log = get_logger(__name__)


API_BASE = "https://api.telegram.org/bot{token}"
POLL_TIMEOUT = 30
MAX_MSG_LEN  = 4000


# ── Telegram primitives ──────────────────────────────────────────────────────

def _api(token: str, method: str, **params) -> dict:
    url = API_BASE.format(token=token) + f"/{method}"
    try:
        r = requests.post(url, json=params, timeout=POLL_TIMEOUT + 5)
        return r.json()
    except Exception as e:
        log.error("[tg_bot] api {m} failed: {e}", m=method, e=e)
        return {"ok": False, "error": str(e)}


def _send(token: str, chat_id: int, text: str, parse: str = "HTML") -> None:
    # Chunk for Telegram 4096 limit
    while text:
        chunk, text = text[:MAX_MSG_LEN], text[MAX_MSG_LEN:]
        _api(token, "sendMessage",
             chat_id=chat_id, text=chunk, parse_mode=parse,
             disable_web_page_preview=True)


# ── Formatters ───────────────────────────────────────────────────────────────

def _fmt_price(p) -> str:
    if not p: return "—"
    return f"€{int(p):,}".replace(",", " ")


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else "—"


def _lead_summary_line(L: Lead, idx: Optional[int] = None) -> str:
    tier = _classify_owner_tier(L) if L.contact_phone else "?"
    nm = (L.contact_name or "—")[:22]
    zone = (_short_zone(L.zone) or "—")[:15]
    typ = (L.typology or L.property_type or "—")[:9]
    price = _fmt_price(L.price)
    ph = L.contact_phone or "—"
    prefix = f"{idx}. " if idx else ""
    return (
        f"{prefix}<b>#{L.id}</b> · <b>{tier}</b> · {_esc(nm)}\n"
        f"   {_esc(zone)} · {_esc(typ)} · {_esc(price)}\n"
        f"   <code>{_esc(ph)}</code>"
    )


# ── Command handlers ────────────────────────────────────────────────────────

def cmd_start(token: str, chat_id: int, args: list[str]) -> None:
    msg = (
        "👋 <b>Patabrava · Lead Bot</b>\n\n"
        "Olá! Eu sou o motor de angariações da Pata Brava."
        " Podes pedir-me leads, KPIs e briefings em tempo real.\n\n"
        "<b>Comandos rápidos:</b>\n"
        "/kpi        — números do dia\n"
        "/top        — top 10 para chamar agora\n"
        "/lead 12345 — dossier de um lead\n"
        "/help       — todos os comandos\n\n"
        "Manda <code>/kpi</code> para começar."
    )
    _send(token, chat_id, msg)


def cmd_help(token: str, chat_id: int, args: list[str]) -> None:
    msg = (
        "<b>Comandos disponíveis</b>\n\n"
        "/kpi            KPIs da base (total · HOT · Tier A+B · premarket)\n"
        "/top            Top 10 Tier A/B para chamar hoje\n"
        "/tier A|B|C|D   Leads de um tier específico (até 15)\n"
        "/zona &lt;nome&gt;     Leads de uma zona (ex: /zona Cascais)\n"
        "/lead &lt;id&gt;       Briefing completo + opening WhatsApp\n"
        "/reengage       Fila de re-engagement (30d+)\n"
        "/premarket      Sinais premarket por tipo\n"
        "/buscar &lt;termo&gt;  Procurar por nome ou telefone\n"
        "/brief          Resumo da manhã (MORNING_BRIEF)"
    )
    _send(token, chat_id, msg)


def cmd_kpi(token: str, chat_id: int, args: list[str]) -> None:
    with get_db() as db:
        total = db.query(Lead).filter(Lead.archived == False).count()  # noqa: E712
        hot = db.query(Lead).filter(
            Lead.archived == False, Lead.score_label == "HOT").count()
        mobile = db.query(Lead).filter(
            Lead.archived == False, Lead.phone_type == "mobile").count()
        leads = db.query(Lead).filter(
            Lead.archived == False, Lead.contact_phone.isnot(None),
            Lead.phone_type == "mobile").all()
        ab = sum(1 for L in leads if _classify_owner_tier(L) in ("A", "B"))
        premkt = db.query(PremktSignal).count()
        # Re-engagement count
        now = datetime.utcnow()
        re_eng = db.query(Lead).filter(
            Lead.archived == False,
            Lead.re_engage_after.isnot(None),
            Lead.re_engage_after <= now).count()

    msg = (
        f"📊 <b>KPIs · {datetime.utcnow().strftime('%d/%m %H:%M UTC')}</b>\n\n"
        f"Total leads activos   <b>{total:,}</b>\n".replace(",", " ")
        + f"Com telemóvel mobile  <b>{mobile:,}</b>\n".replace(",", " ")
        + f"HOT (score ≥ 60)      <b>{hot:,}</b>\n".replace(",", " ")
        + f"Tier A+B verificados  <b>{ab}</b>\n"
        f"Re-engagement hoje    <b>{re_eng}</b>\n"
        f"Sinais premarket      <b>{premkt:,}</b>".replace(",", " ")
    )
    _send(token, chat_id, msg)


def cmd_top(token: str, chat_id: int, args: list[str]) -> None:
    limit = 10
    if args and args[0].isdigit():
        limit = min(int(args[0]), 25)
    with get_db() as db:
        candidates = (db.query(Lead).filter(
            Lead.archived == False,                                   # noqa: E712
            Lead.contact_phone.isnot(None),
            Lead.phone_type == "mobile",
            Lead.last_contacted_at.is_(None),
            Lead.score >= 20,
        ).order_by(Lead.score.desc(), Lead.price.desc()).limit(2000).all())
    top = [L for L in candidates if _classify_owner_tier(L) in ("A", "B")][:limit]
    if not top:
        _send(token, chat_id, "Sem leads Tier A/B novos hoje · base limpa ou aguardar próxima run.")
        return
    parts = [f"📞 <b>Top {len(top)} para chamar hoje</b>\n"]
    for i, L in enumerate(top, 1):
        parts.append(_lead_summary_line(L, i))
        parts.append("")
    parts.append(f"<i>Pede /lead &lt;id&gt; para ver briefing completo.</i>")
    _send(token, chat_id, "\n".join(parts))


def cmd_tier(token: str, chat_id: int, args: list[str]) -> None:
    if not args:
        _send(token, chat_id, "Uso: /tier A | B | C | D | E")
        return
    target = args[0].upper()
    if target not in ("A", "B", "C", "D", "E", "?"):
        _send(token, chat_id, "Tier inválido. Usa A, B, C, D ou E.")
        return
    with get_db() as db:
        candidates = (db.query(Lead).filter(
            Lead.archived == False,                                   # noqa: E712
            Lead.contact_phone.isnot(None),
            Lead.phone_type.in_(("mobile", "landline")),
        ).order_by(Lead.score.desc()).limit(800).all())
    leads = [L for L in candidates if _classify_owner_tier(L) == target][:15]
    if not leads:
        _send(token, chat_id, f"Sem leads em Tier {target}.")
        return
    parts = [f"📋 <b>Tier {target} · {len(leads)} leads (top)</b>\n"]
    for i, L in enumerate(leads, 1):
        parts.append(_lead_summary_line(L, i))
        parts.append("")
    _send(token, chat_id, "\n".join(parts))


def cmd_zona(token: str, chat_id: int, args: list[str]) -> None:
    if not args:
        _send(token, chat_id, "Uso: /zona Lisboa  (ou /zona Cascais, /zona Almada…)")
        return
    zone = " ".join(args).strip()
    with get_db() as db:
        leads = (db.query(Lead).filter(
            Lead.archived == False,                                   # noqa: E712
            Lead.contact_phone.isnot(None),
            Lead.zone.ilike(f"%{zone}%"),
        ).order_by(Lead.score.desc()).limit(15).all())
    if not leads:
        _send(token, chat_id, f"Sem leads na zona {zone}.")
        return
    parts = [f"📍 <b>Zona {zone} · top {len(leads)}</b>\n"]
    for i, L in enumerate(leads, 1):
        parts.append(_lead_summary_line(L, i))
        parts.append("")
    _send(token, chat_id, "\n".join(parts))


def cmd_lead(token: str, chat_id: int, args: list[str]) -> None:
    if not args or not args[0].isdigit():
        _send(token, chat_id, "Uso: /lead 12345")
        return
    lead_id = int(args[0])
    with get_db() as db:
        L = db.query(Lead).filter(Lead.id == lead_id).first()
        if not L:
            _send(token, chat_id, f"Lead #{lead_id} não encontrado.")
            return
    tier = _classify_owner_tier(L) if L.contact_phone else "?"
    # Try briefing
    try:
        from pipeline.precall_briefing import build_briefing
        br = build_briefing(L)
        brief_text = br.get("text") or ""
        opening = br.get("opening") or ""
        commission = br.get("commission_eur", 0)
    except Exception:
        brief_text = ""
        opening = ""
        commission = 0
    # Build URL
    url = ""
    try:
        s = json.loads(L.sources_json or "[]")
        if s and isinstance(s, list) and isinstance(s[0], dict):
            url = s[0].get("url", "")
    except Exception:
        pass

    stage = _PT_STAGE_LABELS.get(L.crm_stage, L.crm_stage or "—")
    msg = (
        f"📄 <b>Lead #{L.id} · Tier {tier}</b>\n\n"
        f"<b>{_esc(L.contact_name or 'sem nome')}</b>\n"
        f"<code>{_esc(L.contact_phone)}</code>\n"
        f"Zona: {_esc(_short_zone(L.zone))}\n"
        f"Tipo: {_esc(L.typology or L.property_type)}\n"
        f"Preço: <b>{_fmt_price(L.price)}</b>\n"
        f"Score: {L.score}/100 · {L.score_label}\n"
        f"Estado: {_esc(stage)}\n"
    )
    if commission:
        msg += f"Comissão est.: <b>€{commission:,}</b>\n".replace(",", " ")
    msg += "\n"
    if brief_text:
        msg += f"<b>DOSSIER</b>\n<pre>{_esc(brief_text)}</pre>\n\n"
    if opening:
        msg += f"<b>OPENING WHATSAPP</b>\n<i>{_esc(opening)}</i>\n\n"
    if url:
        msg += f"🔗 <a href=\"{_esc(url)}\">Anúncio original</a>\n"
    if L.contact_phone:
        from urllib.parse import quote
        wa = f"https://wa.me/{L.contact_phone.lstrip('+').replace(' ','')}"
        if opening:
            wa += "?text=" + quote(opening)
        msg += f"💬 <a href=\"{_esc(wa)}\">Abrir WhatsApp</a>"
    _send(token, chat_id, msg)


def cmd_reengage(token: str, chat_id: int, args: list[str]) -> None:
    now = datetime.utcnow()
    with get_db() as db:
        leads = (db.query(Lead).filter(
            Lead.archived == False,                                   # noqa: E712
            Lead.re_engage_after.isnot(None),
            Lead.re_engage_after <= now,
        ).order_by(Lead.score.desc()).limit(15).all())
    if not leads:
        _send(token, chat_id, "Fila de re-engagement vazia ✓\nLeads aparecem aqui 30d depois de 'sem resposta'.")
        return
    parts = [f"🔄 <b>Re-engagement · {len(leads)} leads</b>\n"]
    for i, L in enumerate(leads, 1):
        last = L.last_contacted_at.strftime("%d/%m") if L.last_contacted_at else "—"
        stage = _PT_STAGE_LABELS.get(L.crm_stage, "—")
        parts.append(
            f"{i}. <b>#{L.id}</b> · {_esc(L.contact_name or '—')}\n"
            f"   última chamada {last} · {stage}\n"
            f"   <code>{_esc(L.contact_phone)}</code>"
        )
        parts.append("")
    _send(token, chat_id, "\n".join(parts))


def cmd_premarket(token: str, chat_id: int, args: list[str]) -> None:
    from sqlalchemy import func
    with get_db() as db:
        rows = db.query(
            PremktSignal.signal_type, func.count(PremktSignal.id)
        ).group_by(PremktSignal.signal_type).all()
        total = db.query(PremktSignal).count()
    if total == 0:
        _send(token, chat_id, "Sem sinais premarket no DB.")
        return
    labels = {
        "building_permit":          "🏗️ Licença obras",
        "renovation_ad_homeowner":  "🔨 Renovação (dono)",
        "renovation_ad_generic":    "🔧 Renovação",
        "linkedin_city_change":     "✈️ Mudança cidade",
        "linkedin_job_change":      "💼 Mudança profissional",
        "contractor_search_post":   "📋 Procura empreiteiro",
        "distressed_stale":         "❄ Listing frio (120+d)",
        "distressed_cross_portal":  "🔗 Multi-portal",
        "distressed_portfolio":     "📊 Portfolio 3-4",
    }
    parts = [f"📡 <b>Premarket · {total} sinais totais</b>\n"]
    for sig_type, n in sorted(rows, key=lambda x: -x[1]):
        lbl = labels.get(sig_type, sig_type)
        parts.append(f"{lbl}: <b>{n}</b>")
    _send(token, chat_id, "\n".join(parts))


def cmd_buscar(token: str, chat_id: int, args: list[str]) -> None:
    if not args:
        _send(token, chat_id, "Uso: /buscar Maria  (ou /buscar 91234)")
        return
    term = " ".join(args).strip()
    with get_db() as db:
        q = db.query(Lead).filter(Lead.archived == False)             # noqa: E712
        if term.replace("+", "").replace(" ", "").isdigit():
            q = q.filter(Lead.contact_phone.like(f"%{term}%"))
        else:
            q = q.filter(Lead.contact_name.ilike(f"%{term}%"))
        leads = q.order_by(Lead.score.desc()).limit(10).all()
    if not leads:
        _send(token, chat_id, f"Sem resultados para «{term}».")
        return
    parts = [f"🔎 <b>Busca «{term}» · {len(leads)} resultados</b>\n"]
    for i, L in enumerate(leads, 1):
        parts.append(_lead_summary_line(L, i))
        parts.append("")
    _send(token, chat_id, "\n".join(parts))


def cmd_brief(token: str, chat_id: int, args: list[str]) -> None:
    from pathlib import Path
    p = Path("logs/MORNING_BRIEF.txt")
    if not p.exists():
        try:
            from reports.morning_brief import generate_morning_brief
            generate_morning_brief()
        except Exception as e:
            _send(token, chat_id, f"Erro a gerar brief: {e}")
            return
    txt = p.read_text()[:3800]
    _send(token, chat_id, f"<pre>{html.escape(txt)}</pre>")


# ── Dispatcher ──────────────────────────────────────────────────────────────

COMMANDS: dict[str, Callable] = {
    "/start":     cmd_start,
    "/help":      cmd_help,
    "/kpi":       cmd_kpi,
    "/stats":     cmd_kpi,
    "/top":       cmd_top,
    "/tier":      cmd_tier,
    "/zona":      cmd_zona,
    "/lead":      cmd_lead,
    "/reengage":  cmd_reengage,
    "/premarket": cmd_premarket,
    "/buscar":    cmd_buscar,
    "/search":    cmd_buscar,
    "/brief":     cmd_brief,
    "/morning":   cmd_brief,
}


def _handle_update(token: str, update: dict) -> None:
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    log.info("[tg_bot] chat={c} from={n} text={t}",
             c=chat_id, n=chat.get("first_name", ""), t=text[:60])
    # Parse command + args
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]  # strip "@BotName" suffix
    args = parts[1:]
    handler = COMMANDS.get(cmd)
    if not handler:
        if cmd.startswith("/"):
            _send(token, chat_id,
                  "Comando não reconhecido. Manda /help para a lista.")
        return
    try:
        handler(token, chat_id, args)
    except Exception as e:
        log.error("[tg_bot] handler {c} crashed: {e}\n{tb}",
                  c=cmd, e=e, tb=traceback.format_exc())
        _send(token, chat_id, f"⚠ Erro interno: {html.escape(str(e))[:200]}")


# ── Main loop ───────────────────────────────────────────────────────────────

def run_bot(token: Optional[str] = None) -> None:
    """Long-polling loop. Blocks until killed (Ctrl-C or SIGTERM)."""
    token = token or settings.telegram_bot_token
    if not token:
        log.error("[tg_bot] no TELEGRAM_BOT_TOKEN configured")
        return

    # Verify bot
    me = _api(token, "getMe")
    if not me.get("ok"):
        log.error("[tg_bot] getMe failed: {e}", e=me)
        return
    log.info("[tg_bot] connected as @{u}", u=me["result"].get("username"))

    offset = 0
    while True:
        try:
            r = requests.get(
                API_BASE.format(token=token) + "/getUpdates",
                params={"offset": offset, "timeout": POLL_TIMEOUT},
                timeout=POLL_TIMEOUT + 5,
            ).json()
            if not r.get("ok"):
                log.warning("[tg_bot] getUpdates: {r}", r=r)
                time.sleep(5)
                continue
            for u in r.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                _handle_update(token, u)
        except KeyboardInterrupt:
            log.info("[tg_bot] stopped by user")
            return
        except Exception as e:
            log.error("[tg_bot] loop error: {e}", e=e)
            time.sleep(5)
