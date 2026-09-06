#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$project_root/_cursor_output"
output_file="$output_dir/BASELINE_SHA256.txt"
mkdir -p "$output_dir"

cd "$project_root"
find delta_backend frontend tests deploy -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum > "$output_file"

sha256sum Dockerfile main.py pyproject.toml requirements.txt requirements-dev.txt \
  compose.vps.yml compose.testnet.yml >> "$output_file"

echo "Baseline hashes written to $output_file"

