#!/bin/bash
# Refresh the Pata Brava demo with the latest DB state.
#
# Usage:
#   ./refresh-demo.sh                 # full: scrape + process + refresh + push
#   ./refresh-demo.sh --no-scrape     # skip scraper, just refresh from current DB
#   ./refresh-demo.sh --no-push       # build but don't push to GitHub
#
# Designed for Monday-night execution: run before bed, demo refreshed by morning.

set -e
cd "$(dirname "$0")"

NO_SCRAPE=0
NO_PUSH=0
for arg in "$@"; do
  case "$arg" in
    --no-scrape) NO_SCRAPE=1 ;;
    --no-push)   NO_PUSH=1 ;;
  esac
done

STAMP=$(date +%Y%m%d_%H%M%S)
LOG="logs/refresh_${STAMP}.log"
mkdir -p logs

echo "=== Pata Brava demo refresh · $(date) ==="
echo "Log: $LOG"
echo

# ── 1. Run scrape + full pipeline ────────────────────────────────────
if [ "$NO_SCRAPE" = "0" ]; then
  echo "→ Step 1/4 — scraping + pipeline (this is the long one, ~2-3h)…"
  python3 main.py run >> "$LOG" 2>&1
  echo "  done."
else
  echo "→ Step 1/4 — SKIPPED (--no-scrape)"
fi

# ── 2. Re-export commercial XLSX ─────────────────────────────────────
echo "→ Step 2/4 — generating fresh commercial export…"
python3 main.py export-commercial \
  --premium-limit 50 --expanded-limit 65 \
  --output-dir exports/ --format xlsx >> "$LOG" 2>&1
LATEST_XLSX=$(ls -t exports/leads_comercial_*.xlsx | head -1)
echo "  $LATEST_XLSX"

# ── 3. Refresh demo HTML + map data ──────────────────────────────────
echo "→ Step 3/4 — refreshing demo numbers…"
python3 scripts/refresh_demo.py >> "$LOG" 2>&1
tail -40 "$LOG" | grep -E "✓|⊘|Wrote|pins" || true

# ── 4. Sync proposta-ptbp + push ─────────────────────────────────────
echo "→ Step 4/4 — syncing to proposta-ptbp…"
PROP_DIR="/Users/highlevel/proposta-ptbp"
cp exports/demo_patabrava.html "$PROP_DIR/index.html"
cp exports/mapa.html "$PROP_DIR/mapa.html"
cp exports/mapa-data.json "$PROP_DIR/mapa-data.json"
cp exports/email-diario.html "$PROP_DIR/email-diario.html"
cp exports/mobile.html "$PROP_DIR/mobile.html"

# Replace the older XLSX with the latest one (cleanup)
rm -f "$PROP_DIR"/leads_comercial_*.xlsx
cp "$LATEST_XLSX" "$PROP_DIR/"

# Update the XLSX_URL constant in index.html to point at the new file
NEW_NAME=$(basename "$LATEST_XLSX")
sed -i '' "s|leads_comercial_[0-9_]*\.xlsx|$NEW_NAME|g" "$PROP_DIR/index.html"

if [ "$NO_PUSH" = "0" ]; then
  cd "$PROP_DIR"
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    GIT_AUTHOR_NAME="highlevelvnc" GIT_AUTHOR_EMAIL="vnc.oli@gmail.com" \
    GIT_COMMITTER_NAME="highlevelvnc" GIT_COMMITTER_EMAIL="vnc.oli@gmail.com" \
    git commit -m "Refresh · $(date '+%Y-%m-%d %H:%M') · auto-generated from refresh-demo.sh"
    git push
    echo "  pushed."
  else
    echo "  no changes to commit."
  fi
else
  echo "→ Step 4/4 — push SKIPPED (--no-push)"
fi

echo
echo "=== Done ==="
echo "Demo: $PROP_DIR/index.html"
echo "Public URL (if Pages active): https://highlevelvnc.github.io/ptbp/"
