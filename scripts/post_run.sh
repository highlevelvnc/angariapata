#!/bin/bash
# Post-run pipeline · executes all steps after scrape to prepare leads
# for delivery to Susana. Each step is non-fatal — pipeline continues
# even if one step fails, so we always get *something* refreshed.

set -u
cd "$(dirname "$0")/.."

STAMP=$(date +%Y%m%d_%H%M%S)
LOG="logs/post_run_${STAMP}.log"
PROP_DIR="/Users/highlevel/proposta-ptbp"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

say "═══ Post-run pipeline start ═══"

# Capture baseline
LEADS_BEFORE=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM leads;" 2>/dev/null || echo 0)
HOT_BEFORE=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM leads WHERE score_label='HOT';" 2>/dev/null || echo 0)
say "Baseline · leads=$LEADS_BEFORE · hot=$HOT_BEFORE"

# ── Step 1a · Quality pass completo (Sprints Quality A,C,F,J,N) ──
# Cinco filtros sequenciais ANTES do score, para garantir integridade total
# antes da entrega à Susana:
#   F. Validação de phones (formato + mobile/landline)
#   A. Caça-flippers (phones em ≥4 listings)
#   J. Disguised agency detection by name pattern
#   C. Suspicious listings (spam/scam patterns)
#   N. Confidence score (0-100) por lead
say "→ 1a/8 Quality pass: 5 filtros de integridade (F+A+J+C+N)…"
python3 -c "from pipeline.quality_filter import cli_quality_pass; import json; print(json.dumps(cli_quality_pass(), indent=2, default=str))" >> "$LOG" 2>&1 \
  && say "  ✓ done" || say "  ✗ failed (non-fatal)"

# ── Step 1b · Mark dropped listings (Sprint Quality E) ───────────
# HEAD-check a primary URL; flip listing_status='dropped' on 404s.
# Removes ghost leads from old listings that already closed.
say "→ 1b/8 HEAD-check de URLs (remove leads fantasma)…"
python3 main.py detect-price-drops >> "$LOG" 2>&1 && say "  ✓ done" || say "  ✗ failed (non-fatal)"

# ── Step 1 · Score ────────────────────────────────────────────────
say "→ 1/6 Score (HOT/WARM/COLD classification)…"
python3 main.py score >> "$LOG" 2>&1 && say "  ✓ done" || say "  ✗ failed (non-fatal)"

# ── Step 2 · Geocode network ──────────────────────────────────────
say "→ 2/6 Geocoding (Nominatim · pode demorar 30-50min)…"
python3 main.py geocode-leads --limit 5000 >> "$LOG" 2>&1 && say "  ✓ done" || say "  ✗ failed (non-fatal)"

# ── Step 3 · Alerts ───────────────────────────────────────────────
say "→ 3/6 Disparar alertas para HOT leads…"
python3 main.py alerts >> "$LOG" 2>&1 && say "  ✓ done" || say "  ✗ failed (non-fatal)"

# ── Step 4 · Re-export commercial XLSX ────────────────────────────
say "→ 4/6 Gerar XLSX comercial fresco…"
python3 main.py export-commercial \
  --premium-limit 50 --expanded-limit 65 \
  --output-dir exports/ --format xlsx >> "$LOG" 2>&1 && say "  ✓ done" || say "  ✗ failed (non-fatal)"

LATEST_XLSX=$(ls -t exports/leads_comercial_*.xlsx 2>/dev/null | head -1)
say "  XLSX: $LATEST_XLSX"

# ── Step 5 · Refresh demo numbers + map data ──────────────────────
say "→ 5/6 Actualizar números no demo + mapa-data.json…"
python3 scripts/refresh_demo.py >> "$LOG" 2>&1 && say "  ✓ done" || say "  ✗ failed (non-fatal)"

