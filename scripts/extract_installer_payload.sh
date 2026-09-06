#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 INSTALLER.sh EMPTY_DESTINATION" >&2
  exit 2
fi

installer="$1"
destination="$2"

[[ -f "$installer" ]] || { echo "Installer not found: $installer" >&2; exit 2; }
mkdir -p "$destination"

if find "$destination" -mindepth 1 -print -quit | grep -q .; then
  echo "Destination must be empty: $destination" >&2
  exit 2
fi

marker_line="$(awk '/^__GFORT_FINAL_.*PAYLOAD__$/ {print NR; exit}' "$installer")"
[[ -n "$marker_line" ]] || { echo "Payload marker not found" >&2; exit 2; }

tail -n "+$((marker_line + 1))" "$installer" \
  | base64 -d \
  | tar --no-same-owner -xzf - -C "$destination"

echo "Payload extracted to $destination"
