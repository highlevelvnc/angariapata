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

# Admin chat_ids — only these can run /run_start, /run_stop, etc.
# Add your chat_id here (descobre com /chatid no bot).
ADMIN_CHAT_IDS: set[int] = {722055603}  # Vinicius


# ── Telegram primitives ──────────────────────────────────────────────────────

def _api(token: str, method: str, **params) -> dict:
    url = API_BASE.format(token=token) + f"/{method}"
    try:
        r = requests.post(url, json=params, timeout=POLL_TIMEOUT + 5)
        return r.json()
    except Exception as e:
        log.error("[tg_bot] api {m} failed: {e}", m=method, e=e)
        return {"ok": False, "error": str(e)}


def _send(token: str, chat_id: int, text: str, parse: str = "HTML",
          keyboard: Optional[list] = None) -> None:
    """Send a text message. Optionally with an inline keyboard."""
    while text:
        chunk, text = text[:MAX_MSG_LEN], text[MAX_MSG_LEN:]
        payload = dict(
            chat_id=chat_id, text=chunk, parse_mode=parse,
            disable_web_page_preview=True,
        )
        if keyboard and not text:  # attach keyboard only to last chunk
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        _api(token, "sendMessage", **payload)


def _send_doc(token: str, chat_id: int, file_path: str,
              caption: str = "") -> None:
    """Send a file (PDF/XLSX/etc) as a document."""
    from pathlib import Path
    p = Path(file_path)
    if not p.exists():
        _send(token, chat_id, f"⚠ Ficheiro não existe: {p.name}")
        return
    url = API_BASE.format(token=token) + "/sendDocument"
    with open(p, "rb") as f:
        try:
            requests.post(url, data={
                "chat_id": chat_id, "caption": caption[:1000],
                "parse_mode": "HTML",
            }, files={"document": (p.name, f)}, timeout=60)
        except Exception as e:
            log.error("[tg_bot] sendDocument failed: {e}", e=e)
            _send(token, chat_id, f"⚠ Erro a enviar {p.name}: {e}")


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
        "<b>📚 Comandos disponíveis</b>\n\n"
        "<b>━ Leads ━</b>\n"
        "/top             Top 10 Tier A/B para chamar\n"
        "/tier A|B|C|D    Leads de um tier (até 15)\n"
        "/zona &lt;nome&gt;     ex: /zona Cascais\n"
        "/lead &lt;id&gt;       Dossier completo + WhatsApp\n"
        "/buscar &lt;termo&gt;  Procurar por nome/telefone\n"
        "/reengage        Fila de re-engagement (30d+)\n\n"
        "<b>━ Relatórios ━</b>\n"
        "/kpi             KPIs do dia (com botões)\n"
        "/relatorio       Relatório completo · por zona/source/tier\n"
        "/premarket       Sinais premarket por tipo\n"
        "/brief           MORNING_BRIEF.txt\n\n"
        "<b>━ Ficheiros (envia documentos) ━</b>\n"
        "/xlsx            Lista comercial (XLSX 5 folhas)\n"
        "/cards [id]      PDF cards · todos ou de um lead\n"
        "/audit           Audit Trail HTML\n"
        "/manual          Manual da Susana PDF\n\n"
        "<b>━ Admin (só admin) ━</b>\n"
        "/menu            Painel admin com botões\n"
        "/run_start       Iniciar scrapper\n"
        "/run_stop        Parar scrapper\n"
        "/run_status      Status + sources persistidas\n"
        "/run_log [N]     Últimas N linhas do log\n"
        "/refresh         Regenerar dashboard/audit/manual/brief\n"
        "/services        Lista serviços launchd activos\n"
        "/chatid          O teu chat_id"
    )
    _send(token, chat_id, msg)


