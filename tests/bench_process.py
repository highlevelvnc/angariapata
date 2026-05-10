"""Quick profiler: time each phase of _process_one over N raw listings."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.database import get_db
from storage.repository import RawListingRepo, LeadRepo
from pipeline.runner import PipelineRunner

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
runner = PipelineRunner()

phases = {"normalize": 0.0, "fingerprint": 0.0, "lookup": 0.0, "enrich": 0.0,
          "create": 0.0, "record_price": 0.0, "mark": 0.0, "total": 0.0}

with get_db() as db:
    raw_repo = RawListingRepo(db)
    lead_repo = LeadRepo(db)
    rows = raw_repo.get_unprocessed(limit=N)
    print(f"Loaded {len(rows)} raw rows")
    t_total = time.perf_counter()
    for raw in rows:
        t0 = time.perf_counter()
        raw_data = raw.get_data()
        normalised = runner.normalizer.normalize(raw.source, raw_data)
        phases["normalize"] += time.perf_counter() - t0
        if not normalised or not normalised.get("url"):
            continue
        t0 = time.perf_counter()
        fp = runner.deduplicator.compute_fingerprint(normalised)
        phases["fingerprint"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        existing = lead_repo.get_by_fingerprint(fp)
        phases["lookup"] += time.perf_counter() - t0
        first_seen = existing.first_seen_at if existing else None
        t0 = time.perf_counter()
        enriched = runner.enricher.enrich(normalised, first_seen_at=first_seen)
        phases["enrich"] += time.perf_counter() - t0
        if not existing:
            t0 = time.perf_counter()
            data = runner._build_lead_data(enriched, fp, raw.source)
            new_lead = lead_repo.create(data)
            phases["create"] += time.perf_counter() - t0
            if new_lead.price:
                t0 = time.perf_counter()
                lead_repo.record_price(new_lead.id, new_lead.price, raw.source)
                phases["record_price"] += time.perf_counter() - t0
    db.rollback()  # don't actually persist
    phases["total"] = time.perf_counter() - t_total

print("\n=== Per-phase totals (s) ===")
for k, v in sorted(phases.items(), key=lambda x: -x[1]):
    print(f"  {k:14s} {v:7.3f}s   ({v/len(rows)*1000:6.1f} ms/row)")
print(f"\nThroughput: {len(rows)/phases['total']:.1f} rows/s = "
      f"{len(rows)/phases['total']*3600:.0f} rows/h")
