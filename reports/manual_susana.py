"""
Manual da Susana · A4 PDF de 2 páginas que ela leva para a reunião / mesa.

Explica como usar a lista Pata Brava todos os dias:
  - O que cada coluna do XLSX significa
  - Como ligar (workflow daily)
  - O que preencher de volta (Estado / Notas / Data)
  - Re-engagement automático
  - Top quick-reference

Gera data/manual_susana.pdf.
"""
from __future__ import annotations

from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

GOLD   = HexColor("#ddc269")
INK    = HexColor("#0a0908")
BONE   = HexColor("#f7f1de")
DIM    = HexColor("#c5bea3")
CRIMS  = HexColor("#c62828")
GREEN  = HexColor("#1B5E20")

OUT = Path(__file__).resolve().parent.parent / "data" / "manual_susana.pdf"


def _h1(c, x, y, txt, size=22):
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, txt)
    c.setStrokeColor(GOLD); c.setLineWidth(1)
    c.line(x, y - 6, x + 80*mm, y - 6)


def _h2(c, x, y, txt):
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, txt.upper())


def _p(c, x, y, txt, size=10, color=BONE, font="Helvetica"):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, txt)


def _bullet(c, x, y, label, desc):
    c.setFillColor(GOLD); c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x, y, f"•  {label}")
    c.setFillColor(BONE); c.setFont("Helvetica", 9.5)
    c.drawString(x + 75*mm, y, desc)


