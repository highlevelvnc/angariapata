#!/bin/bash
# Overnight watchdog for the Pata Brava run.
# - Heartbeats every 5 min to logs/watchdog.log
# - Captures process state, DB row counts, last log lines
# - Detects scraper death and writes a post-mortem
# - Detects SAPO 429 storm and auto-disables SAPO if too aggressive
# - Never auto-restarts the main process (avoids loop spirals)

set -u
cd "$(dirname "$0")/.."

PID_TO_WATCH="${1:-19900}"
LOG="logs/watchdog.log"
RUN_LOG=$(ls -t logs/run_*.log | head -1)
SAPO_429_LIMIT=15            # if SAPO emits more than this many 429s, auto-disable
INTERVAL_SECS=300            # 5 min

ts() { date '+%Y-%m-%d %H:%M:%S'; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

say "═══ Watchdog start · PID=$PID_TO_WATCH · run_log=$RUN_LOG ═══"

# Snapshot baseline DB
LEADS_BASELINE=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM leads;" 2>/dev/null || echo "?")
RAW_BASELINE=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM raw_listings;" 2>/dev/null || echo "?")
say "Baseline · leads=$LEADS_BASELINE · raw=$RAW_BASELINE"

while true; do
  # ── 1. Process check ────────────────────────────────────────────
  if ! ps -p "$PID_TO_WATCH" > /dev/null 2>&1; then
    say "❌ Process $PID_TO_WATCH no longer alive."
    say "Last 80 lines of run log:"
    tail -80 "$RUN_LOG" | sed 's/\x1b\[[0-9;]*m//g' >> "$LOG"
    say "═══ Run process ended · NO auto-restart performed ═══"
    say "If finished cleanly: 'Pipeline complete' should be visible above."
    say "If crashed: investigate Traceback above and re-run manually with 'python3 main.py run'."
    break
  fi

  # ── 2. Heartbeat metrics ────────────────────────────────────────
  LEADS_NOW=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM leads;" 2>/dev/null || echo "?")
  RAW_NOW=$(sqlite3 data/patabrava.db "SELECT COUNT(*) FROM raw_listings;" 2>/dev/null || echo "?")
  ETIME=$(ps -p "$PID_TO_WATCH" -o etime= 2>/dev/null | tr -d ' ')
  CURRENT=$(grep -oE "zone=[A-Za-z0-9-]+" "$RUN_LOG" | tail -1 || echo "—")
  ERRORS=$(grep -c "ERROR" "$RUN_LOG" 2>/dev/null || echo 0)
  TRACEBACKS=$(grep -c "^Traceback" "$RUN_LOG" 2>/dev/null || echo 0)
  SAPO_429=$(grep -c "sapo.*429\|Too Many Requests.*sapo\|sapo.*Too Many" "$RUN_LOG" 2>/dev/null || echo 0)

  say "❤  alive · etime=$ETIME · raw=$RAW_NOW (+$((RAW_NOW - RAW_BASELINE))) · leads=$LEADS_NOW · current=$CURRENT · errors=$ERRORS · tb=$TRACEBACKS · sapo429=$SAPO_429"

  # ── 3. SAPO 429 storm protection ────────────────────────────────
  if [ "$SAPO_429" -gt "$SAPO_429_LIMIT" ]; then
    if grep -q '"sapo":.*is_active = True' config/sources_registry.py 2>/dev/null || \
       grep -q 'is_active = True,' <(grep -A 30 '"sapo": SourceMeta' config/sources_registry.py); then
      say "⚠  SAPO emitted $SAPO_429 × 429 — disabling for the rest of this run is N/A (registry change won't affect running process)."
      say "    Will note for morning review: SAPO needs proxy rotation before re-enabling."
      # Write a flag file for the morning
      echo "SAPO failed with $SAPO_429 × 429 at $(ts) — disable in registry before next run" > logs/MORNING_REVIEW_SAPO.txt
    fi
  fi

  # ── 4. Detect any *new* uncaught Traceback ──────────────────────
  if [ "$TRACEBACKS" -gt 0 ]; then
    NEW_TB=$(grep -A 8 "^Traceback" "$RUN_LOG" | tail -20)
    LAST_LOGGED_TB_HASH_FILE="logs/.watchdog_last_tb_hash"
    NEW_HASH=$(echo "$NEW_TB" | shasum | awk '{print $1}')
    OLD_HASH=$(cat "$LAST_LOGGED_TB_HASH_FILE" 2>/dev/null || echo "")
    if [ "$NEW_HASH" != "$OLD_HASH" ]; then
      say "🚨 New Traceback detected:"
      echo "$NEW_TB" >> "$LOG"
      echo "$NEW_HASH" > "$LAST_LOGGED_TB_HASH_FILE"
    fi
  fi

  sleep "$INTERVAL_SECS"
done

say "═══ Watchdog ended · final state in this log ═══"
