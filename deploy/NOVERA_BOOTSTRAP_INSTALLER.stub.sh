#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="NOVERA"
RELEASE_VERSION="__RELEASE_VERSION__"
PAYLOAD_MARKER="__NOVERA_BOOTSTRAP_PAYLOAD__"
PAYLOAD_TAR_SHA256="__PAYLOAD_TAR_SHA256__"
DEFAULT_DOMAIN="bnbb.tech"
DEFAULT_IPV4="170.168.91.129"
DEFAULT_OWNER_ID="8054710484"
RELEASE_ROOT="${NOVERA_RELEASE_ROOT:-/opt/gfort}"
RELEASES_DIR="$RELEASE_ROOT/releases"
STATE_DIR="$RELEASE_ROOT/state"
CURRENT_LINK="$RELEASE_ROOT/current"
COMPAT_LINK="/opt/delta"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
RELEASE_ID="novera-bootstrap-$STAMP"
CANDIDATE_DIR="$RELEASES_DIR/$RELEASE_ID"
COMPOSE_FILE="compose.vps.yml"
DOMAIN="$DEFAULT_DOMAIN"
EXPECTED_IPV4="$DEFAULT_IPV4"
OWNER_ID="$DEFAULT_OWNER_ID"
SELF_PATH=""
STARTED=0

if [[ -f "${BASH_SOURCE[0]:-}" ]]; then
    SELF_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
fi

log(){ printf '\033[1;36m[NOVERA]\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail(){ printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

usage(){
    cat <<EOF
NOVERA one-file bootstrap installer

Usage:
  sudo bash $(basename "$0")
  sudo bash $(basename "$0") --domain bnbb.tech --ip 170.168.91.129 --owner-id 8054710484

The installer prompts for a NEW Telegram bot token without echoing it.
RPC, WSS and the payout seed are configured later by the immutable Owner
inside the NOVERA Mini App. Financial operations stay locked until activation.
EOF
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --domain) [[ "$#" -ge 2 ]] || fail "--domain requires a value"; DOMAIN="$2"; shift 2 ;;
        --ip) [[ "$#" -ge 2 ]] || fail "--ip requires a value"; EXPECTED_IPV4="$2"; shift 2 ;;
        --owner-id) [[ "$#" -ge 2 ]] || fail "--owner-id requires a value"; OWNER_ID="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done

cleanup(){
    local rc=$?
    trap - EXIT
    unset BOT_TOKEN || true
    if [[ "$rc" -ne 0 && "$STARTED" == "1" && -f "$CANDIDATE_DIR/$COMPOSE_FILE" ]]; then
        warn "Bootstrap failed; stopping the rejected release"
        (cd "$CANDIDATE_DIR" && docker compose -f "$COMPOSE_FILE" down --remove-orphans) >/dev/null 2>&1 || true
    fi
    if [[ "$rc" -ne 0 ]]; then
        if [[ -L "$COMPAT_LINK" && "$(readlink -f "$COMPAT_LINK" 2>/dev/null || true)" == "$CANDIDATE_DIR" ]]; then
            rm -f "$COMPAT_LINK"
        fi
        if [[ -L "$CURRENT_LINK" && "$(readlink -f "$CURRENT_LINK" 2>/dev/null || true)" == "$CANDIDATE_DIR" ]]; then
            rm -f "$CURRENT_LINK"
        fi
        warn "No previous production was replaced. Diagnostic state is retained under $RELEASE_ROOT."
    fi
    exit "$rc"
}
trap cleanup EXIT

