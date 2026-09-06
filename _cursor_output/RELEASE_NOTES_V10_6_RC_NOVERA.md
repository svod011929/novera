# Release notes — V10.6 RC NOVERA

**Build:** `GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023`  
**SHA-256:** `71c0ff4f4c23e7a611c45a3f0cd63e2b42043ba20f1f754dcfc37051e5ca9350`  
**Date (UTC):** 2026-09-05  
**Verdict base:** I-11 **CONDITIONAL GO** (`11_HARDENING_REVIEW.md`)

## What’s in this candidate

Public brand surface is **NOVERA**; Safe Deploy paths stay `/opt/gfort`, package `delta_backend`.

| Iteration | Highlights |
|-----------|------------|
| I-01…I-04 | Local verify, pytest green, design tokens, session dual headers NOVERA/GFORT |
| I-05…I-07 | Home/assets hierarchy, deposit invoice UX, admin user card IA |
| I-08 | Admin controls API tests + reason/operation_id validators (min/max still owner-gated) |
| I-09 | Wallet vs payout clarity (UI only; no address rewrite) |
| I-10 | Broadcast preview, audience count, admin-only test send, failed-delivery retry |
| I-11 | Financial golden fixtures + security hardening suite |

## Financial core

Unchanged by design: 10%/day · 20 days · principal return · referral bps `(800,400,250,150,100)` · invoice fractional tail. Locked by `tests/test_financial_regression.py`.

## Explicitly not in this RC

- Production install / cutover (hard stop)
- Answers to `OPEN_BUSINESS_DECISIONS.md` P0/P1
- Admin investment min/max clamp
- Balance/level Idempotency-Key
- Rewriting queued/signed/broadcast payout addresses on wallet change

## Artifacts

```
_cursor_output/releases/
  GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh
  GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh.sha256
  PAYLOAD_MANIFEST_20260905-210023.txt
```

Rebuild locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release_candidate.ps1
```

## Install command (DO NOT RUN without owner written approval)

```bash
# On the target VPS only after owner Stage-5 install permission:
sudo bash GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh
```

Secrets are prompted or taken from `GFORT_*` env vars at install time — none are embedded in the installer.