# ── Step 6 · Sync proposta-ptbp + push ────────────────────────────
say "→ 6/6 Sync proposta-ptbp + push GitHub…"
if [ -d "$PROP_DIR" ]; then
  cp exports/demo_patabrava.html "$PROP_DIR/index.html"  2>>"$LOG" || true
  cp exports/mapa.html             "$PROP_DIR/mapa.html"  2>>"$LOG" || true
  cp exports/mapa-data.json        "$PROP_DIR/"            2>>"$LOG" || true
  cp exports/email-diario.html     "$PROP_DIR/"            2>>"$LOG" || true
  cp exports/mobile.html           "$PROP_DIR/"            2>>"$LOG" || true

  if [ -n "$LATEST_XLSX" ] && [ -f "$LATEST_XLSX" ]; then
    rm -f "$PROP_DIR"/leads_comercial_*.xlsx 2>/dev/null
    cp "$LATEST_XLSX" "$PROP_DIR/"
    NEW_NAME=$(basename "$LATEST_XLSX")
    # Update the JS XLSX_URL constant in the new index.html
    sed -i '' "s|leads_comercial_[0-9_]*\.xlsx|$NEW_NAME|g" "$PROP_DIR/index.html" 2>>"$LOG" || true
  fi

  cd "$PROP_DIR"
  if [ -n "$(git status --porcelain)" ]; then
    git add -A >> "$LOG" 2>&1
    GIT_AUTHOR_NAME="highlevelvnc" GIT_AUTHOR_EMAIL="vnc.oli@gmail.com" \
    GIT_COMMITTER_NAME="highlevelvnc" GIT_COMMITTER_EMAIL="vnc.oli@gmail.com" \
      git commit -m "Auto-refresh nocturno · $(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>&1 \
      && git push >> "$LOG" 2>&1 \
      && say "  ✓ pushed to GitHub" \
      || say "  ⚠ push falhou (provavelmente passphrase do agent expirou — empurras de manhã com 1 comando)"
  else
    say "  · sem alterações para push"
  fi
  cd - > /dev/null
fi

# ── Final stats ───────────────────────────────────────────────────
LEADS_AFTER=$(sqlite3 /Users/highlevel/ScrapperPatabrava/data/patabrava.db "SELECT COUNT(*) FROM leads;" 2>/dev/null || echo 0)
HOT_AFTER=$(sqlite3 /Users/highlevel/ScrapperPatabrava/data/patabrava.db "SELECT COUNT(*) FROM leads WHERE score_label='HOT';" 2>/dev/null || echo 0)
WARM_AFTER=$(sqlite3 /Users/highlevel/ScrapperPatabrava/data/patabrava.db "SELECT COUNT(*) FROM leads WHERE score_label='WARM';" 2>/dev/null || echo 0)
PHONE_AFTER=$(sqlite3 /Users/highlevel/ScrapperPatabrava/data/patabrava.db "SELECT COUNT(*) FROM leads WHERE contact_phone IS NOT NULL AND contact_phone!='';" 2>/dev/null || echo 0)

# ── Morning summary file ──────────────────────────────────────────
cat > /Users/highlevel/ScrapperPatabrava/logs/MORNING_SUMMARY.txt <<EOF
═══════════════════════════════════════════════════════════
  PATA BRAVA · SUMÁRIO DA NOITE
  Gerado em: $(date)
═══════════════════════════════════════════════════════════

DB FINAL
────────────────────────────
  Total leads ........ $LEADS_AFTER  (era $LEADS_BEFORE)
  HOT ................ $HOT_AFTER  (era $HOT_BEFORE)
  WARM ............... $WARM_AFTER
  Com telemóvel ...... $PHONE_AFTER

ENTREGÁVEL
────────────────────────────
  XLSX: $LATEST_XLSX
  Demo: $PROP_DIR/index.html

GITHUB
────────────────────────────
  $(cd "$PROP_DIR" 2>/dev/null && git log -1 --pretty=format:"%h · %s · %ar" 2>/dev/null || echo "—")

LOGS DA NOITE
────────────────────────────
  Run scraper: $(ls -t /Users/highlevel/ScrapperPatabrava/logs/run_*.log | head -1)
  Watchdog:    /Users/highlevel/ScrapperPatabrava/logs/watchdog.log
  Post-run:    $LOG

