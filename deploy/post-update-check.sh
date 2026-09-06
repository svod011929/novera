#!/usr/bin/env bash
# One-shot post-promote verification for NOVERA on a live VPS.
set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
    if [[ -f /opt/gfort/current/.env ]]; then
        DOMAIN="$(awk -F= '$1=="API_DOMAIN"{print substr($0,index($0,"=")+1);exit}' /opt/gfort/current/.env)"
    fi
fi
[[ -n "$DOMAIN" ]] || { echo "Usage: bash deploy/post-update-check.sh <domain>" >&2; exit 2; }

echo "current=$(readlink -f /opt/gfort/current 2>/dev/null || true)"
curl -fsS --connect-timeout 4 --max-time 12 "https://$DOMAIN/health"
echo
curl -fsS --connect-timeout 4 --max-time 12 "https://$DOMAIN/ready"
echo
curl -fsS --connect-timeout 4 --max-time 12 -H 'Cache-Control: no-cache' "https://$DOMAIN/" | grep -o '<title>[^<]*</title>' | head -1
cd /opt/gfort/current
docker compose -f compose.vps.yml ps
