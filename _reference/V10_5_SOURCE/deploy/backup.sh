#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
retention_days=${BACKUP_RETENTION_DAYS:-14}

case "$retention_days" in
    ''|*[!0-9]*)
        echo "BACKUP_RETENTION_DAYS must be a non-negative integer" >&2
        exit 2
        ;;
esac

backup_name="delta-$(date -u +%Y%m%d-%H%M%S).sqlite3"
cd "$project_dir"

docker compose -f compose.vps.yml exec -T delta \
    python -m delta_backend.backup --output "/app/backups/$backup_name"
chmod 640 "$project_dir/backups/$backup_name"
sha256sum "$project_dir/backups/$backup_name" > "$project_dir/backups/$backup_name.sha256"
chmod 640 "$project_dir/backups/$backup_name.sha256"

find "$project_dir/backups" -maxdepth 1 -type f \
    -name 'delta-*.sqlite3' -mtime "+$retention_days" -delete
find "$project_dir/backups" -maxdepth 1 -type f \
    -name 'delta-*.sqlite3.sha256' -mtime "+$retention_days" -delete

echo "$project_dir/backups/$backup_name"
