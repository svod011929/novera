# Local development verification

Safe checks only. Never deploy, never load production secrets, never send payouts or user messages.

## One-command options

### Windows (PowerShell) — preferred on this machine

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_workspace.ps1 -InstallDeps
```

Without installing deps (compileall only / skip pytest if deps missing):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_workspace.ps1
```

### Docker (Windows / macOS / Linux) — no host Python

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_in_docker.ps1
```

```bash
bash scripts/verify_in_docker.sh
```

### Linux / Git Bash / WSL (original)

```bash
python3 -m pip install -r requirements-dev.txt
bash scripts/verify_workspace.sh
```

## What the checks do

1. `python -m compileall` on `delta_backend`, `tests`, `main.py`
2. `bash -n` on `deploy/*.sh` and `scripts/*.sh` when bash is available
3. `pytest -q` when FastAPI / aiogram / web3 / pytest are importable

## Snapshot baseline hashes

```bash
bash scripts/snapshot_baseline.sh
```

Windows fallback (already used in Stage 0): PowerShell `Get-FileHash` over the same trees into `_cursor_output/BASELINE_SHA256.txt`.

## Environment notes

- Do not create a real `.env` with production secrets in this workspace.
- `compose.testnet.yml` expects a local `.env` and starts the app; it is **not** the verify path. Use the Docker verify scripts above for tests without bringing the stack up.
- If verify fails only because Docker/Python are missing, install one of them; that is an environment gap, not an application defect.
