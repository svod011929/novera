# GFORT Stage 0 — Baseline Audit

**Date:** 2026-09-05  
**Candidate:** V10.6 Admin Controls (base: V10.5 Safe Deploy + V10.4 Safety)  
**Mode:** Analyst only — source code not modified  
**Production:** not touched  

## 1. Workspace verification

| Check | Result |
|-------|--------|
| `bash scripts/verify_workspace.sh` | Not executed: host has no `bash`; WSL distro not installed |
| PowerShell SHA-256 snapshot | Done → `_cursor_output/BASELINE_SHA256.txt` (40 source files, no `__pycache__`) |
| `python3 -m compileall` | Skipped: Python runtime not available (WindowsApps stubs only) |
| `pytest` | Skipped: no local Python/deps |
| Secrets / `.env` | Not read; not present in reports |

**Assumption:** full syntax/pytest suite will be re-run inside a Linux/Docker/devcontainer environment before any code iteration that touches runtime.

## 2. Architecture map

### Stack

- **Backend:** FastAPI (`delta_backend/api.py`), SQLite via `aiosqlite` (`repository.py`), single uvicorn worker (`main.py`)
- **Frontend:** vanilla HTML/CSS/JS Mini App (`frontend/`), Telegram WebApp API
- **Bot:** aiogram launcher (`launcher.py`)
- **Chain:** BEP-20 USDT, deposit WSS + HTTP fallback, payout signer/reconciler
- **Deploy:** Docker + Caddy + Safe Deploy release layout (`/opt/gfort/releases`, persistent `/opt/gfort/state`)

### Background workers (lifespan)

| Worker | Role |
|--------|------|
| `daily-payout-worker` | Schedule / sign / broadcast / confirm daily + principal + referral payouts |
| `deposit-http-monitor` | HTTPS log scan, backfill, invoice expiry |
| `deposit-wss-monitor` | Alchemy WSS Transfer + newHeads → confirm → credit |
| `telegram-miniapp-launcher` | `/start`, partner stats, admin WebApp buttons |
| `telegram-broadcast-worker` | Drain `broadcast_deliveries` |
| `telegram-user-notification-worker` | Drain `user_notifications` |
| Safety monitor | Circuit breaker, integrity, SQLite backups |

### User API

- `POST /api/session/exchange`
- `GET /api/bootstrap`
- Notifications: list / read / read-all
- `GET /api/team`
- `POST /api/referrals/withdraw`
- `POST /api/wallet`
- `POST /api/deposits/invoice`
- Ops: `GET /health`, `GET /ready`

### Admin API (all `Depends(admin_user)`)

- Summary, users list/detail, block, balance, wallet, referrer
- **V10.6:** `POST .../referral-balance`, `POST .../referral-level`, `POST .../investments`
- Admins grant/list/delete
- Deposits, operations, payout retry
- Broadcasts + media
- Treasury + test payout
- Settings, terms, audit, chain-config, safety, system

### Frontend views

| User `view=` | Admin `tab=` |
|--------------|--------------|
| home, assets, wallet, team, history, profile, notifications | overview, users, deposits, payouts, broadcasts, admins, terms, links, treasury, system, logs |

Admin user modal already contains V10.6 controls: referral balance, manual investment, partner level.

### Core tables

`users`, `admin_grants`, `web_login_tokens`, `deposit_invoices`, `chain_deposits`, `deposits`, `payouts`, `referral_rewards`, `referral_accruals`, `sync_state`, `audit_events`, `safety_state`, `runtime_settings`, `balance_adjustments`, `referrer_adjustments`, **`referral_balance_adjustments`**, **`referral_level_overrides`**, **`referral_level_adjustments`**, **`admin_investment_openings`**, `broadcasts`, `broadcast_deliveries`, `user_notifications`

Migrations: inline `_migrate()` on connect (CREATE IF NOT EXISTS + conditional ALTER). No Alembic.

## 3. Financial invariants (immutable without owner decision)

1. Amounts are integer **minor units** (6 decimals, `MINOR_FACTOR=10^6`).
2. Default terms: **1000 bps/day × 20 days**; deposit min/max 10…100_000 USDT.
3. Daily profit: `principal_minor * daily_profit_bps // 10000` (integer floor).
4. Principal returned as separate `subtype=principal` payout on last day; deposit completes only after all profit days + principal confirmed.
5. Referral levels 1–5 bps: `(800,400,250,150,100)` with personal/line thresholds; admin override can unlock qualification for future accruals only.
6. Invoice: unique pending `exact_minor`; fuzzy tail `+1..99`; max 3 pending/user; idempotency key.
7. Chain deposit unique on `(chain_id, tx_hash, log_index)`.
8. Payout states: `queued → signed → broadcast → confirmed | failed`; unique `idempotency_key`.
9. Circuit breaker blocks **new signatures** only; signed/broadcast still reconcile.
10. Low USDT/BNB or ambiguous broadcast → do not create double-sign hazard; keep signed bytes/nonce when ambiguous.
11. `manual_balance_minor >= 0`; referral available clamped `max(0, …)`; no self-referral.
12. Financial mutations use `BEGIN IMMEDIATE`; admin mutations require reason / confirm where specified.
13. Matching invoice fractional tail remains required until owner provides another matching method.

