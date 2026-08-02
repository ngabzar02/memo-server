#!/usr/bin/env bash
# fetch-cache.sh — unduh docs.db pre-built (dibuat di GitHub Actions runner).
# Ponsel/perangkat lokal tidak perlu fetch+embed sama sekali.
set -euo pipefail

URL="https://github.com/ngabzar02/memo-server/releases/latest/download/docs.db"
DEST="${MEMO_DB:-$HOME/.local/share/memo/docs.db}"
TMP="$DEST.download"

mkdir -p "$(dirname "$DEST")"
echo "Mengunduh $URL ..."
curl -fL --retry 3 -o "$TMP" "$URL"
[ -s "$TMP" ] || { echo "GAGAL: file hasil unduhan kosong"; rm -f "$TMP"; exit 1; }

# verifikasi cepat: sqlite sehat + ada isi
if command -v python3 >/dev/null; then
  python3 -c "
import sqlite3, sys
c = sqlite3.connect('$TMP')
n = c.execute('SELECT COUNT(*) FROM libs').fetchone()[0]
m = c.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
assert n > 0 and m > 0, 'DB tidak valid'
print(f'OK: {n} library, {m} chunk')
" || { echo "GAGAL: docs.db rusak"; rm -f "$TMP"; exit 1; }
fi

if [ -f "$DEST" ]; then cp "$DEST" "$DEST.bak"; echo "Backup lama -> $DEST.bak"; fi
mv "$TMP" "$DEST"
echo "Selesai: $DEST ($(du -h "$DEST" | cut -f1))"
