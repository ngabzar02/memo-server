"""CI step summary: build-cache log -> markdown.

Usage: python scripts/ci-summary-cache.py /tmp/build-cache.log >> "$GITHUB_STEP_SUMMARY"
"""
import re
import sys

log_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/build-cache.log"
try:
    log = open(log_path).read()
except OSError:
    log = ""
ok = len(re.findall(r"cache: \S+ OK", log))
fail = re.findall(r"cache: (\S+) FAIL", log)
print("## Build cache")
print("")
print("| metrik | jumlah |")
print("|---|---|")
print(f"| lib berhasil di-cache | {ok} |")
print(f"| lib gagal | {len(fail)} |")
if fail:
    print("")
    print(f"> Gagal: {', '.join(fail)}")
