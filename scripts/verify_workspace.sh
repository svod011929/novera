#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

echo "GFORT local workspace verification"
echo "Python: $(python3 --version 2>&1)"

python3 -m compileall -q delta_backend tests main.py

for script in deploy/*.sh scripts/*.sh; do
  bash -n "$script"
done

if command -v pytest >/dev/null 2>&1; then
  if python3 -c 'import fastapi, aiogram, web3' >/dev/null 2>&1; then
    pytest -q
  else
    echo "Python dependencies are incomplete; pytest skipped until an isolated development environment is prepared."
  fi
else
  echo "pytest is not installed; test execution skipped."
fi

echo "Workspace syntax checks passed. No production action was performed."