require_fresh_host(){
    [[ "$(id -u)" -eq 0 ]] || fail "Run this installer with sudo"
    [[ -n "$SELF_PATH" && -f "$SELF_PATH" ]] || fail "Run the installer from a regular file"
    [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || fail "Domain contains invalid characters"
    [[ "$EXPECTED_IPV4" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || fail "Invalid IPv4 address"
    [[ "$OWNER_ID" =~ ^[0-9]{5,20}$ ]] || fail "Owner ID must be a numeric Telegram ID"
    if [[ -e "$COMPAT_LINK" || -e "$CURRENT_LINK" || -f "$STATE_DIR/data/delta.sqlite3" ]]; then
        fail "Existing NOVERA/GFORT state detected. Fresh bootstrap refuses to overwrite it."
    fi
    if [[ -d "$RELEASE_ROOT" ]] && find "$RELEASE_ROOT" -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
        fail "$RELEASE_ROOT is not empty. Recover or archive it before a fresh install."
    fi
}

check_platform(){
    [[ -r /etc/os-release ]] || fail "Ubuntu or Debian is required"
    # shellcheck disable=SC1091
    source /etc/os-release
    case "${ID:-}" in
        ubuntu|debian) ;;
        *) fail "Unsupported Linux distribution: ${ID:-unknown}" ;;
    esac
    command -v apt-get >/dev/null 2>&1 || fail "apt-get is required"
}

install_base(){
    log "Installing base packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y ca-certificates curl jq tar gzip coreutils findutils iproute2 python3
    if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
        apt-get install -y docker.io docker-compose-v2 2>/dev/null || true
    fi
    if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
        local docker_installer
        docker_installer="$(mktemp)"
        curl -fsSL https://get.docker.com -o "$docker_installer"
        sh "$docker_installer"
        rm -f "$docker_installer"
    fi
    command -v docker >/dev/null 2>&1 || fail "Docker installation failed"
    docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 installation failed"
    systemctl enable --now docker >/dev/null 2>&1 || true
    docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable"
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
        ufw allow 80/tcp >/dev/null
        ufw allow 443/tcp >/dev/null
        ufw allow 443/udp >/dev/null
    fi
    ok "Base runtime is ready"
}

measure_clock_skew(){
    # Prints the absolute skew (seconds) between this host and api.telegram.org.
    local remote_epoch local_epoch skew
    remote_epoch="$(python3 - <<'PYCLOCK'
import email.utils
import urllib.error
import urllib.request

request = urllib.request.Request(
    "https://api.telegram.org/",
    method="HEAD",
    headers={"User-Agent": "NOVERA-Bootstrap/1.0"},
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        header = response.headers.get("Date")
except urllib.error.HTTPError as exc:
    header = exc.headers.get("Date")
if not header:
    raise SystemExit(1)
print(int(email.utils.parsedate_to_datetime(header).timestamp()))
PYCLOCK
)" || return 1
    local_epoch="$(date +%s)"
    skew=$(( local_epoch - remote_epoch ))
    [[ "$skew" -lt 0 ]] && skew=$(( -skew ))
    printf '%s\n' "$skew"
}

check_clock(){
    # Telegram initData is rejected when auth_date is more than 300 s ahead of
    # the server clock, so a skewed VPS would boot into an app nobody can enter.
    local skew
    skew="$(measure_clock_skew)" || { warn "Clock skew could not be measured against api.telegram.org"; return 0; }
    if [[ "$skew" -gt 120 ]] && command -v chronyc >/dev/null 2>&1; then
        warn "System clock is off by ${skew}s; asking chrony to step it"
        chronyc makestep >/dev/null 2>&1 || true
        sleep 5
        skew="$(measure_clock_skew)" || skew=0
    fi
    if [[ "$skew" -gt 120 ]]; then
        fail "System clock differs from Telegram by ${skew}s. Fix NTP (chrony/timesyncd) and re-run the installer."
    fi
    ok "System clock is within ${skew}s of Telegram"
}

check_network_target(){
    local resolved
    resolved="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u)"
    [[ -n "$resolved" ]] || fail "$DOMAIN does not resolve to IPv4"
    printf '%s\n' "$resolved" | grep -Fxq "$EXPECTED_IPV4" || {
        printf 'Resolved IPv4 addresses:\n%s\n' "$resolved" >&2
        fail "$DOMAIN must resolve to $EXPECTED_IPV4"
    }
    if ss -ltnH 2>/dev/null | awk '{print $4}' | grep -Eq ':(80|443)$'; then
        fail "TCP port 80 or 443 is already occupied; fresh bootstrap will not replace that service"
    fi
    ok "DNS and public ports passed preflight"
}

extract_payload(){
    log "Extracting embedded release payload"
    local work payload
    work="$(mktemp -d)"
    payload="$work/payload.tar.gz"
    awk -v marker="$PAYLOAD_MARKER" 'found {print} $0 == marker {found=1}' "$SELF_PATH" \
        | base64 -d > "$payload"
    printf '%s  %s\n' "$PAYLOAD_TAR_SHA256" "$payload" | sha256sum -c - >/dev/null \
        || fail "Embedded payload SHA-256 mismatch"
    mkdir -p "$CANDIDATE_DIR"
    tar -xzf "$payload" -C "$CANDIDATE_DIR"
    rm -rf "$work"
    # The payload is archived on Windows and carries 0666/0777 modes; the release
    # tree is served by Caddy and built by Docker, so it must not be world-writable.
    find "$CANDIDATE_DIR" -type d -exec chmod 0755 {} +
    find "$CANDIDATE_DIR" -type f -exec chmod 0644 {} +
    [[ -f "$CANDIDATE_DIR/Dockerfile" ]] || fail "Dockerfile is missing from payload"
    [[ -f "$CANDIDATE_DIR/.dockerignore" ]] || fail ".dockerignore is missing from payload"
    [[ -f "$CANDIDATE_DIR/deploy/PAYLOAD_SHA256.txt" ]] || fail "Payload manifest is missing"
    (
        cd "$CANDIDATE_DIR"
        sha256sum -c deploy/PAYLOAD_SHA256.txt >/dev/null
    ) || fail "Critical payload file hash mismatch"
    ok "Embedded payload and critical hashes verified"
}

write_secret(){
    local destination="$1" value="$2"
    umask 077
    printf '%s\n' "$value" > "$destination"
    chown root:10001 "$destination"
    chmod 640 "$destination"
}

configure_bootstrap(){
    log "Creating protected bootstrap state"
    install -d -m 0755 "$RELEASE_ROOT" "$RELEASES_DIR"
    # Ubuntu 26.04 ships uutils coreutils, whose "install -o/-g" rejects numeric
    # IDs that have no passwd entry. Create and own the state tree explicitly.
    mkdir -p "$STATE_DIR/data" "$STATE_DIR/backups" "$STATE_DIR/secrets"
    chown 10001:10001 "$STATE_DIR/data" "$STATE_DIR/backups"
    chmod 0750 "$STATE_DIR/data" "$STATE_DIR/backups"
    chown root:10001 "$STATE_DIR/secrets"
    chmod 0750 "$STATE_DIR/secrets"

    if [[ -n "${NOVERA_BOT_TOKEN_FILE:-}" ]]; then
        [[ -s "$NOVERA_BOT_TOKEN_FILE" ]] || fail "NOVERA_BOT_TOKEN_FILE is missing or empty"
        BOT_TOKEN="$(tr -d '\r\n' < "$NOVERA_BOT_TOKEN_FILE")"
    else
        [[ -t 0 ]] || fail "Interactive token prompt requires a terminal; use NOVERA_BOT_TOKEN_FILE"
        read -r -s -p "New Telegram bot token (input hidden): " BOT_TOKEN
        printf '\n'
    fi
    [[ "$BOT_TOKEN" =~ ^[0-9]{6,12}:[A-Za-z0-9_-]{30,}$ ]] || fail "Telegram bot token format is invalid"
    write_secret "$STATE_DIR/secrets/bot_token.txt" "$BOT_TOKEN"
    unset BOT_TOKEN

    umask 077
    python3 - <<'PYKEY' > "$STATE_DIR/secrets/runtime_config_key.txt"
import base64
import secrets
print(base64.b64encode(secrets.token_bytes(32)).decode("ascii"))
PYKEY
    chown root:10001 "$STATE_DIR/secrets/runtime_config_key.txt"
    chmod 640 "$STATE_DIR/secrets/runtime_config_key.txt"

    local bot_username
    bot_username="$(python3 - "$STATE_DIR/secrets/bot_token.txt" <<'PYBOT'
import json
import sys
import urllib.request
from pathlib import Path

token = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
request = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/getMe",
    headers={"User-Agent": "NOVERA-Bootstrap/1.0"},
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
except Exception as exc:
    raise SystemExit("Telegram bot token could not be verified") from exc
if not payload.get("ok") or not payload.get("result", {}).get("username"):
    raise SystemExit("Telegram bot token was rejected")
print(payload["result"]["username"])
PYBOT
)"
    [[ "$bot_username" =~ ^[A-Za-z0-9_]{5,64}$ ]] || fail "Telegram bot username is invalid"

    rm -rf "$CANDIDATE_DIR/data" "$CANDIDATE_DIR/backups" "$CANDIDATE_DIR/secrets"
    ln -s "$STATE_DIR/data" "$CANDIDATE_DIR/data"
    ln -s "$STATE_DIR/backups" "$CANDIDATE_DIR/backups"
    ln -s "$STATE_DIR/secrets" "$CANDIDATE_DIR/secrets"

    cat > "$CANDIDATE_DIR/.env" <<EOF
API_DOMAIN=$DOMAIN
EXPECTED_VPS_IPV4=$EXPECTED_IPV4
MINIAPP_URL=https://$DOMAIN
MINIAPP_ORIGIN=https://$DOMAIN
TRUSTED_HOSTS=$DOMAIN,localhost,127.0.0.1
SUPPORT_URL=https://t.me/$bot_username
CHAT_URL=https://t.me/$bot_username
BOT_TOKEN_FILE=/run/secrets/bot_token
ADMIN_IDS=$OWNER_ID
OWNER_IDS=$OWNER_ID
BOT_USERNAME=$bot_username
RUN_BOT_LAUNCHER=true
RUN_BROADCAST_WORKER=true
ENVIRONMENT=production
DEMO_MODE=false
CHAIN_ENABLED=false
SIMULATE_PAYOUTS=false
BSC_CHAIN_ID=56
LIVE_MODE_ACK=false
SECURITY_AUDIT_ACK=false
LEGAL_REVIEW_ACK=false
DATABASE_PATH=/app/data/delta.sqlite3
DAILY_PROFIT_BPS=1000
PAYOUT_DAYS=20
DEPOSIT_MIN_USDT=10
DEPOSIT_MAX_USDT=100000
INVOICE_TTL_MINUTES=30
DEPOSITS_ENABLED=false
INVESTMENTS_ENABLED=false
PAYOUTS_ENABLED=false
REFERRAL_ENABLED=false
TOKEN_CONTRACT=0x55d398326f99059fF775485246999027B3197955
TOKEN_SYMBOL=USDT
TOKEN_DECIMALS=18
TREASURY_ADDRESS=
CONFIRMATION_BLOCKS=12
SCAN_START_BLOCK=0
BLOCK_EXPLORER_TX_URL=https://bscscan.com/tx/{tx_hash}
MINIMUM_NATIVE_BALANCE_WEI=0
MINIMUM_TOKEN_BALANCE_USDT=0
RUNTIME_CONFIG_KEY_FILE=/run/secrets/runtime_config_key
SEED_ACCOUNT_PATH=m/44'/60'/0'/0/0
SAFETY_MONITOR_ENABLED=true
SAFETY_CHECK_INTERVAL_SECONDS=30
SAFETY_STARTUP_GRACE_SECONDS=180
SAFETY_MIN_NATIVE_BALANCE_WEI=1000000000000000
SAFETY_PAYOUT_STUCK_SECONDS=900
SAFETY_WSS_STALE_SECONDS=180
SAFETY_HTTP_SCAN_STALE_SECONDS=300
SAFETY_INTEGRITY_INTERVAL_SECONDS=3600
SAFETY_BACKUP_INTERVAL_SECONDS=3600
SAFETY_BACKUP_STALE_SECONDS=10800
SAFETY_BACKUP_RETENTION_COUNT=72
API_HOST=0.0.0.0
API_PORT=8080
FORCE_HTTPS=true
FORWARDED_ALLOW_IPS=*
MAX_REQUEST_BYTES=65536
MUTATION_RATE_LIMIT=12
MUTATION_RATE_WINDOW_SECONDS=60
TELEGRAM_INIT_DATA_TTL_SECONDS=86400
TELEGRAM_SESSION_TTL_SECONDS=604800
LOG_LEVEL=INFO
LOG_JSON=true
GFORT_APP_IMAGE=novera-app:$RELEASE_ID
GFORT_DATA_DIR=$STATE_DIR/data
GFORT_BACKUPS_DIR=$STATE_DIR/backups
GFORT_SECRETS_DIR=$STATE_DIR/secrets
GFORT_FRONTEND_DIR=$CANDIDATE_DIR/frontend
GFORT_CADDYFILE=$CANDIDATE_DIR/deploy/Caddyfile.vps
EOF
    chown root:root "$CANDIDATE_DIR/.env"
    chmod 600 "$CANDIDATE_DIR/.env"
    ok "Owner, bot and fail-closed bootstrap settings created"
}