def cmd_kpi(token: str, chat_id: int, args: list[str]) -> None:
    with get_db() as db:
        total = db.query(Lead).filter(Lead.archived == False).count()  # noqa: E712
        hot = db.query(Lead).filter(
            Lead.archived == False, Lead.score_label == "HOT").count()
        warm = db.query(Lead).filter(
            Lead.archived == False, Lead.score_label == "WARM").count()
        mobile = db.query(Lead).filter(
            Lead.archived == False, Lead.phone_type == "mobile").count()
        leads = db.query(Lead).filter(
            Lead.archived == False, Lead.contact_phone.isnot(None),
            Lead.phone_type == "mobile").all()
        ab = sum(1 for L in leads if _classify_owner_tier(L) in ("A", "B"))
        premkt = db.query(PremktSignal).count()
        now = datetime.utcnow()
        re_eng = db.query(Lead).filter(
            Lead.archived == False,
            Lead.re_engage_after.isnot(None),
            Lead.re_engage_after <= now).count()

    def _n(x): return f"{x:,}".replace(",", " ")
    msg = (
        f"📊 <b>PATA BRAVA · KPIs</b>\n"
        f"<i>{datetime.utcnow().strftime('%d/%m/%Y · %H:%M UTC')}</i>\n\n"
        f"<pre>"
        f"┌─────────────────────────────┐\n"
        f"│  COBERTURA                  │\n"
        f"├─────────────────────────────┤\n"
        f"│  Total leads      {_n(total):>10s}│\n"
        f"│  Mobile           {_n(mobile):>10s}│\n"
        f"├─────────────────────────────┤\n"
        f"│  CLASSIFICAÇÃO              │\n"
        f"├─────────────────────────────┤\n"
        f"│  HOT  (≥60)       {_n(hot):>10s}│\n"
        f"│  WARM (≥40)       {_n(warm):>10s}│\n"
        f"│  Tier A+B real    {_n(ab):>10s}│\n"
        f"├─────────────────────────────┤\n"
        f"│  WORKFLOW                   │\n"
        f"├─────────────────────────────┤\n"
        f"│  Re-engage hoje   {_n(re_eng):>10s}│\n"
        f"│  Premarket sinais {_n(premkt):>10s}│\n"
        f"└─────────────────────────────┘"
        f"</pre>"
    )
    kb = [[
        {"text": "📞 Top 10", "callback_data": "/top"},
        {"text": "🔄 Re-engage", "callback_data": "/reengage"},
    ], [
        {"text": "📡 Premarket", "callback_data": "/premarket"},
        {"text": "📋 Relatório", "callback_data": "/relatorio"},
    ]]
    _send(token, chat_id, msg, keyboard=kb)


