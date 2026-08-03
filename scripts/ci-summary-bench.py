"""CI step summary: bench results (20 query vs Context7) -> markdown.

Usage: python scripts/ci-summary-bench.py <results_dir> >> "$GITHUB_STEP_SUMMARY"
"""
import glob
import json
import sys

results_dir = sys.argv[1] if len(sys.argv) > 1 else "bench/results"
files = sorted(glob.glob(f"{results_dir}/*.json"))
c7_hit = dm_hit = 0
misses = []
for f in files:
    e = json.load(open(f))
    c7_hit += 1 if e.get("c7", {}).get("hit") else 0
    if e.get("dm", {}).get("hit"):
        dm_hit += 1
    else:
        misses.append(e.get("lib", "?"))

print("## Bench (20 query vs Context7)")
print("")
print("| metrik | jumlah |")
print("|---|---|")
print(f"| query dieksekusi | {len(files)} |")
print(f"| memo hit | {dm_hit} |")
print(f"| Context7 hit | {c7_hit} |")
if misses:
    print("")
    print(f"> memo miss: {', '.join(misses)}")