## 4. State machines

| Domain | States |
|--------|--------|
| Invoice | `pending → paid \| expired` |
| Deposit | `active → completed` (schema also allows `paused`/`failed`) |
| Payout | `queued → signed → broadcast → confirmed \| failed` |
| Broadcast | `queued → sending → completed \| failed` |
| Notification telegram | `queued → sending → delivered \| failed` |

## 5. V10.5 → V10.6 delta

**Unchanged (byte-identical / functionally same):** `main.py`, all `delta_backend/services/*`, payout/deposit/blockchain/safety engines, `styles.css`, most tests except repository additions.

**Changed / new runtime surface:**

| Area | Change |
|------|--------|
| Referral balance | Admin set available balance; `referral_balance_adjustments`; withdrawals mark accruals **and** adjustments |
| Manual investment | Creates paid invoice + active deposit; real daily/principal liability; idempotent `operation_key` + `confirm=OPEN_INVESTMENT` |
| Partner level | Override 1–5 or clear (0); future accruals only; audit + notify |
| Pending/failed referral metrics | Now based on referral **payout** rows (needed with adjustments) |
| Docs/scripts | Cursor workspace scaffolding only |

Admin controls are **wired end-to-end** (API + repository + UI + repository tests). Gaps are quality/risk, not missing screens.

## 6. Risk register

| Sev | Finding | Notes |
|-----|---------|-------|
| **P0** | Manual investment creates unpaid treasury liability | No on-chain USDT in; schedule still pays daily + principal |
| **P0** | Admin deposits participate in normal referral accrual path | Upline can earn commissions on non-chain capital |
| **P1** | Referral debit vs withdrawal linking | Debit can leave accrual “withdrawn” accounting mismatched vs payout amount |
| **P1** | Admin investment bypasses deposit min/max | Only `principal_minor > 0` |
| **P1** | Referral balance/level lack idempotency keys | Investment has `operation_id`; balance/level do not |
| **P2** | No HTTP/API tests for three new admin routes | Only `tests/test_repository.py` coverage |
| **P2** | Level override can unlock all 5 levels | Future accruals expansion if abused |
| **P2** | UI: layout overlap / RU system messages / session switch (owner known bugs) | UX, not core formula |
| **P3** | Pending metric formula change | Display-level; should be safer with adjustments |
| **P3** | Local Windows cannot run bash/pytest | Blocks Stage 0 self-test proof until Linux/Docker env |

## 7. Current UI states (inventory)

- Loading / connecting, session expired, auth failed, account blocked
- Empty lists (assets, history, team, notifications, admin histories)
- Invoice create success; wallet validation; copy feedback
- Admin mutation toasts (balance, referral, investment, level, broadcast)
- Offline / request failed / rate limit texts present in i18n (RU primary)

Owner-reported UX gaps: text overlap on some devices; RU system popups; “Сессия устарела” / account switch mix; richer broadcasts; clearer wallet-change vs queued payouts.

## 8. Regression fixtures / test inventory

| File | Covers |
|------|--------|
| `tests/test_telegram_auth.py` | initData HMAC validity |
| `tests/test_api.py` | Session, deposit gate, account switch protection |
| `tests/test_repository.py` | Deposit/referral idempotency; invoices; block/broadcast; **admin referral controls**; **admin investment idempotency** |
| `tests/test_fast_deposits.py` | WSS confirm path |
| `tests/test_safety.py` | Low USDT keeps payout queued |
| `tests/test_deployment_settings.py` | Env/mode validation |

**Needed before release (not yet present):** API-layer tests for new admin mutations; concurrent debit; insufficient referral balance after debit; admin investment min/max policy decision; financial regression golden amounts for V10.5 schedules.

## 9. Open business decisions (owner only)

See `_owner_inputs/OPEN_BUSINESS_DECISIONS.md`. Until answered, current code behavior is preserved:

- Principal vs “200% cycle” marketing math
- Wallet change cutover status (`queued` / `signed` / `broadcast`)
- Definition of line turnover
- Whether manual level only unlocks qualification (current code) vs broader rights
- Extra confirmations for payout address change
- Role model beyond Owner / full Admin

## 10. Stage 0 verdict

- Baseline architecture, APIs, workers, tables, invariants, and V10.5→V10.6 delta are documented.
- Source tree left unchanged.
- Production not contacted.
- Local host cannot run official bash verify/pytest; SHA-256 baseline captured via PowerShell.
- Ready for Stage 1 UX audit and for owner confirmation of the first **non-financial** implementation iteration (see `01_IMPLEMENTATION_PLAN.md`).
