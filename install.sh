#!/usr/bin/env bash
# NOVERA — тонкая curl-точка входа.
# Скачивает закреплённый one-file bootstrap installer из этого
# приватного репозитория, проверяет SHA-256 и запускает его.
set -euo pipefail

REPO="${NOVERA_REPO:-svod011929/novera}"
REF="${NOVERA_REF:-main}"
INSTALLER_NAME="NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh"
EXPECTED_SHA256="85b5b6b54147e7d683777bb529ae4d7d937ac8de71f005180b85ec6d20eab415"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/novera-bootstrap.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "нужна команда: $1" >&2
    exit 1
  }
}

need curl
need sha256sum
need bash

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запускайте от root (sudo)." >&2
  exit 1
fi

TOKEN="${NOVERA_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"
if [[ -z "$TOKEN" ]] && command -v gh >/dev/null 2>&1; then
  TOKEN="$(gh auth token 2>/dev/null || true)"
fi
if [[ -z "$TOKEN" ]]; then
  cat >&2 <<'EOF'
Для приватного репозитория нужен GitHub-токен.

Экспортируйте один из вариантов:
  export NOVERA_GH_TOKEN=ghp_...
  export GH_TOKEN=...          # или: gh auth login

Затем повторите установку.
EOF
  exit 1
fi

RAW_URL="https://raw.githubusercontent.com/${REPO}/${REF}/_cursor_output/releases/${INSTALLER_NAME}"
OUT="${WORK}/${INSTALLER_NAME}"

echo "[NOVERA] Скачиваю ${INSTALLER_NAME}"
HTTP_CODE="$(curl -fsSL \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github.raw" \
  -o "$OUT" \
  -w '%{http_code}' \
  "$RAW_URL" || true)"

if [[ "$HTTP_CODE" != "200" ]] || [[ ! -s "$OUT" ]]; then
  # Запасной путь: Contents API (если raw для private недоступен)
  API_URL="https://api.github.com/repos/${REPO}/contents/_cursor_output/releases/${INSTALLER_NAME}?ref=${REF}"
  curl -fsSL \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github.raw" \
    -o "$OUT" \
    "$API_URL"
fi

ACTUAL="$(sha256sum "$OUT" | awk '{print $1}')"
if [[ "$ACTUAL" != "$EXPECTED_SHA256" ]]; then
  echo "Не совпал SHA-256" >&2
  echo "  ожидался: $EXPECTED_SHA256" >&2
  echo "  получен:  $ACTUAL" >&2
  exit 1
fi
echo "[NOVERA] SHA-256 OK (${ACTUAL:0:12}…)"

chmod 0755 "$OUT"
exec bash "$OUT" "$@"
