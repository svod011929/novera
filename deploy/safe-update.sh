#!/usr/bin/env bash
# Safe in-place update for an already-bootstrapped NOVERA/GFORT VPS.
# Never rewrites owner secrets or .env; never runs the bootstrap installer.
set -euo pipefail

RELEASE_ROOT="${NOVERA_RELEASE_ROOT:-/opt/gfort}"
RELEASES_DIR="$RELEASE_ROOT/releases"
STATE_DIR="$RELEASE_ROOT/state"
CURRENT_LINK="$RELEASE_ROOT/current"
COMPAT_LINK="/opt/delta"
COMPOSE_FILE="compose.vps.yml"
MODE="full"
SOURCE_DIR=""
KEEP_RELEASES="${NOVERA_KEEP_RELEASES:-5}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
RELEASE_ID="novera-update-$STAMP"
CANDIDATE_DIR="$RELEASES_DIR/$RELEASE_ID"
PREVIOUS_DIR=""
PREVIOUS_IMAGE=""
STARTED_DELTA=0
DOMAIN=""
SETUP_STATUS_BEFORE=""

log(){ printf '\033[1;36m[UPDATE]\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

usage(){
    cat <<EOF
NOVERA safe update

Usage:
  sudo bash deploy/safe-update.sh --source /path/to/payload [--mode frontend|full]

Modes:
  frontend  Copy frontend only, recreate Caddy with new bind mount (no API blink)
  full      Build new app image and recreate delta (short API blink) + Caddy if needed
EOF
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --source) [[ "$#" -ge 2 ]] || fail "--source requires a value"; SOURCE_DIR="$2"; shift 2 ;;
        --mode) [[ "$#" -ge 2 ]] || fail "--mode requires a value"; MODE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done

[[ "$(id -u)" -eq 0 ]] || fail "Run with sudo/root"
[[ -n "$SOURCE_DIR" && -d "$SOURCE_DIR" ]] || fail "--source must be an extracted release directory"
[[ -f "$SOURCE_DIR/compose.vps.yml" ]] || fail "compose.vps.yml missing in source"
[[ -d "$SOURCE_DIR/frontend" ]] || fail "frontend/ missing in source"
case "$MODE" in frontend|full) ;; *) fail "--mode must be frontend or full" ;; esac
[[ -L "$CURRENT_LINK" ]] || fail "$CURRENT_LINK is not a symlink; refuse to update a non-staged install"
PREVIOUS_DIR="$(readlink -f "$CURRENT_LINK")"
[[ -d "$PREVIOUS_DIR" ]] || fail "Current release path is missing: $PREVIOUS_DIR"
[[ -f "$PREVIOUS_DIR/.env" ]] || fail "Current release has no .env"
[[ -d "$STATE_DIR/data" && -d "$STATE_DIR/secrets" ]] || fail "Persistent state is incomplete under $STATE_DIR"

DOMAIN="$(awk -F= '$1=="API_DOMAIN"{print substr($0,index($0,"=")+1);exit}' "$PREVIOUS_DIR/.env")"
[[ -n "$DOMAIN" ]] || fail "API_DOMAIN missing in current .env"
PREVIOUS_IMAGE="$(awk -F= '$1=="GFORT_APP_IMAGE"{print substr($0,index($0,"=")+1);exit}' "$PREVIOUS_DIR/.env")"
[[ -n "$PREVIOUS_IMAGE" ]] || PREVIOUS_IMAGE="novera-app:current"

read_ready_status(){
    curl -fsS --connect-timeout 4 --max-time 12 "https://$DOMAIN/ready" 2>/dev/null \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status",""), (d.get("setup") or {}).get("status",""), (d.get("setup") or {}).get("financial_ready",""))' \
        || true
}