def cmd_relatorio(token: str, chat_id: int, args: list[str]) -> None:
    """Relatório completo + opção de receber XLSX."""
    from collections import Counter
    with get_db() as db:
        total = db.query(Lead).filter(Lead.archived == False).count()
        hot = db.query(Lead).filter(
            Lead.archived == False, Lead.score_label == "HOT").count()
        # By source
        from sqlalchemy import func
        by_src = dict(db.query(Lead.discovery_source, func.count(Lead.id))
                      .filter(Lead.archived == False)
                      .group_by(Lead.discovery_source).all())
        # By zone (top 8)
        by_zone = (db.query(Lead.zone, func.count(Lead.id))
                   .filter(Lead.archived == False,
                           Lead.zone.isnot(None))
                   .group_by(Lead.zone)
                   .order_by(func.count(Lead.id).desc())
                   .limit(8).all())
        # Tier breakdown
        leads = db.query(Lead).filter(
            Lead.archived == False, Lead.contact_phone.isnot(None),
            Lead.phone_type == "mobile").all()
        tiers = Counter(_classify_owner_tier(L) for L in leads)
        premkt_total = db.query(PremktSignal).count()
        premkt_by = dict(db.query(PremktSignal.signal_type,
                                    func.count(PremktSignal.id))
                         .group_by(PremktSignal.signal_type).all())

    def _n(x): return f"{x:,}".replace(",", " ")

    msg = (
        f"📋 <b>RELATÓRIO COMPLETO</b>\n"
        f"<i>{datetime.utcnow().strftime('%d/%m/%Y · %H:%M UTC')}</i>\n\n"
        f"<b>━━━ COBERTURA ━━━</b>\n"
        f"<pre>"
        f"Total leads:    {_n(total)}\n"
        f"HOT (≥60):      {_n(hot)}"
        f"</pre>\n"
        f"<b>━━━ POR SOURCE ━━━</b>\n<pre>"
    )
    for src, n in sorted(by_src.items(), key=lambda x: -x[1])[:10]:
        if src:
            msg += f"{(src or '—')[:18]:18s}{_n(n):>8s}\n"
    msg += "</pre>\n"

    msg += "<b>━━━ TOP ZONAS ━━━</b>\n<pre>"
    for zone, n in by_zone:
        z = _short_zone(zone) or "—"
        msg += f"{z[:20]:20s}{_n(n):>6s}\n"
    msg += "</pre>\n"

    msg += "<b>━━━ TIER (mobile) ━━━</b>\n<pre>"
    for t in ("A", "B", "C", "D", "E", "?"):
        if tiers.get(t):
            msg += f"Tier {t}: {_n(tiers[t])}\n"
    msg += "</pre>\n"

    msg += f"<b>━━━ PREMARKET · {premkt_total} sinais ━━━</b>\n<pre>"
    labels = {
        "building_permit":         "🏗  Licença obras",
        "renovation_ad_homeowner": "🔨 Renovação dono",
        "renovation_ad_generic":   "🔧 Renovação",
        "distressed_stale":        "❄  Listing frio",
        "distressed_cross_portal": "🔗 Multi-portal",
        "distressed_portfolio":    "📊 Portfolio 3-4",
        "linkedin_city_change":    "✈  Mudança cidade",
        "linkedin_job_change":     "💼 Mudança job",
    }
    for sig, n in sorted(premkt_by.items(), key=lambda x: -x[1]):
        lbl = labels.get(sig, sig)[:22]
        msg += f"{lbl:22s}{_n(n):>5s}\n"
    msg += "</pre>"

    kb = [[
        {"text": "📥 Receber XLSX", "callback_data": "/xlsx"},
        {"text": "📥 Receber Brief", "callback_data": "/brief"},
    ]]
    _send(token, chat_id, msg, keyboard=kb)


def cmd_xlsx(token: str, chat_id: int, args: list[str]) -> None:
    """Envia o XLSX comercial mais recente."""
    import glob, os
    files = sorted(glob.glob("exports/leads_comercial_*.xlsx"),
                   key=os.path.getmtime, reverse=True)
    if not files:
        _send(token, chat_id, "Sem XLSX gerado · corre <code>python main.py export-commercial</code>.")
        return
    latest = files[0]
    fname = os.path.basename(latest)
    cap = (f"📊 <b>Lista Comercial</b>\n"
           f"<i>{fname}</i>\n\n"
           f"5 folhas: Premium · Expandida · ⚠ Sem Telefone · 🔄 Re-engagement · Resumo")
    _send_doc(token, chat_id, latest, caption=cap)


def cmd_cards(token: str, chat_id: int, args: list[str]) -> None:
    """Envia o PDF card de um lead específico OU os top N."""
    import glob, os
    if args and args[0].isdigit():
        # Single lead PDF
        lead_id = int(args[0])
        pdf = f"data/lead_cards/lead_{lead_id:05d}.pdf"
        if not os.path.exists(pdf):
            _send(token, chat_id, f"PDF card para lead #{lead_id} não existe ainda.\nCorre <code>python main.py generate-cards</code>.")
            return
        _send_doc(token, chat_id, pdf,
                  caption=f"📄 <b>Lead Card #{lead_id}</b>")
        return
    # All cards — send max 5 to avoid spam
    pdfs = sorted(glob.glob("data/lead_cards/lead_*.pdf"))
    if not pdfs:
        _send(token, chat_id, "Sem PDFs gerados · corre <code>python main.py generate-cards</code>.")
        return
    _send(token, chat_id, f"📄 A enviar primeiros 5 de {len(pdfs)} cards…")
    for p in pdfs[:5]:
        _send_doc(token, chat_id, p)


