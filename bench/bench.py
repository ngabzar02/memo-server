#!/usr/bin/env python3
"""bench.py — 20 query vs Context7 asli (REST, tanpa key) vs memo lokal.

Skor per query: hit jika hasil non-kosong DAN mengandung >=1 keyword query.
Keluaran: JSON per query di _sys/bench/results/ + ringkasan markdown.
"""
import json
import os
import re
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.abspath(__file__))
QUERIES = os.path.join(ROOT, "queries.md")
OUT = os.path.join(ROOT, "results")
C7 = "https://context7.com/api/v2"
HDRS = {"X-Client-Info": "bench-cc/1.0"}


def parse_queries():
    rows, cur = [], None
    for line in open(QUERIES):
        m = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
        if m:
            cur = {"n": int(m.group(1)), "query": m.group(2), "lib": m.group(3)}
            rows.append(cur)
    return rows


def c7_context(query, lib_id):
    r = httpx.get(f"{C7}/context", params={"query": query, "libraryId": lib_id},
                  headers=HDRS, timeout=30)
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"
    text = r.text
    if not text or text.startswith("{"):
        return [], "no text (JSON?)"
    chunks = []
    for block in re.split(r"\n-{10,}\n", text):
        block = block.strip()
        if not block:
            continue
        title = ""
        m = re.match(r"#+ (.*)", block)
        if m:
            title = m.group(1)[:80]
        chunks.append({"title": title, "text": block})
    return chunks, None


def c7_resolve(lib):
    r = httpx.get(f"{C7}/libs/search", params={"libraryName": lib, "query": ""},
                  headers=HDRS, timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    res = r.json().get("results", [])
    return res[0]["id"] if res else None, None


def dm_docs(lib, query):
    from memo.server import get_docs
    return get_docs(lib, query)


def hit(chunks, query):
    kws = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 3]
    for c in chunks:
        txt = c["text"].lower()
        if any(k in txt for k in kws):
            return True
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = parse_queries()
    sleep_s = float(os.environ.get("BENCH_SLEEP", "0"))
    summary = []
    for r in rows:
        if os.path.exists(f"{OUT}/{r['n']:02d}.json"):
            continue  # resume: hasil sudah ada (misal dari run yang terpotong)
        q, lib = r["query"], r["lib"]
        entry = {"n": r["n"], "query": q, "lib": lib}

        c7id, err = c7_resolve(lib)
        if err or not c7id:
            entry["c7"] = {"resolve": None, "error": err or "no result"}
        else:
            chunks, err = c7_context(q, c7id)
            entry["c7"] = {"resolve": c7id, "chunks": len(chunks),
                           "hit": hit(chunks, q), "error": err,
                           "sample": chunks[:2]}

        try:
            chunks = dm_docs(lib, q)
            entry["dm"] = {"chunks": len(chunks), "hit": hit(chunks, q),
                           "sample": chunks[:2]}
        except Exception as e:  # noqa: BLE001
            entry["dm"] = {"error": str(e)[:200]}

        with open(f"{OUT}/{r['n']:02d}.json", "w") as f:
            json.dump(entry, f, indent=1)
        ok_c7 = entry["c7"].get("hit", False)
        ok_dm = entry["dm"].get("hit", False)
        mark = "OK" if ok_dm else ("?" if entry["dm"].get("chunks") else "EMPTY")
        summary.append((r["n"], lib, ok_c7, ok_dm, mark, entry["c7"].get("chunks"), entry["dm"].get("chunks")))
        print(f"[{r['n']:02d}] {lib:14s} c7:{entry['c7'].get('chunks', '-')} "
              f"dm:{entry['dm'].get('chunks', '-')} {mark}", flush=True)
        if sleep_s:
            time.sleep(sleep_s)

    c7_ok = sum(1 for s in summary if s[2])
    dm_ok = sum(1 for s in summary if s[3])
    print(f"\nc7 hits: {c7_ok}/{len(summary)}  dm hits: {dm_ok}/{len(summary)}")


if __name__ == "__main__":
    main()
