# GFORT — Implementation Plan (post Stage 0)

**Date:** 2026-09-05  
**Rule:** One small iteration at a time. No production. Financial semantics unchanged without written owner decision.  
**Coding gate:** Per `docs/MASTER_PLAN.md`, source edits start only after owner confirms a specific iteration ID below.

## Priority order (aligned with `_owner_inputs/PRIORITIES.md`)

1. Money / data / double-payout safety  
2. Telegram auth / session bugs  
3. User Mini App UX  
4. Admin panel UX  
5. Harden existing V10.6 admin controls (tests, limits, audit polish) — **not** new financial formulas  
6. Notifications / broadcasts polish  
7. Release candidate  

## Iteration backlog

### I-01 — Local dev self-test environment (docs/scripts only)

- **Scope:** Document or add a Windows-friendly verify path (Docker/`compose.testnet.yml`) so `compileall` + `pytest` run without host Python/bash.
- **Files:** `scripts/*`, `_cursor_output/TEST_REPORT.md` (no `delta_backend` / `frontend` logic).
- **API/DB:** none  
- **Acceptance:** One documented command produces green syntax + pytest (or clear skip reasons).
- **Tests:** `pytest -q` inside container.
- **Rollback:** delete script/doc changes.
- **Risk:** low.

### I-02 — UX audit backlog with acceptance criteria (analysis only)

- **Scope:** Screen-by-screen inventory vs MASTER_PLAN §6–7; P0/P1/P2 list for overlap, RU strings, empty/error/offline, 360/390/430.
- **Files:** `_cursor_output/02_UX_AUDIT.md` only.
- **API/DB:** none  
- **Acceptance:** Every user + admin screen has findings + AC.
- **Rollback:** n/a  
- **Risk:** none to runtime.

### I-03 — Design tokens + component primitives (DONE 2026-09-05)

- Token source: `frontend/assets/design-tokens.css`; brand layer rewritten to consume it
- Primitives + 360/390/430 gutters; spec `_cursor_output/03_DESIGN_TOKENS.md`
- Visual-only; no business copy / formula changes

### I-04 — Session / Telegram account switch hardening (DONE 2026-09-05)

- Fixed NOVERA/GFORT session header mismatch (root cause of post-rebrand session failures)
- Dual storage keys; clear conflicting token; RU account-mismatch path; pytest coverage
- Details: `TEST_REPORT.md` / `CHANGELOG.md`

### I-05 — User home / assets clarity (DONE 2026-09-05)

- Home: active / next payout / received / projected remaining / partner available
- Assets: paid / remaining / next payment labeled; expected never presented as withdrawable
- Frontend only (`index.html`, `app.js`, `novera-brand.css`)

### I-06 — Deposit invoice UX (DONE 2026-09-05)

- Network / exact amount (+ tail hint) / address / TTL status / copy feedback clarified
- Invoice fractional matching tail unchanged (owner constraint)
- Frontend only

### I-07 — Admin user card IA (DONE 2026-09-05)

- Tabbed modal: Overview / Investments / Payouts / Referral / Access / Audit
- All V10.6 controls retained; money ops require reason + confirm
- Frontend only

### I-08 — Harden V10.6 admin controls (DONE 2026-09-05)

- API tests: referral-balance / referral-level / investments (`tests/test_admin_controls_api.py`)
- Additive validation: strip `reason` (≥2 after strip); strip `operation_id` for investments
- Investment `operation_id` already idempotent (covered); balance/level Idempotency-Key **deferred** (no owner confirm)
- Deposit min/max clamp for admin investment **deferred** (no owner confirm) — see `DECISIONS.md` D-20
- Result: **30 passed / 0 failed**; details in `TEST_REPORT.md`

### I-09 — Wallet change vs payout states (DONE 2026-09-05)

- Frontend clarity only: profile address vs frozen deposit/payout addresses
- User wallet: impact copy + open pipeline counts; confirm on address change
- History/assets/admin: show which address applies; admin strip queued/signed/broadcast
- Server behavior **unchanged** — cutover policy still open in `OPEN_BUSINESS_DECISIONS.md`
- Details: `TEST_REPORT.md` / `CHANGELOG.md` / `DECISIONS.md` D-22

### I-10 — Broadcast / notifications polish (DONE 2026-09-05)

- Composer: Telegram-style preview (JS mirror of `sanitize_telegram_html`), length counter, caption-split warning
- Audience recipient count + confirm before send; test send goes **only to the acting admin**
- List: localized audience, progress bar, delivered/failed/pending, last error, retry of failed deliveries
- Additive API: `GET /broadcasts/audience`, `POST /broadcasts/test`, `POST /broadcasts/{id}/retry`
- Sanitized HTML pipeline unchanged; no mass send performed from this workspace
- Details: `TEST_REPORT.md` / `CHANGELOG.md` / `DECISIONS.md` D-23

### I-11 — Hardening suite + independent review (DONE 2026-09-05)

- Financial golden fixtures: `tests/test_financial_regression.py` (bps floor, 10%/20d, L1 accrual, day-20 principal, full cycle)
- Security: `tests/test_security_hardening.py` (IDOR, non-admin matrix, login replay, XSS allowlist, auth fail-closed)
- Verdict: **CONDITIONAL GO** — see `_cursor_output/11_HARDENING_REVIEW.md`
- Open owner gates (P0/P1, cutover) unchanged; no formula/production changes
- pytest: **74 passed / 0 failed**

### I-12 — Release candidate (DONE 2026-09-05 · HARD STOP)

- Builder: `scripts/build_release_candidate.ps1` (no secrets embedded)
- Artifact: `_cursor_output/releases/GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh`
- SHA-256: `71c0ff4f4c23e7a611c45a3f0cd63e2b42043ba20f1f754dcfc37051e5ca9350`
- Payload extract + critical hash round-trip verified locally; pytest **74/74**
- Docs: `12_RELEASE_CANDIDATE.md`, `RELEASE_NOTES_V10_6_RC_NOVERA.md`, `POST_DEPLOY_CHECKLIST.md`
- **Production install NOT performed** — requires separate owner command

## Recommended first coding confirmation

After Stage 1 UX audit (I-02, analysis-only), request owner confirmation for:

1. **I-01** (dev verify path) and/or  
2. **I-03** (design tokens) and/or  
3. **I-04** (session hardening)

I-08 shipped tests + strip validators only. Do **not** add deposit min/max clamp or balance/level Idempotency-Key until owner answers `OPEN_BUSINESS_DECISIONS.md` / P0 manual-investment policy.

### I-01b — Close baseline pytest failures (DONE 2026-09-05)

Discovered by I-01 local run (22 pass / 4 fail). Result: **26 pass / 0 fail**.

1. Telegram `max_age_seconds=0` contract — code: `0` disables age check like `None`
2. Referral idempotency fixture → asserts `referral_accruals` (V8 model), zero direct referral `payouts`
3. Cookie clear when initData overrides shared session — server already correct; test asserts `Set-Cookie … Max-Age=0`
4. `Header.strip` crash on login-token account switch — code: `_header_text()` helper; expected 409 restored

No production; no yield/principal/referral-% formula changes. Details: `TEST_REPORT.md`.

## Explicitly deferred (approval gates)

- Changing profit bps, days, principal return semantics, referral %  
- Removing invoice fractional matching  
- Production deploy / `--fresh` / destructive SQL / real payouts / real user messages  
- Changing debit-withdrawal accrual linking behavior without owner review of P1 finding  