def cmd_audit(token: str, chat_id: int, args: list[str]) -> None:
    """Envia o audit_trail.html."""
    import os
    p = "data/audit_trail.html"
    if not os.path.exists(p):
        _send(token, chat_id, "Sem audit trail · corre <code>python main.py audit-trail</code>.")
        return
    _send_doc(token, chat_id, p,
              caption=("🔍 <b>Audit Trail</b>\n\n"
                       "HTML self-contained · abre no browser para ver "
                       "leads com fotos + URLs clicáveis do anúncio original."))


def cmd_manual(token: str, chat_id: int, args: list[str]) -> None:
    """Envia o manual da Susana."""
    import os
    p = "data/manual_susana.pdf"
    if not os.path.exists(p):
        try:
            from reports.manual_susana import generate_manual
            generate_manual()
        except Exception:
            _send(token, chat_id, "Sem manual gerado.")
            return
    _send_doc(token, chat_id, p,
              caption="📖 <b>Manual da Susana</b> · workflow daily + cheat-sheet")


# ── ADMIN COMMANDS ──────────────────────────────────────────────────────────
# Restritos a ADMIN_CHAT_IDS. Outros utilizadores vêem "Sem permissão".

def _is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_CHAT_IDS


def _admin_only(handler):
    """Decorator que rejeita chamadas de chat_ids não-admin."""
    def wrapped(token: str, chat_id: int, args: list[str]) -> None:
        if not _is_admin(chat_id):
            _send(token, chat_id, "⛔ Sem permissão · este comando é só admin.")
            return
        handler(token, chat_id, args)
    return wrapped


def _run_pid() -> Optional[int]:
    """Return PID do main.py run, ou None se não estiver a correr."""
    import subprocess
    try:
        r = subprocess.run(
            ["pgrep", "-f", "main.py run"],
            capture_output=True, text=True, timeout=3,
        )
        for line in r.stdout.strip().split("\n"):
            if line.strip().isdigit():
                # Verify it's actually our scraper run (not e.g. import or generate)
                ps = subprocess.run(
                    ["ps", "-p", line.strip(), "-o", "command="],
                    capture_output=True, text=True, timeout=2,
                ).stdout
                if "main.py run" in ps and "morning" not in ps and "import" not in ps:
                    return int(line.strip())
    except Exception:
        pass
    return None


@_admin_only
def cmd_menu(token: str, chat_id: int, args: list[str]) -> None:
    """Menu admin com inline keyboard."""
    pid = _run_pid()
    status_line = (f"🟢 Scrapper a correr · PID {pid}"
                   if pid else "⚪ Scrapper parado")
    msg = (
        f"⚙️ <b>MENU ADMIN</b>\n\n{status_line}\n\n"
        "Escolhe uma acção:"
    )
    kb = [
        [
            {"text": "▶ Iniciar Scrapper",  "callback_data": "/run_start"},
            {"text": "⏹ Parar Scrapper",    "callback_data": "/run_stop"},
        ],
        [
            {"text": "📊 Status",            "callback_data": "/run_status"},
            {"text": "📜 Log (tail)",        "callback_data": "/run_log"},
        ],
        [
            {"text": "🔄 Refresh Reports",   "callback_data": "/refresh"},
            {"text": "🛠 Services",          "callback_data": "/services"},
        ],
        [
            {"text": "📊 KPIs",              "callback_data": "/kpi"},
            {"text": "📋 Relatório",         "callback_data": "/relatorio"},
        ],
    ]
    _send(token, chat_id, msg, keyboard=kb)