def generate_manual() -> Path:
    c = canvas.Canvas(str(OUT), pagesize=A4)
    W, H = A4

    # ── Page 1 · Workflow ────────────────────────────────────────────────────
    c.setFillColor(INK); c.rect(0, 0, W, H, fill=1, stroke=0)

    # Header
    c.setFillColor(GOLD); c.setFont("Helvetica-Bold", 9)
    c.drawString(14*mm, H - 14*mm, "PATA BRAVA")
    c.setFillColor(DIM); c.setFont("Helvetica", 9)
    c.drawRightString(W - 14*mm, H - 14*mm, "MANUAL DA SUSANA · v1")

    y = H - 30*mm
    _h1(c, 14*mm, y, "Como usar a tua lista")
    y -= 14*mm

    _h2(c, 14*mm, y, "1.  De manhã, abre 2 coisas")
    y -= 8*mm
    _bullet(c, 16*mm, y, "logs/MORNING_BRIEF.txt", "resumo de 1 página com os top 10 para ligar")
    y -= 6*mm
    _bullet(c, 16*mm, y, "data/dashboard.html", "abre no browser — vê funil, KPIs, mapa")
    y -= 11*mm

    _h2(c, 14*mm, y, "2.  Pega no XLSX da pasta exports/")
    y -= 8*mm
    _p(c, 16*mm, y, "Procura o ficheiro mais recente: leads_comercial_YYYYMMDD_HHMMSS.xlsx")
    y -= 6*mm
    _p(c, 16*mm, y, "Tem 5 folhas — começa pela Lista Premium.", color=DIM)
    y -= 11*mm

    _h2(c, 14*mm, y, "3.  Para cada lead, abre o WhatsApp")
    y -= 8*mm
    _bullet(c, 16*mm, y, "Coluna 'WhatsApp'", "clique abre a conversa pronta com a opening")
    y -= 6*mm
    _bullet(c, 16*mm, y, "Coluna 'Briefing'", "5 linhas com tudo o que precisas saber antes de falar")
    y -= 6*mm
    _bullet(c, 16*mm, y, "Coluna 'Tier'", "A = quase certeza dono · B = provável · D = duvidoso")
    y -= 6*mm
    _bullet(c, 16*mm, y, "Coluna 'Comissão est.'", "valor a 5% sobre o preço — alavancagem na conversa")
    y -= 11*mm

    _h2(c, 14*mm, y, "4.  Marca o resultado (3 colunas no fim)")
    y -= 8*mm
    _bullet(c, 16*mm, y, "Estado", "✓ Convertido · Interessado · Sem resposta · Não interessado · Indisponível")
    y -= 6*mm
    _bullet(c, 16*mm, y, "Notas", "1-2 linhas do que se passou (texto livre)")
    y -= 6*mm
    _bullet(c, 16*mm, y, "Data Contacto", "DD/MM/YYYY (deixa em branco = usa hoje)")
    y -= 11*mm

    _h2(c, 14*mm, y, "5.  Devolve o XLSX ao motor")
    y -= 8*mm
    _p(c, 16*mm, y, "Terminal:  python3 main.py import-feedback <path-do-xlsx>",
       font="Courier", size=9.5)
    y -= 7*mm
    _p(c, 16*mm, y,
       "O motor lê o que preencheste, actualiza o DB, e ranqueia os próximos.",
       color=DIM)
    y -= 6*mm
    _p(c, 16*mm, y, "Leads com 'Sem resposta' voltam automaticamente daqui a 30 dias.",
       color=DIM)
    y -= 12*mm

    # Footer page 1
    c.setStrokeColor(GOLD); c.setLineWidth(0.5)
    c.line(14*mm, 22*mm, W - 14*mm, 22*mm)
    c.setFillColor(DIM); c.setFont("Helvetica", 8.5)
    c.drawString(14*mm, 16*mm, "Tens dúvidas? Pergunta — antes de fazer algo manual.")
    c.drawRightString(W - 14*mm, 16*mm, "Página 1 / 2")

    c.showPage()

    # ── Page 2 · Tabela de colunas + atalhos ─────────────────────────────────
    c.setFillColor(INK); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(GOLD); c.setFont("Helvetica-Bold", 9)
    c.drawString(14*mm, H - 14*mm, "PATA BRAVA")
    c.setFillColor(DIM); c.setFont("Helvetica", 9)
    c.drawRightString(W - 14*mm, H - 14*mm, "MANUAL DA SUSANA · v1")

    y = H - 30*mm
    _h1(c, 14*mm, y, "Cheat-sheet das colunas")
    y -= 14*mm

    cols = [
        ("Tier",          "A → liga primeiro. E → não ligues (switchboard de agência)."),
        ("Score",         "0-100. ≥60 HOT, ≥40 WARM. Quanto maior, mais sinal de venda."),
        ("Sinais",        "🔥 herança · 🥶 6m+ mercado · 🔗 em N portais · 👥 portfolio Nx"),
        ("Nome",          "Primeiro nome PT (Maria, João…). NULL = não temos nome."),
        ("Telefone",      "+351 9XX XXX XXX — mobile português validado."),
        ("Tipo Tel.",     "📱 telemóvel directo · 📞 fixo · 🔁 relay (NÃO chega ao dono)"),
        ("Tipologia",     "T0/T1/T2/T3+ ou Moradia/Terreno/Garagem."),
        ("Preço",         "Preço pedido. Comparar com benchmark € zona."),
        ("Briefing",      "5 linhas: portfolio, tempo, motivação, premarket, comissão, opening."),
        ("Opening",       "Linha pronta a copiar para o WhatsApp."),
        ("Comissão est.", "5% do preço (default Pata Brava luxury)."),
        ("Estado",        "← O QUE PREENCHES. Dropdown ou texto livre."),
        ("Notas",         "← O QUE PREENCHES. O que aconteceu na chamada."),
        ("Data Contacto", "← O QUE PREENCHES (opcional, default hoje)."),
        ("Lead ID",       "Não tocar — chave para o import-feedback."),
    ]
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(GOLD)
    c.drawString(14*mm, y, "COLUNA")
    c.drawString(50*mm, y, "O QUE É")
    y -= 4*mm
    c.setStrokeColor(GOLD); c.line(14*mm, y, W - 14*mm, y)
    y -= 5*mm
    for label, desc in cols:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(BONE)
        c.drawString(14*mm, y, label)
        c.setFont("Helvetica", 9)
        c.setFillColor(DIM if "← O QUE PREENCHES" not in desc else GOLD)
        c.drawString(50*mm, y, desc)
        y -= 5.5*mm

    y -= 6*mm
    _h2(c, 14*mm, y, "Atalhos terminal")
    y -= 8*mm
    shortcuts = [
        ("python3 main.py morning-prep",   "abre dashboard + gera cards + analytics"),
        ("python3 main.py import-feedback X.xlsx", "guarda o teu input no DB"),
        ("python3 main.py conversion-report",      "vê taxa de conversão por zona/tier"),
        ("cat logs/MORNING_BRIEF.txt",             "resumo da manhã em texto"),
    ]
    for cmd, desc in shortcuts:
        c.setFont("Courier-Bold", 9)
        c.setFillColor(GOLD)
        c.drawString(16*mm, y, cmd)
        c.setFont("Helvetica", 9)
        c.setFillColor(DIM)
        c.drawString(105*mm, y, desc)
        y -= 5.5*mm

    y -= 8*mm
    _h2(c, 14*mm, y, "Sinais de alerta")
    y -= 8*mm
    alerts = [
        ("Banner vermelho 'SEM TELEFONE'", "NÃO ligues. Contacta via portal (mensagem interna OLX)."),
        ("Folha '🔄 Re-engagement'",        "2ª tentativa — opening já reescrita com novo ângulo."),
        ("Tier 'E'",                       "Switchboard de agência. Ignora."),
        ("agency_name preenchido",         "Lead é mediadora, não dono — usa para benchmark."),
    ]
    for a, b in alerts:
        c.setFont("Helvetica-Bold", 9); c.setFillColor(CRIMS)
        c.drawString(16*mm, y, "⚠")
        c.setFont("Helvetica-Bold", 9); c.setFillColor(BONE)
        c.drawString(20*mm, y, a)
        c.setFont("Helvetica", 9); c.setFillColor(DIM)
        c.drawString(85*mm, y, b)
        y -= 5.5*mm

    # Footer page 2
    c.setStrokeColor(GOLD); c.setLineWidth(0.5)
    c.line(14*mm, 22*mm, W - 14*mm, 22*mm)
    c.setFillColor(DIM); c.setFont("Helvetica", 8.5)
    c.drawString(14*mm, 16*mm, "Imprime esta página, mantém na mesa.")
    c.drawRightString(W - 14*mm, 16*mm, "Página 2 / 2")

    c.save()
    return OUT


if __name__ == "__main__":
    p = generate_manual()
    print(f"✓ {p}")
