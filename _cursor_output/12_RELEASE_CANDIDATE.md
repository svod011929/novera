# I-12 — Release candidate

**Date:** 2026-09-05  
**Status:** **RC READY · HARD STOP BEFORE PRODUCTION**

This iteration prepared a self-contained installer and local verification only.  
**No production host was contacted. No install was executed.**

## Artifacts

| File | Role |
|------|------|
| `_cursor_output/releases/GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh` | Self-contained installer (~2.7 MB) |
| `…sh.sha256` | SHA-256 sidecar |
| `PAYLOAD_MANIFEST_20260905-210023.txt` | Critical payload hashes |
| `RELEASE_NOTES_V10_6_RC_NOVERA.md` | Owner-facing notes |
| `POST_DEPLOY_CHECKLIST.md` | After-install checklist |
| `scripts/build_release_candidate.ps1` | Reproducible RC builder |

**Installer SHA-256:** `71c0ff4f4c23e7a611c45a3f0cd63e2b42043ba20f1f754dcfc37051e5ca9350`

## What the builder does

1. Takes the V10.6 Safe Deploy installer stub from `_reference/INSTALLERS` (read-only).
2. Patches for this candidate:
   - payload marker `V10_6_RC_NOVERA`
   - release id `v10.6-rc-novera-<stamp>`
   - critical hashes for modified `api.py` / `repository.py`
   - brand self-tests / public smoke expect **NOVERA**
   - extra greps for I-08…I-11 surfaces
3. Packs the working tree **without** secrets, `.env`, sqlite, `_reference`, `_cursor_output`, `__pycache__`.
4. Embeds base64 tar payload; verifies round-trip extract + hash.

## Local verification performed

| Check | Result |
|-------|--------|
| RC build | PASS |
| Embedded payload extract | PASS (`compose.vps.yml`, `Dockerfile`, `.env.vps.example` present) |
| No secrets in payload | PASS |
| Critical file hash round-trip | PASS |
| `pytest -q` | **74 passed / 0 failed** |
| Production install | **NOT RUN** |

## Preflight / rollback rehearsal (paper + local only)

Full VPS preflight needs Docker, DNS, and secrets on a real host. On this Windows candidate tree:

| Step | Rehearsal |
|------|-----------|
| `deploy/vps-preflight.sh` | Reviewed; requires Linux VPS + `.env` + `secrets/bot_token.txt` — not executed |
| Verified DB backup | Logic present in installer (`sqlite3.backup` + `integrity_check`) — not executed against production DB |
| Rollback image capture | Installer tags `gfort-rollback:<stamp>` before cutover — not executed |
| Candidate reject before cutover | Installer `cleanup` removes candidate if preflight fails while `CUTOVER_STARTED=0` — documented |
| Payload hash gate | Updated critical hashes; mismatch aborts install before cutover |

Owner install permission is still required before any of the above run on a live server.

## Hard stop

Per `START_HERE.md` / `MASTER_PLAN.md` Stage 5:

> Owner gives a **separate** written permission to install.

Until that command:

- Do **not** copy the installer to production.
- Do **not** run it with `sudo`.
- Do **not** point DNS or secrets at this workspace.

Still open from I-11: P0/P1 owner decisions (manual investment treasury/referral policy, min/max, balance/level idempotency, wallet cutover). Installing while those remain unanswered keeps the release at **CONDITIONAL GO**.

## Rebuild

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release_candidate.ps1
```
