#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed" >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is not installed" >&2
    exit 1
fi
if [ ! -f .env ]; then
    echo ".env is missing; copy .env.vps.example and fill it" >&2
    exit 1
fi

for secret_file in secrets/bot_token.txt
do
    if [ ! -s "$secret_file" ]; then
        echo "$secret_file is missing or empty" >&2
        exit 1
    fi
done

if grep -Eq 'example\.com|your_support|^ADMIN_IDS=123456789$' .env; then
    echo ".env still contains placeholder values" >&2
    exit 1
fi

api_domain=$(awk -F= '$1 == "API_DOMAIN" {print substr($0, index($0, "=") + 1); exit}' .env)
expected_ipv4=$(awk -F= '$1 == "EXPECTED_VPS_IPV4" {print substr($0, index($0, "=") + 1); exit}' .env)
if [ -z "$api_domain" ] || [ -z "$expected_ipv4" ]; then
    echo "API_DOMAIN and EXPECTED_VPS_IPV4 are required" >&2
    exit 1
fi

resolved_ipv4=$(getent ahostsv4 "$api_domain" 2>/dev/null | awk '{print $1}' | sort -u)
if [ -z "$resolved_ipv4" ]; then
    echo "$api_domain does not resolve to an IPv4 address yet" >&2
    exit 1
fi
if ! printf '%s\n' "$resolved_ipv4" | grep -Fxq "$expected_ipv4"; then
    echo "$api_domain must resolve to $expected_ipv4 before HTTPS startup" >&2
    echo "Current A records: $resolved_ipv4" >&2
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this preflight with sudo so private files get safe ownership" >&2
    exit 1
fi

mkdir -p data backups
chown -R 10001:10001 data backups
chmod 750 data backups
chown root:10001 secrets/bot_token.txt
chmod 640 secrets/bot_token.txt
chown root:root .env
chmod 600 .env
docker compose -f compose.vps.yml config --quiet
echo "VPS preflight passed"
