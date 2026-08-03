#!/usr/bin/env python3
"""replay_rrf.py — A/B tuning RRF k (P1-03) via replay offline 22 query.

Jalankan search hybrid langsung ke docs.db untuk tiap kandidat RRF k, hitung
hit@1/hit@5 dengan aturan norm yang sama seperti score.py. Tanpa network;
embedding query via fastembed (sama dengan server._embeddings).

Usage: UV_LINK_MODE=copy uv run python bench/replay_rrf.py [k1 k2 ...]
"""
import json
import os
import re
import sys

from fastembed import TextEmbedding

from memo import store

ROOT = os.path.dirname(os.path.abspath(__file__))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def hit_pos(paths: list[str], frags: list[str]) -> int | None:
    if not frags:
        return None
    for i, p in enumerate(paths[:5]):
        pl = p.lower()
        if any(f.lower() in pl for f in frags):
            return i + 1
    return None


def main() -> None:
    ks = [int(x) for x in sys.argv[1:]] or [20, 40, 60, 80, 100]
    queries = json.load(open(os.path.join(ROOT, "queries.json")))
    conn = store.connect()
    emb = TextEmbedding("BAAI/bge-small-en-v1.5", threads=2)
    results = {k: {"hit1": 0, "hit5": 0, "n": 0} for k in ks}
    per_lib = {k: {} for k in ks}
    for q in queries:
        frags = q.get("expected_path_fragments") or []
        if not frags:
            continue
        lib = q["library_name"]
        if store.get_lib(conn, lib) is None:
            print(f"skip {lib}: tidak di DB")
            continue
        vec = [float(x) for x in list(emb.embed([q["query"]]))[0]]
        for k in ks:
            hits = store.search(conn, lib, q["query"], k=10, query_vec=vec, rrf_k=k)
            pos = hit_pos([h["path"] for h in hits], frags)
            results[k]["n"] += 1
            if pos is not None:
                results[k]["hit5"] += 1
                if pos <= 1:
                    results[k]["hit1"] += 1
                per_lib[k][lib] = f"@{pos}"
            else:
                per_lib[k][lib] = "MISS"
    print(f"{'k':>4} {'hit@1':>8} {'hit@5':>8} {'n':>3}")
    for k in ks:
        r = results[k]
        p1 = 100 * r["hit1"] / max(1, r["n"])
        p5 = 100 * r["hit5"] / max(1, r["n"])
        print(f"{k:>4} {p1:>7.0f}% {p5:>7.0f}% {r['n']:>3}")
    print("\nper-lib detail (kandidat terbaik di antara ks):")
    best = max(ks, key=lambda k: (results[k]["hit5"], results[k]["hit1"]))
    for q in queries:
        lib = q["library_name"]
        if lib in per_lib[best]:
            print(f"  {lib:12s} {per_lib[best][lib]:>6}   {q['query'][:50]}")
    print(f"\nbest k = {best} (hit@5 {results[best]['hit5']}/{results[best]['n']})")


if __name__ == "__main__":
    main()
