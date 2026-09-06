# Owner decision pack — as implemented (2026-09-06)

Owner verbal accept 2026-09-06 («Все норм»): keep current behaviour for all rows below.

## OPEN_BUSINESS_DECISIONS — ACCEPTED

| # | Decision | Owner |
|---|----------|-------|
| 1 | 200% = profit only; principal returned separately (~300% gross nominal) | ACCEPT |
| 2 | Freeze payout address at **queued**; deposit schedule address freezes at open | ACCEPT |
| 3 | Line turnover = **active first-line principal** | ACCEPT |
| 4 | Manual level = prospective qualification override with future commission rights | ACCEPT |
| 5 | Client-side `confirm` is enough for wallet change (no server 2FA) | ACCEPT |
| 6 | Roles: User / full Admin / immutable Owner only | ACCEPT |

## Hardening P0/P1 — ACCEPTED as documented

| ID | Decision | Owner |
|----|----------|-------|
| P0 | Manual investment = unfunded liability; keep warnings; fund treasury before use | ACCEPT |
| P0 | Admin-opened deposits participate in referral path | ACCEPT |
| P1 | Admin investment may bypass deposit min/max | ACCEPT |
| P1 | Balance/level `Idempotency-Key` shipped 2026-09-06 | DONE |

## Activation checklist (owner-only, live — still open)

1. Off-server copy of `/opt/gfort/state/secrets/runtime_config_key.txt`
2. Telegram Mini App as Owner → **Admin → System**
3. Fill RPC / WSS / seed / token / scan block → **Validate**
4. Re-enter derived treasury address → **Activate**
5. Confirm `/ready` → `setup.status=active`, then enable approved **Admin → Terms** switches
6. Do **not** enable deposits/payouts until RPC/WSS/treasury funded and tested

Financial formulas unchanged by these accepts.
