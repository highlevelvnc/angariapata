#!/usr/bin/env bash
# ─── Patabrava — ULTRA aggressive resume ───────────────────────────────────────
# Skips already-completed sources (OLX/Marketplace/Standvirtual/Imovirtual/Idealista
# have full delta cache from this run) and finishes only what's left:
#   - sapo + custojusto
#   - process 21k pending raw rows
#   - score, ML, signals, dedup, exports
#   - export-cliente (4-sheet xlsx for client)
# Full CPU priority (no nice). Delays 0.5-1.5s in .env.
set -e

cd "$(dirname "$0")"
source venv/bin/activate
mkdir -p logs

echo "=== Aggressive resume started: $(date) ==="

# Cheap insurance
python main.py backup --keep 14 || true

# Only the remaining sources — Imovirtual+Idealista already done
python main.py scrape --sources sapo,custojusto || true

# Drain the 21k pending
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    echo "--- post-process batch $i ---"
    python main.py process --limit 2000 || break
done

# Re-score after merges
python main.py score

# ML model + classification
python main.py train-owner-classifier || true
python main.py reclassify-owners --threshold 0.85 || true

# Signals + enrichment
python main.py detect-price-drops || true
python main.py enrich-sellers || true
python main.py enrich-websites --max-agencies 100 || true
python main.py geocode-leads --limit 2000 || true

# Photo dedup
python main.py hash-images --limit 1500 || true
python main.py dedup-photos --threshold 5 || true

# Maintenance
python main.py archive-stale --days 60 || true
python main.py sweep-dropped --limit 200 || true

# Tags + search index
python main.py tag-amenities --limit 2000 || true
python main.py rebuild-fts || true

# Final score pass + reports
python main.py score
python main.py trend-report || true
python main.py export-contacts --format both --score-min 30 || true
python main.py export-contacts --format both --score-min 50 || true
python main.py daily-digest --top 10 --score-min 60 || true

# ── CLIENT DELIVERABLE — Directriz scraping format ──────────────────────────
echo "--- entregável cliente (Directriz scraping) ---"
python main.py export-cliente

echo "=== Aggressive resume complete: $(date) ==="
