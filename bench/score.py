#!/usr/bin/env python3
"""score.py — evaluasi hasil benchmark MCP langsung (BRUTAL.md).

Baca bench/activity.log (JSONL ditulis server) + bench/queries.json,
hitung hit@k docs & resolve, cetak masalah utk diperbaiki.

Usage: python bench/score.py [--json]
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_queries() -> list[dict]:
    with open(os.path.join(ROOT, "queries.json")) as f:
        return json.load(f)


def load_activity() -> list[dict]:
    path = os.path.join(ROOT, "activity.log")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    queries = load_queries()
    acts = load_activity()
    by_lib = {}
    for q in queries:
        by_lib.setdefault(norm(q["library_name"]), []).append(q)

    resolve_hits = docs_total = docs_hit1 = docs_hit5 = 0
    misses = []
    for a in acts:
        if a["tool"] == "resolve":
            top = (a.get("top") or [{}])[0]
            if norm(top.get("id", "")) == norm(a["name"]) or (
                    norm(top.get("id", "")).replace("-", "") and
                    norm(a["name"]) in norm(top.get("id", ""))):
                resolve_hits += 1
        elif a["tool"] == "get_docs":
            qs = by_lib.get(norm(a["lib"])) or []
            qs = [q for q in qs if norm(q["query"][:24]) == norm(a["q"][:24])]
            if not qs:
                continue
            expected = qs[0].get("expected_path_fragments") or []
            if not expected:
                continue  # query tanpa fragment: tak dihitung relevance
            tops = a.get("top") or []
            hits = [i + 1 for i, p in enumerate(tops) if any(
                norm(f) in norm(p) for f in expected)]
            docs_total += 1
            if hits:
                docs_hit5 += 1
                if hits[0] <= 1:
                    docs_hit1 += 1
            else:
                misses.append({"lib": a["lib"], "q": a["q"], "ms": a.get("ms"),
                               "top": tops})

    pct1 = 100 * docs_hit1 / max(1, docs_total)
    pct5 = 100 * docs_hit5 / max(1, docs_total)
    if args.json:
        print(json.dumps({"resolve": resolve_hits, "docs": docs_total,
                          "hit1": docs_hit1, "hit5": docs_hit5,
                          "pct_hit1": round(pct1, 1), "pct_hit5": round(pct5, 1),
                          "misses": misses}, indent=1))
        return
    print(f"resolve hit : {resolve_hits}/{len([a for a in acts if a['tool']=='resolve'])}")
    print(f"docs hit@1  : {docs_hit1}/{docs_total} ({pct1:.0f}%)")
    print(f"docs hit@5  : {docs_hit5}/{docs_total} ({pct5:.0f}%)")
    for m in misses:
        print(f"  MISS {m['lib']}: {m['q'][:50]} ({m['ms']}ms)")
        for p in m["top"]:
            print(f"      - {p[:85]}")


if __name__ == "__main__":
    main()