wait_ready(){
    local expect_setup="$1" attempt ready_line status setup financial
    for attempt in $(seq 1 90); do
        ready_line="$(read_ready_status)"
        status="$(printf '%s' "$ready_line" | awk '{print $1}')"
        setup="$(printf '%s' "$ready_line" | awk '{print $2}')"
        financial="$(printf '%s' "$ready_line" | awk '{print $3}')"
        if [[ "$status" == "ready" && "$setup" == "$expect_setup" ]]; then
            ok "Public /ready is ready (setup=$setup financial_ready=$financial)"
            return 0
        fi
        sleep 2
    done
    return 1
}

rollback(){
    local rc=$?
    trap - EXIT
    if [[ "$rc" -eq 0 ]]; then
        exit 0
    fi
    warn "Update failed; rolling back to $PREVIOUS_DIR"
    if [[ -n "$PREVIOUS_DIR" && -d "$PREVIOUS_DIR" ]]; then
        ln -sfn "$PREVIOUS_DIR" "$CURRENT_LINK.new-$STAMP"
        mv -Tf "$CURRENT_LINK.new-$STAMP" "$CURRENT_LINK"
        ln -sfn "$CURRENT_LINK" "$COMPAT_LINK"
        (
            cd "$PREVIOUS_DIR"
            if [[ "$STARTED_DELTA" == "1" || "$MODE" == "full" ]]; then
                docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate delta || true
            fi
            docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate caddy || true
        )
        wait_ready "${SETUP_STATUS_BEFORE:-bootstrap}" || warn "Rollback health gate did not confirm /ready"
    fi
    exit "$rc"
}
trap rollback EXIT

log "Recording baseline /ready"
BASELINE="$(read_ready_status)"
[[ "$(printf '%s' "$BASELINE" | awk '{print $1}')" == "ready" ]] \
    || fail "Baseline /ready is not ready; refuse to update an unhealthy host"
SETUP_STATUS_BEFORE="$(printf '%s' "$BASELINE" | awk '{print $2}')"
[[ -n "$SETUP_STATUS_BEFORE" ]] || SETUP_STATUS_BEFORE="bootstrap"
ok "Baseline setup.status=$SETUP_STATUS_BEFORE"

log "Creating pre-update backup"
(
    cd "$PREVIOUS_DIR"
    bash deploy/backup.sh
) || fail "Pre-update backup failed"

log "Staging candidate $RELEASE_ID"
mkdir -p "$RELEASES_DIR" "$CANDIDATE_DIR"
# Copy payload without overwriting live state paths.
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude 'data/' --exclude 'backups/' --exclude 'secrets/' --exclude '.env' \
        --exclude '.git/' --exclude '_cursor_output/' --exclude '__pycache__/' \
        "$SOURCE_DIR"/ "$CANDIDATE_DIR"/
else
    tar -C "$SOURCE_DIR" \
        --exclude=data --exclude=backups --exclude=secrets --exclude=.env \
        --exclude=.git --exclude=_cursor_output --exclude=__pycache__ \
        -cf - . | tar -C "$CANDIDATE_DIR" -xf -
fi
find "$CANDIDATE_DIR" -type d -exec chmod 0755 {} +
find "$CANDIDATE_DIR" -type f -exec chmod 0644 {} +
chmod 0755 "$CANDIDATE_DIR/deploy/"*.sh 2>/dev/null || true

rm -rf "$CANDIDATE_DIR/data" "$CANDIDATE_DIR/backups" "$CANDIDATE_DIR/secrets"
ln -s "$STATE_DIR/data" "$CANDIDATE_DIR/data"
ln -s "$STATE_DIR/backups" "$CANDIDATE_DIR/backups"
ln -s "$STATE_DIR/secrets" "$CANDIDATE_DIR/secrets"
cp -a "$PREVIOUS_DIR/.env" "$CANDIDATE_DIR/.env"
chmod 600 "$CANDIDATE_DIR/.env"