@_admin_only
def cmd_run_start(token: str, chat_id: int, args: list[str]) -> None:
    """Inicia uma run completa do scrapper em background."""
    import subprocess
    from pathlib import Path
    pid = _run_pid()
    if pid:
        _send(token, chat_id,
              f"⚠ Já há uma run a correr · PID {pid}.\n"
              f"Manda /run_stop primeiro se quiseres reiniciar.")
        return
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = Path(f"logs/run_{stamp}.log")
    try:
        # Launch detached
        with open(log_path, "w") as f:
            proc = subprocess.Popen(
                ["python3", "main.py", "run"],
                stdout=f, stderr=subprocess.STDOUT,
                cwd="/Users/highlevel/ScrapperPatabrava",
                start_new_session=True,
            )
        # auto_after_run watcher
        subprocess.Popen(
            ["./scripts/auto_after_run.sh", str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd="/Users/highlevel/ScrapperPatabrava",
            start_new_session=True,
        )
        _send(token, chat_id,
              f"🚀 <b>Run lançada</b>\n\n"
              f"PID: <code>{proc.pid}</code>\n"
              f"Log: <code>{log_path}</code>\n"
              f"ETA: 3-4h · post-run automático no fim.\n\n"
              f"Manda /run_status para ver progresso.")
    except Exception as e:
        _send(token, chat_id, f"⚠ Falhou a lançar: {html.escape(str(e))[:200]}")


@_admin_only
def cmd_run_stop(token: str, chat_id: int, args: list[str]) -> None:
    """Mata a run actual do scrapper."""
    import subprocess
    pid = _run_pid()
    if not pid:
        _send(token, chat_id, "⚪ Scrapper já está parado.")
        return
    try:
        subprocess.run(["kill", "-TERM", str(pid)], timeout=5)
        # Also kill auto_after_run
        subprocess.run(["pkill", "-f", "auto_after_run.sh"],
                       capture_output=True, timeout=5)
        _send(token, chat_id,
              f"⏹ <b>Scrapper terminado</b> · PID {pid} (SIGTERM)\n\n"
              f"auto_after_run também parado.")
    except Exception as e:
        _send(token, chat_id, f"⚠ Erro: {html.escape(str(e))[:200]}")


@_admin_only
def cmd_run_status(token: str, chat_id: int, args: list[str]) -> None:
    """Status detalhado da run actual."""
    import subprocess
    import glob, os
    pid = _run_pid()
    if not pid:
        _send(token, chat_id,
              "⚪ <b>Scrapper parado</b>\n\nManda /run_start para iniciar.")
        return
    # Get elapsed
    try:
        r = subprocess.run(
            ["ps", "-p", str(pid), "-o", "etime="],
            capture_output=True, text=True, timeout=3,
        )
        etime = r.stdout.strip()
    except Exception:
        etime = "?"
    # Find current log
    logs = sorted(glob.glob("logs/run_*.log"), key=os.path.getmtime, reverse=True)
    log_file = os.path.basename(logs[0]) if logs else "?"
    # Sources completed
    try:
        with open(logs[0]) as f:
            content = f.read()
        import re
        persisted = re.findall(r"Persisted (\d+) new raw listings from (\w+)", content)
        sources_done = "\n".join([f"  ✓ {src}: <b>+{n}</b>" for n, src in persisted])
        # Current activity (last source mentioned)
        last_source = re.findall(r"--- Scraping: (\w+)", content)
        current = last_source[-1] if last_source else "?"
        last_lines = content.split("\n")[-2:]
        last_line = "\n".join(l[:140] for l in last_lines if l.strip())
    except Exception:
        sources_done = ""
        current = "?"
        last_line = ""

    msg = (
        f"📊 <b>SCRAPPER ESTADO</b>\n\n"
        f"PID: <code>{pid}</code>\n"
        f"Elapsed: <b>{etime}</b>\n"
        f"Log: <code>{log_file}</code>\n"
        f"Source actual: <b>{current}</b>\n"
    )
    if sources_done:
        msg += f"\n<b>Sources persistidas:</b>\n{sources_done}\n"
    if last_line:
        msg += f"\n<pre>{html.escape(last_line)}</pre>"
    kb = [[
        {"text": "📜 Tail Log", "callback_data": "/run_log"},
        {"text": "⏹ Parar",     "callback_data": "/run_stop"},
    ]]
    _send(token, chat_id, msg, keyboard=kb)


@_admin_only
def cmd_run_log(token: str, chat_id: int, args: list[str]) -> None:
    """Últimas linhas do log da run."""
    import glob, os, re
    n = 15
    if args and args[0].isdigit():
        n = min(int(args[0]), 50)
    logs = sorted(glob.glob("logs/run_*.log"), key=os.path.getmtime, reverse=True)
    if not logs:
        _send(token, chat_id, "Sem logs.")
        return
    try:
        with open(logs[0]) as f:
            lines = f.readlines()
        tail = lines[-n:]
        # Strip ANSI escape codes
        ansi = re.compile(r"\x1b\[[0-9;]*m")
        clean = "".join(ansi.sub("", l) for l in tail)
        # Truncate to fit Telegram
        clean = clean[-3500:]
        _send(token, chat_id,
              f"📜 <b>Log · {os.path.basename(logs[0])}</b>\n\n"
              f"<pre>{html.escape(clean)}</pre>")
    except Exception as e:
        _send(token, chat_id, f"Erro: {html.escape(str(e))[:200]}")


@_admin_only
def cmd_refresh(token: str, chat_id: int, args: list[str]) -> None:
    """Regenera dashboard, audit_trail, manual, e morning_brief."""
    _send(token, chat_id, "🔄 A regenerar relatórios…")
    try:
        from reports.morning_dashboard import generate_dashboard
        generate_dashboard()
        from reports.audit_trail import generate_audit
        generate_audit(limit=10)
        from reports.manual_susana import generate_manual
        generate_manual()
        from reports.morning_brief import generate_morning_brief
        generate_morning_brief()
        _send(token, chat_id,
              "✅ <b>Relatórios actualizados</b>\n\n"
              "  · dashboard.html\n"
              "  · audit_trail.html\n"
              "  · manual_susana.pdf\n"
              "  · MORNING_BRIEF.txt\n\n"
              "Manda /brief para ver o brief actualizado.")
    except Exception as e:
        _send(token, chat_id, f"⚠ Erro: {html.escape(str(e))[:300]}")


@_admin_only
def cmd_services(token: str, chat_id: int, args: list[str]) -> None:
    """Status de todos os serviços launchd da Pata Brava."""
    import subprocess
    try:
        r = subprocess.run(["launchctl", "list"],
                           capture_output=True, text=True, timeout=5)
        services = [l for l in r.stdout.split("\n") if "patabrava" in l.lower()]
    except Exception as e:
        _send(token, chat_id, f"Erro: {e}")
        return
    msg = "<b>🛠 SERVIÇOS</b>\n\n"
    if not services:
        msg += "Sem serviços patabrava activos."
    else:
        msg += "<pre>"
        for s in services:
            parts = s.split()
            if len(parts) >= 3:
                pid, status, label = parts[0], parts[1], parts[2]
                emoji = "🟢" if pid != "-" else "⚪"
                msg += f"{emoji} {label:35s} pid={pid}\n"
        msg += "</pre>\n"
        msg += "\n<i>com.patabrava.nightly · run automática 03:00\n"
        msg += "com.patabrava.telegram-bot · este bot</i>"
    scraper_pid = _run_pid()
    if scraper_pid:
        msg += f"\n\n🟢 Scrapper run · PID {scraper_pid}"
    _send(token, chat_id, msg)


def cmd_chatid(token: str, chat_id: int, args: list[str]) -> None:
    """Devolve o teu chat_id (útil para adicionar a ADMIN_CHAT_IDS)."""
    _send(token, chat_id,
          f"O teu chat_id é <code>{chat_id}</code>\n\n"
          f"Para te tornares admin, adiciona este ID a "
          f"<code>ADMIN_CHAT_IDS</code> em <code>bots/telegram_bot.py</code>.")


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
        _send(token, chat_id,
              "🟡 <b>Sem Tier A/B fresco hoje</b>\n\n"
              "Acontece quando a base está limpa ou esperamos pela próxima "
              "run nocturna (03:00).\n\n"
              "Manda /reengage para a fila de re-contacto.")
        return

    parts = [f"📞 <b>TOP {len(top)} PARA CHAMAR</b>\n<i>{datetime.utcnow().strftime('%d/%m %H:%M')} UTC</i>\n\n"]
    # Build inline keyboard with lead detail shortcuts (max 8 buttons)
    kb_rows = []
    row = []
    for i, L in enumerate(top, 1):
        parts.append(_lead_summary_line(L, i))
        parts.append("")
        if i <= 8:
            row.append({"text": f"#{i}", "callback_data": f"/lead {L.id}"})
            if len(row) == 4:
                kb_rows.append(row); row = []
    if row:
        kb_rows.append(row)
    kb_rows.append([
        {"text": "🔄 Re-engage", "callback_data": "/reengage"},
        {"text": "📋 Relatório", "callback_data": "/relatorio"},
    ])
    parts.append("<i>Toca num # para ver o dossier completo.</i>")
    _send(token, chat_id, "\n".join(parts), keyboard=kb_rows)


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
    "/start":      cmd_start,
    "/help":       cmd_help,
    "/kpi":        cmd_kpi,
    "/stats":      cmd_kpi,
    "/top":        cmd_top,
    "/tier":       cmd_tier,
    "/zona":       cmd_zona,
    "/lead":       cmd_lead,
    "/reengage":   cmd_reengage,
    "/premarket":  cmd_premarket,
    "/buscar":     cmd_buscar,
    "/search":     cmd_buscar,
    "/brief":      cmd_brief,
    "/morning":    cmd_brief,
    "/relatorio":  cmd_relatorio,
    "/report":     cmd_relatorio,
    "/xlsx":       cmd_xlsx,
    "/cards":      cmd_cards,
    "/audit":      cmd_audit,
    "/manual":     cmd_manual,
    # ── Admin (gated by ADMIN_CHAT_IDS) ──────────────────────────────────
    "/menu":       cmd_menu,
    "/admin":      cmd_menu,
    "/run_start":  cmd_run_start,
    "/start_run":  cmd_run_start,
    "/run_stop":   cmd_run_stop,
    "/stop_run":   cmd_run_stop,
    "/run_status": cmd_run_status,
    "/status":     cmd_run_status,
    "/run_log":    cmd_run_log,
    "/log":        cmd_run_log,
    "/refresh":    cmd_refresh,
    "/services":   cmd_services,
    "/chatid":     cmd_chatid,
}


