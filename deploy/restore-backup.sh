#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$project_dir/compose.vps.yml"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run restore with sudo" >&2
    exit 1
fi
if [ "${NOVERA_CONFIRM_RESTORE:-}" != "RESTORE" ]; then
    echo "Set NOVERA_CONFIRM_RESTORE=RESTORE for this explicit recovery action" >&2
    exit 2
fi
if [ "$#" -ne 1 ]; then
    echo "Usage: sudo env NOVERA_CONFIRM_RESTORE=RESTORE sh deploy/restore-backup.sh /path/delta-*.sqlite3" >&2
    exit 2
fi

backup=$1
case "$backup" in
    /*) ;;
    *) backup=$(CDPATH= cd -- "$(dirname -- "$backup")" && pwd)/$(basename "$backup") ;;
esac
manifest="$backup.sha256"
runtime_backup="${backup%.sqlite3}.runtime-config.enc"
database="$project_dir/data/delta.sqlite3"
runtime_dir="$project_dir/data/runtime_secrets"
runtime_active="$runtime_dir/active.enc"

[ -f "$backup" ] || { echo "Database backup does not exist" >&2; exit 1; }
[ -f "$manifest" ] || { echo "Backup manifest does not exist" >&2; exit 1; }
(
    cd "$(dirname "$backup")"
    sha256sum -c "$(basename "$manifest")"
)

if [ -f "$runtime_active" ] && [ ! -f "$runtime_backup" ]; then
    echo "Refusing to restore an active chain database without its encrypted runtime generation" >&2
    exit 1
fi

stamp=$(date -u +%Y%m%d-%H%M%S)
pre_database="/root/novera-pre-restore-$stamp.sqlite3"
pre_runtime="/root/novera-pre-restore-$stamp.runtime-config.enc"
cutover_started=0
success=0

rollback_restore(){
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$cutover_started" -eq 1 ]; then
        echo "Restore failed; returning to the pre-restore state" >&2
        docker compose -f "$compose_file" down --remove-orphans >/dev/null 2>&1 || true
        if [ -f "$pre_database" ]; then
            cp "$pre_database" "$database"
            chown 10001:10001 "$database"
            chmod 640 "$database"
        fi
        if [ -f "$pre_runtime" ]; then
            mkdir -p "$runtime_dir"
            cp "$pre_runtime" "$runtime_active"
            chown 10001:10001 "$runtime_active"
            chmod 600 "$runtime_active"
        fi
        (cd "$project_dir" && docker compose -f "$compose_file" up -d --remove-orphans) >/dev/null 2>&1 || true
    fi
    exit "$rc"
}
trap rollback_restore EXIT

python3 - "$database" "$pre_database" <<'PYBACKUP'
import sqlite3
import sys
from pathlib import Path

source, target = map(Path, sys.argv[1:])
if not source.is_file():
    raise SystemExit("Current production database is missing")
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
    row = dst.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        raise SystemExit("Pre-restore backup integrity check failed")
PYBACKUP
chmod 600 "$pre_database"
if [ -f "$runtime_active" ]; then
    cp "$runtime_active" "$pre_runtime"
    chmod 600 "$pre_runtime"
fi

cutover_started=1
cd "$project_dir"
docker compose -f "$compose_file" down --remove-orphans

python3 - "$backup" "$database" <<'PYRESTORE'
import os
import sqlite3
import sys
import uuid
from pathlib import Path

source, target = map(Path, sys.argv[1:])
temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.restore")
temporary.unlink(missing_ok=True)
try:
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(temporary) as dst:
        src.backup(dst)
        row = dst.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise SystemExit("Restored database integrity check failed")
    os.replace(temporary, target)
finally:
    temporary.unlink(missing_ok=True)
PYRESTORE
chown 10001:10001 "$database"
chmod 640 "$database"

if [ -f "$runtime_backup" ]; then
    mkdir -p "$runtime_dir"
    runtime_temp="$runtime_dir/.active.enc.$stamp.restore"
    cp "$runtime_backup" "$runtime_temp"
    chown 10001:10001 "$runtime_temp"
    chmod 600 "$runtime_temp"
    mv -f "$runtime_temp" "$runtime_active"
fi

docker compose -f "$compose_file" up -d --remove-orphans
healthy=0
for _attempt in $(seq 1 60)
do
    container=$(docker compose -f "$compose_file" ps -q delta 2>/dev/null || true)
    if [ -n "$container" ]; then
        state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)
        if [ "$state" = "healthy" ]; then
            healthy=1
            break
        fi
    fi
    sleep 2
done
[ "$healthy" -eq 1 ] || { echo "Restored backend did not become healthy" >&2; exit 1; }

domain=$(awk -F= '$1 == "API_DOMAIN" {print substr($0, index($0, "=") + 1); exit}' "$project_dir/.env")
curl -fsS --connect-timeout 4 --max-time 15 "https://$domain/health" >/dev/null
ready=$(curl -fsS --connect-timeout 4 --max-time 15 "https://$domain/ready")
printf '%s' "$ready" | jq -e \
    '.status == "ready" and .database == true and .setup.status != "degraded"' >/dev/null

success=1
cutover_started=0
echo "Verified restore completed; pre-restore recovery files remain under /root with stamp $stamp"
