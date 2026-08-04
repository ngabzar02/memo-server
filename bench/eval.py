"""bench/eval — evaluasi offline retrieval (hit@k) terhadap golden set.

Menjalankan stack retrieval persis seperti get_docs TANPA network/ingest:
  store.search (hybrid FTS+vec, RRF, dedupe) -> _rerank -> hit@k pada path.
Embed query & reranker dimuat lokal sekali. DB dibaca (read-only via store).

Usage:
  python bench/eval.py                        # bench/golden.json -> bench/rounds/<ts>.json
  python bench/eval.py --golden bench/queries.json --topn 5
"""

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from memo import server, store  # noqa: E402


def _hit(hits, fragments) -> tuple[int, int, int]:
    """hit@1/@3/@5: setidaknya satu fragment muncul di path hit mana pun.
    fragments kosong -> (0,0,0) = tidak dinilai (tanpa patokan path)."""
    if not fragments:
        return (0, 0, 0)
    frags = [f.lower() for f in fragments]
    best = 0
    for k, h in enumerate(hits, start=1):
        p = h["path"].lower()
        if any(f in p for f in frags):
            best = max(best, 1 if k == 1 else (3 if k <= 3 else 5))
    return (best >= 1, best >= 3, best >= 5) if best else (0, 0, 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(HERE / "golden.json"))
    ap.add_argument("--topn", type=int, default=5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    golden = json.loads(Path(args.golden).read_text())
    conn = store.connect()
    emb_model = server._embeddings()
    results = []
    scored, h1 = h3 = h5 = 0
    t0 = time.monotonic()
    for it in golden:
        lib, q = it["library_name"], it["query"]
        frags = it.get("expected_path_fragments") or []
        lib_row = store.get_lib(conn, lib)
        if not lib_row:
            results.append({"library_name": lib, "query": q, "error": "no_lib"})
            print(f"NO_LIB  {lib:14s} {q[:40]}", flush=True)
            continue
        has_vec = conn.execute(
            "SELECT 1 FROM chunks_vec WHERE lib_id=? LIMIT 1", (lib,)).fetchone() is not None
        qvec = None
        if has_vec:
            qvec = [float(x) for x in list(emb_model.embed([q]))[0]]
        hits = store.search(conn, lib, q, k=10, query_vec=qvec)
        hits = server._rerank(q, hits)
        hits = store.trim_to_tokens(hits)[:args.topn]
        a, b, c = _hit(hits, frags)
        if frags:
            scored += 1
            h1, h3, h5 = h1 + a, h3 + b, h5 + c
        results.append({"library_name": lib, "query": q, "frags": frags,
                        "hit@1": bool(a), "hit@3": bool(b), "hit@5": bool(c),
                        "paths": [h["path"][:90] for h in hits]})
        print(f"{'OK' if c else '--'} {lib:14s} hit@5={'Y' if c else 'N'} "
              f"{q[:45]:45s} -> {hits[0]['path'][:60] if hits else ''}", flush=True)

    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "libs": len(golden), "scored": scored,
        "hit@1": round(h1 / scored, 3) if scored else 0,
        "hit@3": round(h3 / scored, 3) if scored else 0,
        "hit@5": round(h5 / scored, 3) if scored else 0,
        "seconds": round(time.monotonic() - t0, 1),
        "per_lib": results,
    }
    out_path = Path(args.out) if args.out else HERE / "rounds" / (out["ts"].replace(":", "-") + ".json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1))
    print(f"\neval: {scored} dinilai dari {len(golden)} -> hit@1 {out['hit@1']} / "
          f"hit@3 {out['hit@3']} / hit@5 {out['hit@5']} ({out['seconds']}s) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
