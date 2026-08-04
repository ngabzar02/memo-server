#!/usr/bin/env python3
"""run_bench.py — benchmark NYATA: memo (lokal, stdio MCP) vs Context7 (remote REST).

Dua sistem diukur pada set query yang sama (queries.json):
  - memo: resolve_library_id -> get_docs via subprocess stdio JSON-RPC (MCPClient)
  - Context7: GET /v2/libs/search -> GET /v2/context (tanpa API key)
Skor: resolve hit, relevance hit@k pada path docs, latency ms, token estimate.
Tidak ada mock/stub: semua angka berasal dari eksekusi live.

Usage:
  python bench/run_bench.py --queries bench/queries.json --out bench/report.md
"""

import argparse
import json
import os
import re
import statistics
import sys
import time

import httpx

from mcp_client import MCPClient

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
SRC = os.path.join(REPO, "src")
PYTHON = sys.executable
C7 = "https://context7.com/api/v2"
C7_HEADERS = {"X-Client-Info": "bench-memo/1.0"}
RESOLVE_TIMEOUT = 30.0
DOCS_TIMEOUT = 40.0


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def token_est(chars: int) -> int:
    return max(1, chars // 4)  # ~4 chars/token (same rule as memo store.MAX_TOKENS)


def hit_pos(paths: list[str], frags: list[str]) -> int | None:
    """1-based position of first result (of 5) whose path contains a fragment; None = miss."""
    if not frags:
        return None
    for i, p in enumerate(paths[:5]):
        pl = p.lower()
        if any(f.lower() in pl for f in frags):
            return i + 1
    return None


def resolve_hit(top_id: str | None, name: str) -> bool:
    return bool(top_id) and norm(name) in norm(top_id)


# --- Context7 (remote REST, tanpa key) -------------------------------------

def c7_resolve(name: str, query: str) -> tuple[str | None, str | None, float]:
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{C7}/libs/search", params={"query": name},
                      headers=C7_HEADERS, timeout=RESOLVE_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        return None, f"error: {e}", (time.monotonic() - t0) * 1000
    ms = (time.monotonic() - t0) * 1000
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}", ms
    try:
        results = r.json().get("results", [])
    except Exception:  # noqa: BLE001
        return None, "invalid JSON response", ms
    return (results[0]["id"] if results else None), None, ms


