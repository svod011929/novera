#!/usr/bin/env bash
# Non-destructive backup rehearsal on a live NOVERA host.
# Creates a real backup, verifies SHA-256, and checks SQLite integrity
# without touching the live database file used by the running container.
set -euo pipefail

RELEASE_ROOT="${NOVERA_RELEASE_ROOT:-/opt/gfort}"
STATE_DIR="$RELEASE_ROOT/state"
CURRENT="$(readlink -f "$RELEASE_ROOT/current")"
[[ -d "$CURRENT" ]] || { echo "current release missing" >&2; exit 1; }

cd "$CURRENT"
backup_raw="$(bash deploy/backup.sh | tee /dev/stderr)"
backup_path="$(printf '%s\n' "$backup_raw" | awk 'NF{line=$0} END{print line}')"
if [[ "$backup_path" == /app/backups/* ]]; then
  backup_path="$STATE_DIR/backups/${backup_path##*/}"
fi
if [[ ! -f "$backup_path" && -f "$CURRENT/backups/${backup_path##*/}" ]]; then
  backup_path="$CURRENT/backups/${backup_path##*/}"
fi
if [[ ! -f "$backup_path" && -f "$STATE_DIR/backups/${backup_path##*/}" ]]; then
  backup_path="$STATE_DIR/backups/${backup_path##*/}"
fi
[[ -f "$backup_path" ]] || { echo "backup file missing: $backup_path" >&2; exit 1; }
manifest="${backup_path}.sha256"
[[ -f "$manifest" ]] || { echo "backup manifest missing: $manifest" >&2; exit 1; }

(
  cd "$(dirname -- "$backup_path")"
  sha256sum -c "$(basename -- "$manifest")"
)

python3 - "$backup_path" <<'PY'
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1])
con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
try:
    row = con.execute("PRAGMA integrity_check").fetchone()
finally:
    con.close()
if not row or row[0] != "ok":
    raise SystemExit(f"integrity_check failed: {row}")
print("sqlite integrity_check=ok")
PY

runtime_sidecar="${backup_path%.sqlite3}.runtime-config.enc"
if [[ -f "$runtime_sidecar" ]]; then
  echo "runtime sidecar present: $runtime_sidecar"
else
  echo "runtime sidecar absent (expected before chain activation)"
fi

echo "REHEARSAL_OK $backup_path"
