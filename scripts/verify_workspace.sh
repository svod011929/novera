#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

echo "GFORT local workspace verification"
echo "Python: $(python3 --version 2>&1)"
echo "Tip: on Windows without bash use scripts/verify_workspace.ps1 or scripts/verify_in_docker.ps1"
echo "Docs: _cursor_output/DEV_VERIFY.md"

python3 -m compileall -q delta_backend tests main.py

for script in deploy/*.sh scripts/*.sh; do
  bash -n "$script"
done

if command -v pytest >/dev/null 2>&1; then
  if python3 -c 'import fastapi, aiogram, web3' >/dev/null 2>&1; then
    pytest -q
  else
    echo "Python dependencies are incomplete; pytest skipped until an isolated development environment is prepared."
    echo "Install: python3 -m pip install -r requirements-dev.txt"
    echo "Or: bash scripts/verify_in_docker.sh"
  fi
else
  echo "pytest is not installed; test execution skipped."
  echo "Install: python3 -m pip install -r requirements-dev.txt"
  echo "Or: bash scripts/verify_in_docker.sh"
fi

echo "Workspace syntax checks passed. No production action was performed."

