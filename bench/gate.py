#!/usr/bin/env python3
"""gate.py — gate hit@5 untuk workflow bench-heavy.

Skor diambil dari tabel report.md yang di-render run_bench.py dari OUTPUT
CLIENT MCP (bukan activity.log — terbukti tidak 1:1, report-R4.md:5,20).

Exit code:
  0 = hit@5 >= threshold (PASS)  |  1 = hit@5 < threshold (FAIL)
  2 = report tidak bisa di-baca / tanpa query relevansi
  (dengan --allow-missing: report hilang -> 0, network dianggap skip)

Usage:
  python bench/gate.py --report bench/report.md --threshold 40
  python bench/gate.py --report bench/report.md --threshold 40 --quiet   # 1 baris utk step summary
"""
import argparse
import re
import sys

# Baris tabel docs run_bench.py: | # | library | memo hit@k | chunks | ms | tok | c7 hit@k | ...
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([\w.-]+)\s*\|\s*(@\d+|miss|n/a)\s*\|")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="bench/report.md")
    ap.add_argument("--threshold", type=float, default=40.0)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--allow-missing", action="store_true",
                    help="report hilang -> exit 0 (network down, gate skip)")
    args = ap.parse_args()

    try:
        text = open(args.report, encoding="utf-8").read()
    except OSError as e:
        if args.allow_missing:
            print(f"GATE: {args.report} tidak ada ({e}) — gate di-skip (network?)")
            return 0
        print(f"GATE: tidak bisa baca {args.report}: {e}", file=sys.stderr)
        return 2

    hits = total = 0
    for line in text.splitlines():
        m = _ROW.match(line)
        if m and m.group(3) != "n/a":  # hanya query ber-fragment yang relevansi diskor
            total += 1
            if m.group(3).startswith("@"):
                hits += 1
    if total == 0:
        print(f"GATE: tidak ada query relevansi (ber-fragment) di {args.report}", file=sys.stderr)
        return 2

    pct = 100.0 * hits / total
    ok = pct >= args.threshold
    line = f"hit@5 = {hits}/{total} ({pct:.1f}%) vs threshold {args.threshold:g}% -> {'PASS' if ok else 'FAIL'}"
    if args.quiet:
        print(line)
        return 0 if ok else 1
    print(f"GATE: {line}")
    print(f"GATE: skor dari output client MCP (report.md run_bench.py), bukan activity.log")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
