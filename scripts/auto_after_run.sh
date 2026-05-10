#!/bin/bash
# Auto-after-run · waits for the scraper PID to exit, then triggers post_run.sh
# if the run completed cleanly. Designed to be launched at the same time as
# the scraper, so post-processing happens automatically once scraping finishes.

set -u
SCRAPER_PID="${1:-19900}"
cd "$(dirname "$0")/.."

LOG="logs/auto_after_run.log"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] ═══ auto-after-run watching PID=$SCRAPER_PID ═══" >> "$LOG"

# Block until the scraper PID exits (poll every 60s)
while ps -p "$SCRAPER_PID" > /dev/null 2>&1; do
  sleep 60
done

echo "[$(ts)] Scraper PID=$SCRAPER_PID exited. Inspecting log…" >> "$LOG"

# Find the run log this PID was writing to
RUN_LOG=$(ls -t logs/run_*.log 2>/dev/null | head -1)

if [ -z "$RUN_LOG" ] || [ ! -f "$RUN_LOG" ]; then
  echo "[$(ts)] ⚠  No run log found. Skipping post-run." >> "$LOG"
  echo "Manual review required — run log missing" > logs/MORNING_REVIEW.txt
  exit 0
fi

# Sanity check: did the run reach 'Pipeline complete'?
if grep -q "Pipeline complete" "$RUN_LOG"; then
  echo "[$(ts)] ✓ Clean completion detected. Triggering post-run pipeline…" >> "$LOG"
  /Users/highlevel/ScrapperPatabrava/scripts/post_run.sh
  echo "[$(ts)] ═══ Post-run completed ═══" >> "$LOG"
else
  echo "[$(ts)] ✗ 'Pipeline complete' not found in run log. Possible crash." >> "$LOG"
  echo "Last 30 log lines:" >> "$LOG"
  tail -30 "$RUN_LOG" | sed 's/\x1b\[[0-9;]*m//g' >> "$LOG"
  cat > logs/MORNING_REVIEW.txt <<EOF
SCRAPER NÃO COMPLETOU LIMPO
═══════════════════════════════════════════════════════════
Última actividade no run log:
$(tail -10 "$RUN_LOG" | sed 's/\x1b\[[0-9;]*m//g')

Acção sugerida ao acordares:
  1. tail -100 $RUN_LOG
  2. Se foi 429/anti-block: re-run partial com python3 main.py process
  3. Se foi crash código: investigar Traceback e corrigir
  4. Re-disparar post-run manual: ./scripts/post_run.sh
EOF
  echo "[$(ts)] Wrote logs/MORNING_REVIEW.txt for human review." >> "$LOG"
fi