# Point release-local paths at the candidate while keeping image tag stable for frontend-only.
python3 - "$CANDIDATE_DIR/.env" "$CANDIDATE_DIR" "$RELEASE_ID" "$MODE" "$PREVIOUS_IMAGE" <<'PYENV'
from pathlib import Path
import sys
env_path, candidate, release_id, mode, previous_image = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
lines = env_path.read_text(encoding="utf-8").splitlines()
wanted = {
    "GFORT_DATA_DIR": "/opt/gfort/state/data",
    "GFORT_BACKUPS_DIR": "/opt/gfort/state/backups",
    "GFORT_SECRETS_DIR": "/opt/gfort/state/secrets",
    "GFORT_FRONTEND_DIR": str(candidate / "frontend"),
    "GFORT_CADDYFILE": str(candidate / "deploy" / "Caddyfile.vps"),
}
if mode == "full":
    wanted["GFORT_APP_IMAGE"] = f"novera-app:{release_id}"
else:
    wanted["GFORT_APP_IMAGE"] = previous_image
out = []
seen = set()
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    key = line.split("=", 1)[0]
    if key in wanted:
        out.append(f"{key}={wanted[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in wanted.items():
    if key not in seen:
        out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PYENV

cd "$CANDIDATE_DIR"
docker compose -f "$COMPOSE_FILE" config --quiet || fail "compose config invalid for candidate"

if [[ "$MODE" == "full" ]]; then
    log "Building application image"
    docker compose -f "$COMPOSE_FILE" build --pull delta
    docker run --rm --entrypoint python "novera-app:$RELEASE_ID" -m compileall -q /app/delta_backend /app/main.py \
        || fail "Image compileall failed"
fi

log "Promoting candidate symlink"
ln -sfn "$CANDIDATE_DIR" "$CURRENT_LINK.new-$STAMP"
mv -Tf "$CURRENT_LINK.new-$STAMP" "$CURRENT_LINK"
ln -sfn "$CURRENT_LINK" "$COMPAT_LINK"

cd "$CANDIDATE_DIR"
if [[ "$MODE" == "full" ]]; then
    log "Recreating delta (short API blink expected)"
    STARTED_DELTA=1
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate delta
    healthy=0
    for _ in $(seq 1 90); do
        container="$(docker compose -f "$COMPOSE_FILE" ps -q delta 2>/dev/null || true)"
        if [[ -n "$container" ]]; then
            state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
            if [[ "$state" == "healthy" || "$state" == "running" ]]; then
                # Prefer healthy; accept running only after /ready gate below.
                if [[ "$state" == "healthy" ]]; then healthy=1; break; fi
            fi
        fi
        sleep 2
    done
    [[ "$healthy" == "1" ]] || {
        docker compose -f "$COMPOSE_FILE" logs --tail=80 --no-color delta >&2 || true
        fail "delta did not become healthy"
    }
fi

log "Recreating Caddy with candidate frontend mount"
docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate caddy

wait_ready "$SETUP_STATUS_BEFORE" || {
    docker compose -f "$COMPOSE_FILE" logs --tail=80 --no-color caddy delta >&2 || true
    fail "Post-update /ready gate failed"
}

# Soft prune old update releases (keep newest KEEP_RELEASES + previous).
python3 - "$RELEASES_DIR" "$KEEP_RELEASES" "$CANDIDATE_DIR" "$PREVIOUS_DIR" <<'PYPRUNE'
from pathlib import Path
import sys
root = Path(sys.argv[1])
keep = max(2, int(sys.argv[2]))
protect = {Path(sys.argv[3]).resolve(), Path(sys.argv[4]).resolve()}
releases = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
for path in releases[keep:]:
    if path.resolve() in protect:
        continue
    if not path.name.startswith("novera-update-") and not path.name.startswith("novera-bootstrap-"):
        continue
    # Keep bootstrap history; prune only older updates beyond keep window.
    if path.name.startswith("novera-update-"):
        import shutil
        shutil.rmtree(path, ignore_errors=True)
PYPRUNE

ok "Update promoted: $CANDIDATE_DIR (mode=$MODE)"
trap - EXIT
exit 0