build_and_preflight(){
    log "Validating Compose and building the NOVERA image"
    cd "$CANDIDATE_DIR"
    bash deploy/vps-preflight.sh
    docker compose -f "$COMPOSE_FILE" config --quiet
    docker compose -f "$COMPOSE_FILE" build --pull delta
    docker run --rm --entrypoint python "novera-app:$RELEASE_ID" \
        -m compileall -q /app/delta_backend /app/main.py
    ok "Application image built and import-compiled"
}

promote_and_start(){
    log "Starting fail-closed bootstrap release"
    ln -s "$CANDIDATE_DIR" "$CURRENT_LINK.new-$STAMP"
    mv -Tf "$CURRENT_LINK.new-$STAMP" "$CURRENT_LINK"
    ln -s "$CURRENT_LINK" "$COMPAT_LINK"
    cd "$COMPAT_LINK"
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
    STARTED=1

    local healthy=0 container state
    for _attempt in $(seq 1 90); do
        container="$(docker compose -f "$COMPOSE_FILE" ps -q delta 2>/dev/null || true)"
        if [[ -n "$container" ]]; then
            state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
            if [[ "$state" == "healthy" ]]; then healthy=1; break; fi
        fi
        sleep 2
    done
    [[ "$healthy" == "1" ]] || {
        docker compose -f "$COMPOSE_FILE" logs --tail=120 --no-color delta >&2 || true
        fail "NOVERA backend did not become healthy"
    }

    local ready body
    for _attempt in $(seq 1 90); do
        if curl -fsS --connect-timeout 4 --max-time 12 "https://$DOMAIN/health" >/dev/null 2>&1; then
            ready="$(curl -fsS --connect-timeout 4 --max-time 12 "https://$DOMAIN/ready" 2>/dev/null || true)"
            body="$(curl -fsS --connect-timeout 4 --max-time 12 -H 'Cache-Control: no-cache' "https://$DOMAIN/?bootstrap=$STAMP" 2>/dev/null || true)"
            if printf '%s' "$ready" | jq -e \
                '.status == "ready" and .database == true and .setup.status == "bootstrap" and .setup.financial_ready == false' >/dev/null 2>&1 \
                && [[ "$body" == *"NOVERA"* ]]; then
                ok "Public HTTPS, API and fail-closed setup mode are ready"
                return 0
            fi
        fi
        sleep 2
    done
    docker compose -f "$COMPOSE_FILE" logs --tail=120 --no-color caddy delta >&2 || true
    fail "Public NOVERA bootstrap did not become ready"
}

print_summary(){
    cat <<EOF

NOVERA bootstrap installation completed.

Mini App:       https://$DOMAIN/
Owner ID:      $OWNER_ID
Release:       $CANDIDATE_DIR
Persistent:    $STATE_DIR
Setup state:   bootstrap (all financial operations locked)

Next:
1. Open the bot from Telegram as Owner ID $OWNER_ID.
2. Open NOVERA -> Admin -> System.
3. Validate RPC/WSS/seed, verify the derived treasury address, then activate.
4. After restart, enable only approved financial switches under Admin -> Terms.

The bot token and runtime encryption key were not printed.
EOF
}

main(){
    require_fresh_host
    check_platform
    install_base
    check_clock
    check_network_target
    install -d -m 0755 "$RELEASE_ROOT" "$RELEASES_DIR"
    extract_payload
    configure_bootstrap
    build_and_preflight
    promote_and_start
    STARTED=0
    print_summary
}

main "$@"
exit 0
__NOVERA_BOOTSTRAP_PAYLOAD__