def c7_docs(lib_id: str, query: str) -> tuple[list[dict], str | None, float]:
    t0 = time.monotonic()
    try:
        r = httpx.get(f"{C7}/context", params={"query": query, "libraryId": lib_id},
                      headers=C7_HEADERS, timeout=DOCS_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        return [], f"error: {e}", (time.monotonic() - t0) * 1000
    ms = (time.monotonic() - t0) * 1000
    if r.status_code != 200:
        return [], f"HTTP {r.status_code} (butuh API key?)", ms
    text = r.text.strip()
    if not text:
        return [], "empty response", ms
    if text.startswith("{"):
        return [], f"JSON not markdown: {text[:80]} (butuh API key?)", ms
    blocks = []
    for block in re.split(r"\n-{10,}\n", text):
        block = block.strip()
        if not block:
            continue
        m = re.search(r"Source: (https?://\S+)", block)
        path = m.group(1) if m else ""
        path = re.sub(r"^https?://[^/]+/", "", path)  # strip scheme+host, keep docs path
        blocks.append({"path": path, "text": block})
    return blocks, None, ms


# --- memo (lokal, stdio MCP) -----------------------------------------------

def make_memo() -> MCPClient:
    return MCPClient(PYTHON, REPO, {"PYTHONPATH": SRC})


def memo_call(client: MCPClient, method: str, args: dict,
              timeout: float) -> tuple[list, str | None, float, str | None]:
    """Call with one respawn on dead/timeout process. Returns (result, error, ms, note)."""
    attempts = 0
    while True:
        attempts += 1
        t0 = time.monotonic()
        try:
            res = client.call(method, args, timeout=timeout)
            return res, None, (time.monotonic() - t0) * 1000, None
        except (TimeoutError, EOFError, BrokenPipeError, OSError) as e:
            ms = (time.monotonic() - t0) * 1000
            if attempts >= 2:
                return None, f"{type(e).__name__} x{attempts}", ms, None
            client.respawn()  # respawn once, then report failure
    # pragma: no cover


def memo_phases(client: MCPClient, name: str, query: str) -> dict:
    """resolve_library_id -> get_docs. Returns raw per-phase data."""
    resolve, rerr, rms, rnote = memo_call(client, "resolve_library_id",
                                          {"library_name": name, "query": query},
                                          RESOLVE_TIMEOUT)
    # Hardening: id kandidat harus str (MCP schema get_docs menolak int;
    # beberapa kali resolve mengembalikan id numerik -> bench crash).
    resolve_id = str(resolve[0]["id"]) if resolve and isinstance(resolve[0], dict) else None
    docs = []
    if resolve_id:
        docs, derr, dms, dnote = memo_call(client, "get_docs",
                                           {"library_id": resolve_id, "query": query},
                                           DOCS_TIMEOUT)
    else:
        derr, dms, dnote = None, None, None
    return {"resolve": resolve, "resolve_id": resolve_id, "resolve_ms": rms,
            "resolve_err": rerr, "resolve_note": rnote,
            "docs": docs, "docs_err": derr, "docs_ms": dms, "docs_note": dnote}


def run_query(client: MCPClient, q: dict, n: int) -> dict:
    name, query, frags = q["library_name"], q["query"], q["expected_path_fragments"]
    row = {"n": n, "name": name, "query": query, "frags": frags}

    m = memo_phases(client, name, query)
    m_paths = [c.get("path") or "" for c in (m["docs"] or [])]
    m_chars = sum(len(c.get("text") or "") for c in (m["docs"] or []))
    row["memo"] = {
        "resolve_id": m["resolve_id"],
        "resolve_hit": resolve_hit(m["resolve_id"], name),
        "resolve_ms": round(m["resolve_ms"], 0),
        "resolve_err": m["resolve_err"],
        "resolve_note": m["resolve_note"],
        "docs_pos": hit_pos(m_paths, frags),
        "docs_paths": m_paths[:5],
        "chunks": len(m["docs"] or []),
        "docs_ms": round(m["docs_ms"], 0) if m["docs_ms"] is not None else None,
        "tok": token_est(m_chars),
        "docs_err": m["docs_err"],
        "docs_note": m["docs_note"],
    }

    c7id, cerr, c7rms = c7_resolve(name, query)
    row["c7"] = {"resolve_id": c7id, "resolve_hit": resolve_hit(c7id, name),
                 "resolve_ms": round(c7rms, 0), "resolve_err": cerr}
    if c7id and not cerr:
        blocks, derr, c7dms = c7_docs(c7id, query)
        b_paths = [b["path"] for b in blocks]
        row["c7"].update({
            "docs_pos": hit_pos(b_paths, frags),
            "blocks": len(blocks),
            "docs_ms": round(c7dms, 0),
            "tok": token_est(sum(len(b["text"]) for b in blocks)),
            "docs_err": derr,
            "docs_paths": b_paths[:5],
        })
    else:
        row["c7"].update({"docs_pos": None, "blocks": None, "docs_ms": None,
                          "tok": None, "docs_err": "skip: resolve failed", "docs_paths": []})
    return row


# --- report ----------------------------------------------------------------

def fmt_hit(pos: int | None) -> str:
    return f"@{pos}" if pos else "miss"


def fmt_num(v, default="n/a"):
    return default if v is None else f"{v:,.0f}"


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def pct(ok, total):
    return f"{100 * ok / total:.0f}%" if total else "n/a"


def render_report(rows: list[dict], meta: dict, wall_s: float) -> str:
    L = []
    a = L.append
    a(f"# Bench memo vs Context7 — {time.strftime('%Y-%m-%d %H:%M')}")
    a("")
    a(f"- Query count: {len(rows)} | wall time: {wall_s:.0f}s")
    a(f"- memo: stdio MCP via subprocess `{PYTHON}` (binary `memo` tidak ada di PATH), "
      f"workdir {REPO}, PYTHONPATH={SRC}; tool `resolve_library_id(library_name, query)` -> `get_docs(library_id, query)`.")
    a("- Context7: REST tanpa API key, `GET /v2/libs/search?query=` -> `GET /v2/context?query=&libraryId=`.")
    a(f"- Timeout: resolve {RESOLVE_TIMEOUT:.0f}s, get_docs {DOCS_TIMEOUT:.0f}s. "
      f"Token = perkiraan chars/4. `expected_path_fragments` bersumber curated "
      f"(pengetahuan umum, independen dari kedua sistem).")
    a("- Resolve hit: top-1 id mengandung nama library (dinormalisasi). "
      "Relevance hit@k: path chunk/blok (posisi ke-1..5) mengandung fragment.")
    a("")
    a("## Resolve")
    a("| # | library | memo top-1 id | memo hit | memo ms | c7 top-1 id | c7 hit | c7 ms |")
    a("|---|---------|---------------|----------|---------|-------------|--------|-------|")
    for r in rows:
        m, c = r["memo"], r["c7"]
        a(f"| {r['n']} | {r['name']} | {m['resolve_id'] or '—'} | "
          f"{'YES' if m['resolve_hit'] else 'NO'}{'(' + (m['resolve_err'] or '') + ')' if m['resolve_err'] else ''} "
          f"| {fmt_num(m['resolve_ms'])} | {c['resolve_id'] or '—'} | "
          f"{'YES' if c['resolve_hit'] else 'NO'}{'(' + (c['resolve_err'] or '') + ')' if c['resolve_err'] else ''} "
          f"| {fmt_num(c['resolve_ms'])} |")
    a("")
    a("## Docs (relevance)")
    a("| # | library | memo hit@k | memo chunks | memo ms | memo tok | c7 hit@k | c7 blocks | c7 ms | c7 tok |")
    a("|---|---------|------------|-------------|---------|-----------|----------|-----------|-------|--------|")
    for r in rows:
        m, c = r["memo"], r["c7"]
        a(f"| {r['n']} | {r['name']} | {fmt_hit(m['docs_pos']) if r['frags'] else 'n/a'} "
          f"| {m['chunks']} | {fmt_num(m['docs_ms'])} | {m['tok']} | "
          f"{fmt_hit(c['docs_pos']) if r['frags'] else 'n/a'} | {fmt_num(c['blocks'])} "
          f"| {fmt_num(c['docs_ms'])} | {fmt_num(c['tok'])} |")
    a("")
    a("## Ringkasan agregat")
    a("")
    frag_rows = [r for r in rows if r["frags"]]
    me, ce = [r["memo"] for r in frag_rows], [r["c7"] for r in frag_rows]
    m_hits = [1 if r["docs_pos"] else 0 for r in me]
    c_hits = [1 if r["docs_pos"] else 0 for r in ce]
    m_ok = sum(1 for r in rows if r["memo"]["resolve_hit"])
    c_ok = sum(1 for r in rows if r["c7"]["resolve_hit"])
    ms = [r["memo"]["resolve_ms"] for r in rows if r["memo"]["resolve_ms"]]
    cm = [r["c7"]["resolve_ms"] for r in rows if r["c7"]["resolve_ms"]]
    md = [r["docs_ms"] for r in me if r["docs_ms"] is not None]
    cd = [r["c7"]["docs_ms"] for r in frag_rows if r["c7"]["docs_ms"] is not None]
    m_tok = sum(r["memo"]["tok"] for r in rows)
    c_tok = sum(r["c7"]["tok"] for r in rows if r["c7"]["tok"])
    a("| metrik | memo | Context7 |")
    a("|--------|------|----------|")
    a(f"| resolve hit | {pct(m_ok, len(rows))} ({m_ok}/{len(rows)}) | {pct(c_ok, len(rows))} ({c_ok}/{len(rows)}) |")
    a(f"| docs hit@5 (query ber-fragment) | {pct(sum(m_hits), len(frag_rows))} ({sum(m_hits)}/{len(frag_rows)}) | "
      f"{pct(sum(c_hits), len(frag_rows))} ({sum(c_hits)}/{len(frag_rows)}) |")
    a(f"| resolve latency mean ms | {fmt_num(mean(ms))} | {fmt_num(mean(cm))} |")
    a(f"| docs latency mean ms | {fmt_num(mean(md))} | {fmt_num(mean(cd))} |")
    a(f"| docs latency median ms | {fmt_num(statistics.median(md)) if md else 'n/a'} | "
      f"{fmt_num(statistics.median(cd)) if cd else 'n/a'} |")
    a(f"| total token output (est) | {m_tok} | {c_tok} |")
    a("")
    a("## Kesimpulan jujur")
    a("")
    cold = [r["name"] for r in rows if r["memo"]["chunks"] == 0 and not r["memo"]["docs_err"]
            and (r["memo"]["docs_ms"] or 0) > 1000]  # ingest cold (>1s), bukan retrieval miss cepat
    hot_miss = [r["name"] for r in rows if r["memo"]["chunks"] == 0 and not r["memo"]["docs_err"]
                and (r["memo"]["docs_ms"] or 0) <= 1000]
    a(f"- Memo resolve: {pct(m_ok, len(rows))} benar; Context7 {pct(c_ok, len(rows))}.")
    a(f"- Relevance (hit@5, fragment diketahui): memo {pct(sum(m_hits), len(frag_rows))} vs Context7 {pct(sum(c_hits), len(frag_rows))}.")
    a(f"- Latensi docs memo (mean {fmt_num(mean(md))} ms) vs Context7 (mean {fmt_num(mean(cd))} ms) — "
      f"network Context7 adalah pembanding yang tidak setara di kondisi lokal.")
    a(f"- Resolve memo lambat (mean {fmt_num(mean(ms))} ms) karena registry.resolve melakukan lookup "
      f"network berurutan (alias->builtin->llmstxt->npm->pypi->github, timeout 10s per sumber, "
      f"registry.py:210-248); Context7 resolve adalah satu HTTP call.")
    a(f"- Cold-cache memo (get_docs pertama >1s, hasil 0 chunk, tanpa error): {len(cold)} library "
      f"({', '.join(cold) if cold else 'tidak ada'}). Pada cold cache, budget ingest internal memo "
      f"20s tidak cukup untuk fetch penuh -> hasil kosong; call berikutnya akan lanjut index.")
    if hot_miss:
        a(f"- 0 hasil pada cache hangat (search cepat, tanpa error): {', '.join(hot_miss)} — "
          f"retrieval miss (BM25 AND semua kata + tidak ada vektor untuk lib FTS-only), bukan cold-cache.")
    a(f"- Query tanpa fragment ({len(rows) - len(frag_rows)}) hanya dihitung resolve + latency, bukan relevance.")
    timeouts = [r["name"] for r in rows if r["memo"]["docs_err"]]
    if timeouts:
        a(f"- Error/timeout memo pada get_docs: {', '.join(timeouts)}.")
    tw = next((r for r in rows if r["name"] == "tailwindcss" and "rails" in (r["c7"]["resolve_id"] or "")), None)
    if tw:
        a(f"- False-positive heuristik resolve: c7 tailwindcss -> `{tw['c7']['resolve_id']}` "
          f"(wrapper Rails, bukan Tailwind CSS asli) — heuristik norm-substring tidak sempurna.")
    c7_errs = {r["c7"]["docs_err"] for r in rows if r["c7"].get("docs_err")}
    if c7_errs:
        a(f"- Context7 docs status: {'; '.join(str(e) for e in c7_errs)}.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bench memo (lokal) vs Context7 (remote).")
    ap.add_argument("--queries", required=True, help="path ke queries.json")
    ap.add_argument("--out", default=os.path.join(ROOT, "report.md"), help="output report.md")
    ap.add_argument("--limit", type=int, default=0, help="batasi jumlah query (debug)")
    args = ap.parse_args()

    with open(args.queries) as f:
        queries = json.load(f)
    if args.limit:
        queries = queries[:args.limit]

    client = make_memo()
    t_start = time.monotonic()
    rows = []
    for n, q in enumerate(queries, 1):
        print(f"[{n:02d}/{len(queries)}] {q['library_name']:<12s} {q['query'][:40]}", flush=True)
        row = run_query(client, q, n)
        m, c = row["memo"], row["c7"]
        print(f"    memo resolve={m['resolve_id']} docs=@{m['docs_pos'] if row['frags'] else 'n/a'}"
              f"({m['chunks']} chunks, {fmt_num(m['docs_ms'])}ms) | "
              f"c7 resolve={c['resolve_id']} docs=@{c['docs_pos'] if row['frags'] else 'n/a'}"
              f"({fmt_num(c['blocks'])} blocks, {fmt_num(c['docs_ms'])}ms)", flush=True)
        rows.append(row)
    wall_s = time.monotonic() - t_start
    client.close()

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(render_report(rows, {"queries": args.queries}, wall_s))
    print(f"\nreport -> {out_path} (exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
