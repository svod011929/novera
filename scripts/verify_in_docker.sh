#!/usr/bin/env bash
# GFORT isolated verify via Docker (no host Python required).
# Does not start the app, does not load production secrets, does not deploy.
# Usage:
#   bash scripts/verify_in_docker.sh

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="${GFORT_VERIFY_IMAGE:-python:3.12-slim}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed or not on PATH."
  echo "Fallback: bash scripts/verify_workspace.sh  (with local Python + requirements-dev)"
  echo "No production action was performed."
  exit 2
fi

echo "GFORT Docker workspace verification"
echo "Root: $project_root"
echo "Image: $image"

docker run --rm \
  -v "$project_root:/app" \
  -w /app \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONUNBUFFERED=1 \
  "$image" \
  bash -lc '
    set -euo pipefail
    cd /app
    echo "Python: $(python --version)"
    python -m pip install --upgrade pip
    python -m pip install -r requirements-dev.txt
    python -m compileall -q delta_backend tests main.py
    for script in deploy/*.sh scripts/*.sh; do
      bash -n "$script"
    done
    pytest -q
    echo "Workspace syntax checks and tests passed. No production action was performed."
  '