PRÓXIMOS PASSOS
────────────────────────────
  1. Verifica https://highlevelvnc.github.io/ptbp/ (se Pages activo)
  2. Reúne com Susana terça às 11h
EOF

# ── Step 7 · Idealista bonus pass (post-everything) ──────────────────
# Idealista uses DataDome enterprise. Runs LAST so failures don't impact
# the main delivery. If it works, we re-process + re-export to include
# the Idealista FSBO listings. If DataDome blocks, we skip silently.
say "→ 7/7 Idealista bonus pass (FSBO-only, after main delivery)…"

# Snapshot raw_listings before
RAW_BEFORE_IDEA=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM raw_listings WHERE source='idealista';" 2>/dev/null || echo 0)

# Force-run Idealista regardless of is_active flag
IDEALISTA_FSBO_ONLY=1 python3 main.py scrape --sources idealista >> "$LOG" 2>&1 || say "  ⚠ Idealista scrape falhou (DataDome?) — continuamos"

RAW_AFTER_IDEA=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM raw_listings WHERE source='idealista';" 2>/dev/null || echo 0)
IDEA_NEW=$((RAW_AFTER_IDEA - RAW_BEFORE_IDEA))

if [ "$IDEA_NEW" -gt 0 ]; then
  say "  ✓ Idealista trouxe $IDEA_NEW novos listings"
  # Process the new Idealista raw_listings
  python3 main.py process --source idealista --limit 5000 >> "$LOG" 2>&1
  # Re-run quality + score + export to include Idealista data
  python3 -c "from pipeline.quality_filter import cli_quality_pass; cli_quality_pass()" >> "$LOG" 2>&1
  python3 main.py score >> "$LOG" 2>&1
  python3 main.py export-commercial \
    --premium-limit 50 --expanded-limit 65 \
    --output-dir exports/ --format xlsx >> "$LOG" 2>&1
  python3 scripts/refresh_demo.py >> "$LOG" 2>&1

  # Re-sync to ptbp + force a second push
  cp exports/demo_patabrava.html "$PROP_DIR/index.html" 2>>"$LOG" || true
  cp exports/mapa-data.json      "$PROP_DIR/" 2>>"$LOG" || true
  LATEST_XLSX2=$(ls -t exports/leads_comercial_*.xlsx 2>/dev/null | head -1)
  if [ -n "$LATEST_XLSX2" ] && [ "$LATEST_XLSX2" != "$LATEST_XLSX" ]; then
    rm -f "$PROP_DIR"/leads_comercial_*.xlsx 2>/dev/null
    cp "$LATEST_XLSX2" "$PROP_DIR/"
    NEW_NAME2=$(basename "$LATEST_XLSX2")
    sed -i '' "s|leads_comercial_[0-9_]*\.xlsx|$NEW_NAME2|g" "$PROP_DIR/index.html" 2>>"$LOG" || true
  fi
  cd "$PROP_DIR"
  if [ -n "$(git status --porcelain)" ]; then
    git add -A >> "$LOG" 2>&1
    GIT_AUTHOR_NAME="highlevelvnc" GIT_AUTHOR_EMAIL="vnc.oli@gmail.com" \
    GIT_COMMITTER_NAME="highlevelvnc" GIT_COMMITTER_EMAIL="vnc.oli@gmail.com" \
      git commit -m "Refresh nocturno · +Idealista FSBO ($IDEA_NEW listings)" >> "$LOG" 2>&1 \
      && git push >> "$LOG" 2>&1 \
      && say "  ✓ pushed Idealista delta to GitHub" \
      || say "  ⚠ push do delta Idealista falhou"
  fi
  cd - > /dev/null
  echo "IDEALISTA_RESULT=success ($IDEA_NEW listings)" >> "$LOG"
else
  say "  · Idealista 0 listings (DataDome bloqueou OU já estava em delta-stop)"
  echo "IDEALISTA_RESULT=blocked_or_empty" >> "$LOG"
fi

say "═══ Post-run complete ═══"
say "Resumo da manhã: logs/MORNING_SUMMARY.txt"
