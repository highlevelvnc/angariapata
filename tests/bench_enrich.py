"""Profile inside enricher.enrich() to find the 20s/row hotspot."""
import sys, os, time, cProfile, pstats, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.database import get_db
from storage.repository import RawListingRepo
from pipeline.runner import PipelineRunner

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
runner = PipelineRunner()

with get_db() as db:
    raw_repo = RawListingRepo(db)
    rows = raw_repo.get_unprocessed(limit=N)
    normalised_list = []
    for raw in rows:
        n = runner.normalizer.normalize(raw.source, raw.get_data())
        if n and n.get("url"):
            normalised_list.append(n)

print(f"Profiling enrich() over {len(normalised_list)} rows...")
profiler = cProfile.Profile()
profiler.enable()
t0 = time.perf_counter()
for n in normalised_list:
    runner.enricher.enrich(n)
elapsed = time.perf_counter() - t0
profiler.disable()

print(f"Total: {elapsed:.2f}s ({elapsed/len(normalised_list)*1000:.1f} ms/row)")
print()
s = io.StringIO()
pstats.Stats(profiler, stream=s).sort_stats("cumulative").print_stats(25)
print(s.getvalue())