def _dispatch_text(token: str, chat_id: int, text: str, who: str = "") -> None:
    """Parse a text command and run the handler. Shared by message + callback paths."""
    log.info("[tg_bot] chat={c} from={n} text={t}",
             c=chat_id, n=who, t=text[:60])
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]  # strip @BotName
    args = parts[1:]
    handler = COMMANDS.get(cmd)
    if not handler:
        if cmd.startswith("/"):
            _send(token, chat_id, "Comando não reconhecido. Manda /help.")
        return
    try:
        handler(token, chat_id, args)
    except Exception as e:
        log.error("[tg_bot] handler {c} crashed: {e}\n{tb}",
                  c=cmd, e=e, tb=traceback.format_exc())
        _send(token, chat_id, f"⚠ Erro interno: {html.escape(str(e))[:200]}")


def _handle_update(token: str, update: dict) -> None:
    # Inline keyboard button → callback_query
    cq = update.get("callback_query")
    if cq:
        chat = (cq.get("message") or {}).get("chat", {})
        chat_id = chat.get("id")
        data = cq.get("data", "")
        # Acknowledge the callback to remove the loading spinner
        _api(token, "answerCallbackQuery", callback_query_id=cq.get("id"))
        if chat_id and data:
            _dispatch_text(token, chat_id, data, who=chat.get("first_name", ""))
        return

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    _dispatch_text(token, chat_id, text, who=chat.get("first_name", ""))


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
