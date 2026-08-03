#!/usr/bin/env python3
"""ci-poll — kolektor mekanis full-auto (jalan via cron, tanpa LLM).

Alur tiap jalan:
1. Cek workflow test/bench/build-cache yang sudah selesai & belum tercatat.
2. Download artifact hasil → simpan ke /tmp/opencode/ci/<batch>.
3. Update bench/state.md + commit+push (state live tidak boleh ketinggalan).
4. Kirim ringkasan ke Telegram via send_telegram.py (bila ada perubahan).
5. Trigger bench-heavy bila ada perubahan src/ (gate G1) & tidak ada yang jalan.

Guard: file lock (/tmp/ci-poll.lock) — cron 5 menit tidak boleh tumpuk.
Log: /tmp/ci-poll.log (append).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = "/root/.local/share/memo"
OUT = "/tmp/opencode/ci"
LOCK = "/tmp/ci-poll.lock"
LOG = "/tmp/ci-poll.log"
SEND = "/root/.opencode/skills/shared_skills/telegram-bridge-send/scripts/send_telegram.py"
LOGGED = os.path.join(OUT, "processed.json")

WF = {
    "test.yml": ("test", "pytest-logs"),
    "bench-heavy.yml": ("bench", "bench-heavy-results"),
    "bench.yml": ("bench", "bench-results"),
    "cache.yml": ("cache", None),
}


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)


def gh(*args: str) -> str:
    tok = ""
    try:
        cred = open(os.path.expanduser("~/.git-credentials")).read()
        m = re.search(r"https://[^:]+:([^@]+)@github.com", cred)
        if m:
            tok = m.group(1)
    except OSError:
        pass
    env = dict(os.environ, GH_TOKEN=tok)
    return subprocess.run(["gh", *args], capture_output=True, text=True, env=env,
                          timeout=120).stdout


def load_logged() -> list[str]:
    try:
        return json.load(open(LOGGED))
    except (OSError, json.JSONDecodeError):
        return []


def save_logged(items: list[str]) -> None:
    os.makedirs(os.path.dirname(LOGGED), exist_ok=True)
    json.dump(sorted(items), open(LOGGED, "w"))


def send_tg(text: str) -> None:
    if not os.path.exists(SEND):
        log("telegram: script send_telegram.py tidak ada — skip")
        return
    r = subprocess.run([sys.executable, SEND, "--message", text[:4000]],
                       capture_output=True, text=True, timeout=60)
    log(f"telegram: {'OK' if r.returncode == 0 else 'FAIL ' + r.stderr[:100]}")


def update_state(batch: str, note: str) -> None:
    """Update bench/state.md baris state (batch + catatan workflow)."""
    sp = os.path.join(REPO, "bench/state.md")
    if os.path.exists(sp):
        txt = open(sp).read()
        txt = re.sub(r"- state: `[^`]+`", f"- state: `{batch}` (auto-update {note})", txt, count=1)
        open(sp, "w").write(txt)


def git_commit_push(subject: str) -> None:
    """Commit+push file yang dikelola ci-poll. Gagal -> log, tidak crash."""
    files = ["bench/state.md"]
    try:
        dirty = subprocess.run(
            ["git", "-C", REPO, "status", "--porcelain", "--", *files],
            capture_output=True, text=True, timeout=30).stdout
        if not dirty:
            log("commit: tidak ada perubahan state — skip")
            return
        subprocess.run(["git", "-C", REPO, "add", *files], check=True, timeout=30)
        subprocess.run(["git", "-C", REPO, "commit", "-m", subject],
                       check=True, capture_output=True, timeout=30)
        subprocess.run(["git", "-C", REPO, "push", "origin", "main"],
                       check=True, capture_output=True, timeout=120)
        log("commit+push OK")
    except Exception as e:  # noqa: BLE001
        log(f"commit+push GAGAL: {e}")


def main() -> None:
    if os.path.exists(LOCK):
        age = time.time() - os.path.getmtime(LOCK)
        if age < 600:
            log("lock aktif — skip (cron sebelumnya masih jalan)")
            return
        log(f"lock basi ({age:.0f}s) — lanjut")
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))

    try:
        processed = load_logged()
        runs = json.loads(gh("run", "list", "--limit", "20", "--json",
                             "databaseId,status,conclusion,workflowName,displayTitle,headSha"))
        new = [r for r in runs
               if r["status"] == "completed"
               and r["conclusion"] in ("success", "failure", "cancelled")
               and str(r["databaseId"]) not in processed]
        if not new:
            log("tidak ada run baru yang selesai")
            return
        os.makedirs(OUT, exist_ok=True)
        msgs = []
        for r in sorted(new, key=lambda x: x["databaseId"]):
            rid = str(r["databaseId"])
            wf = r["workflowName"]
            con = r["conclusion"]
            head = (r.get("displayTitle") or "")[:50]
            note = f"{wf} {rid} {con} ({head})"
            log(f"RUN SELESAI: {note}")
            try:
                shutil.rmtree(f"{OUT}/{rid}", ignore_errors=True)
                gh("run", "download", rid, "-D", f"{OUT}/{rid}")
                log(f"artifact → {OUT}/{rid}")
            except Exception as e:  # noqa: BLE001
                log(f"download gagal: {e}")
            processed.append(rid)
            msgs.append(note)
        save_logged(processed)
        if msgs:
            send_tg("CI update:\n" + "\n".join(msgs))
        update_state("COLLECTED", ",".join(sorted({r["workflowName"] for r in new})))
        git_commit_push(f"docs(bench): auto-update state dari ci-poll ({len(new)} run)")
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == "__main__":
    main()
