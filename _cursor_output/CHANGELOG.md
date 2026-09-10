# CHANGELOG (Cursor working notes)

## 2026-09-10 — Payout worker: delegated treasury serialization + dropped-tx recovery

Motivated by the 2026-09-10 BSC mainnet incident (EIP-7702 delegated treasury:
in-flight limit / gapped-nonce rejections, a broadcast that never propagated,
duplicate-nonce rows after manual retry, a 0.05 gwei transaction that never mined).

- `delta_backend/services/blockchain.py`: `is_delegated()` (eth_getCode prefix
  `0xef0100`, cached 180 s), `latest_nonce()`, `pending_nonce()`,
  `transaction_exists()`, `transaction_gas_price()` (fail-closed across endpoints
  like `receipt_status`), `sign_token_transfer(nonce=…)` for same-nonce
  replacements only. `receipt_status` semantics unchanged.
- `delta_backend/services/payouts.py`:
  - (A) delegated treasury → in-flight `signed+broadcast` capped at 1; batch
    behaviour unchanged for plain EOAs; delegation check failure fails safe to 1.
    `in-flight transaction limit reached` / `gapped-nonce` are transient in
    `_broadcast` (row stays `signed`, error recorded, no failure).
  - (B) `broadcast` rows without a receipt for ≥15 s re-send the stored
    `raw_transaction` (same bytes/nonce, never re-signed; `already known` /
    `nonce too low` are fine). When on-chain nonce > payout nonce and the hash is
    unknown to every endpoint for 3 consecutive passes → `failed` with an explicit
    reason for admin retry. Never failed while latest nonce == payout nonce.
  - (C) before signing, pause when any in-flight row holds a nonce ≥ the RPC
    pending nonce (duplicate-nonce guard); comment documents why delegated
    treasuries cannot produce duplicates under (A).
  - (D) stalled pending tx older than `safety_payout_stuck_seconds/2` with latest
    nonce == payout nonce → same-nonce replacement at
    `max(current×1.5, old×1.125)`, at most 3 bumps per payout, row stays
    `broadcast`; previous hashes kept so reconcile confirms whichever mines.
- `delta_backend/repository.py`: additive nullable `payouts.replaced_tx_hashes`
  (JSON, migration via `ALTER TABLE`), `replace_payout_transaction()`
  (broadcast rows only, atomic), `retry_payout` also clears the new column,
  `parse_replaced_tx_hashes()` helper.
- Tests: `tests/test_payout_recovery.py` (25 cases, fake chain + real SQLite
  repository); `tests/test_safety.py` fake gained `is_delegated`.
- No deposit logic, economics, payout amounts/schedule or nonce source for new
  payouts changed. Production not contacted.

## 2026-09-07 — Branded bootstrap installer profiles

- Added `_owner_inputs/BRAND_PROFILES/` (`novera` + `_template`) with non-secret
  name/logo/colors/domain/owner defaults.
- Extended `scripts/build_bootstrap_installer.ps1 -BrandProfile <id>` and
  `scripts/apply_brand_profile.ps1` to bake branding into the one-file installer.
- Stub uses `$APP_NAME` for public ready-check/messages; technical payload marker
  and `NOVERA_*` env names stay stable.
- Docs: `_owner_inputs/BRAND_PROFILES/README.md`, README white-label section.

## 2026-09-07 — NOVERA-only public branding

- Removed the retired brand from bot notifications, inline buttons, API errors,
  safety alerts and frontend runtime source.
- Added startup migration for durable notifications, broadcasts and audit text.
- Restored hidden session/storage compatibility aliases without exposing them
  in user-facing copy.
- Added decoded-payload brand gate and rebuilt pinned installer:
  `NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh`
  (`759fe144e5520805576cb124030a6fc08bbd2a540e3cd2bf6e67ef25b2549b45`).

## 2026-09-06 — Decision pack + System wizard + admin idempotency

- Added `_owner_inputs/DECISION_PACK_AS_IMPLEMENTED.md` (as-implemented answers + activation checklist)
- Admin → System: activation step list, key-backup hint, post-activate Terms CTA
- P1 hardening: `Idempotency-Key` for admin user-balance / referral-balance / referral-level
  (`admin_control_idempotency` table; replay returns `reused=true`, payload mismatch → 409)
- Cache bust `novera-master-followup-3`

## 2026-09-06 — Master-plan follow-up (Stage 3/4 UX + responsive)

- Stage 3 admins: owner-model card, immutable Owner badge, grant disabled for non-owner, confirm before remove
- Stage 3 links: audit hint, open/preview buttons, profile-button preview strip
- Stage 4: offline banner + retry, slow-network status, request timeout, focus-visible, reduced-motion, nav `aria-current`
- Brand wordmark no longer truncates to `NOVE…` at ≤520px
- Cache bust `novera-master-followup-2`; live CDP proof updated in `RESPONSIVE_PROOF_360_390_430.md`

## 2026-09-06 — Staged UX updates + safe VPS promote

- Added `deploy/safe-update.sh`, `deploy/post-update-check.sh`,
  `scripts/safe_update_remote.ps1`: staged release under `/opt/gfort/releases`,
  shared state/secrets, frontend-only Caddy remount or full delta recreate,
  `/ready` setup-status gate, automatic rollback, pre-update backup
- Added `deploy/backup-rehearsal.sh` (non-destructive integrity check)
- Track A: history status hints, team available/pending/source/withdraw reasons,
  notifications empty/error/unread, session recover CTA, 360/390/430 touch targets
- Track B: admin overview safety/queue/freshness, deposit/payout age + retry hint,
  users list filters
- Track C notes: `_cursor_output/WSS_HTTP_BOOTSTRAP_NOTES.md`,
  `_cursor_output/RESPONSIVE_PROOF_360_390_430.md`

## 2026-09-06 — Ubuntu 26.04 fix, clock guard, production bootstrap

- Installer: replaced `install -d -o/-g` with `mkdir` + `chown` + `chmod`;
  uutils coreutils (Ubuntu 26.04) rejects numeric IDs without a passwd entry,
  which aborted the first install right after payload extraction
- Installer: normalises extracted payload modes to 0755/0644 (Windows-built
  tar carried 0666/0777 into the Caddy-served release tree)
- Installer: new `check_clock` step — measures skew against the
  `api.telegram.org` Date header, asks chrony to step once, fails closed above
  120 s (Telegram auth rejects `auth_date` > server time + 300 s)
- Rebuilt artifact: `releases/NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh`,
  SHA-256 `85b5b6b54147e7d683777bb529ae4d7d937ac8de71f005180b85ec6d20eab415`
- Production bootstrap performed on `170.168.91.129` / `bnbb.tech` at the
  owner's explicit request; host clock fixed via chrony + Cloudflare NTS first.
  Result recorded in `NOVERA_BOOTSTRAP_RELEASE.md`

## 2026-09-05 — NOVERA secure bootstrap installer

- Added production setup states `bootstrap/configured/active/degraded` and a
  separate `financial_ready` gate
- Fresh production starts with chain/deposits/payouts/investments/referrals,
  demo and simulation disabled
- Added immutable `OWNER_IDS`; dynamic admins cannot rotate signer, activate
  chain configuration or grant/revoke administrators
- Replaced plaintext runtime secret files with a versioned AES-256-GCM bundle
  using an installer-generated Docker secret key
- Split chain validation and activation; activation requires generation,
  idempotency key, reason, exact derived treasury confirmation and fresh
  Telegram initData
- Added public-address endpoint validation, secret-safe validation responses,
  no-store responses and redacted chain audit reason fingerprints
- Added owner setup wizard with Telegram WebView seed-risk warning and DOM
  clearing after submit
- Backups now include SQLite plus encrypted active generation; added guarded
  restore with integrity verification and automatic rollback
- Added canonical stub + `scripts/build_bootstrap_installer.ps1`
- Final artifact:
  `releases/NOVERA_BOOTSTRAP_INSTALLER_20260905-220159.sh`
- SHA-256:
  `9bfe81db3eb67d37992b82ca6d6fc2ed4f033f4b35af3e2c87d44feb7c16d378`
- Full pytest: **90 passed / 0 failed**; JS/shell parse and independent 74-file
  payload round-trip passed
- **No production installation performed**

## 2026-09-05 — I-12 release candidate (hard stop)

- Added `scripts/build_release_candidate.ps1`: packs current tree into a Safe Deploy installer without secrets
- Patched V10.6 stub for NOVERA brand smoke, updated `api.py`/`repository.py` critical hashes, RC self-tests (I-08…I-11)
- Built `_cursor_output/releases/GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh`
- SHA-256 `71c0ff4f4c23e7a611c45a3f0cd63e2b42043ba20f1f754dcfc37051e5ca9350`; payload extract verified
- Release notes + post-deploy checklist + preflight/rollback paper rehearsal in `_cursor_output/12_RELEASE_CANDIDATE.md`
- **No production install / SSH / secrets contact**
- pytest: **74 passed / 0 failed**

## 2026-09-05 — I-11 hardening suite + review

- Financial regression: `tests/test_financial_regression.py` locks V10.5 defaults (10%/20d/referral bps), floor `calculate_bps`, day-1 + L1 accrual, day-20 profit+principal, full-cycle 200% profit + principal, exact-100 USDT admin investment
- Security: `tests/test_security_hardening.py` — notification IDOR, bootstrap/team isolation, 12-route non-admin 403 matrix (no side effects), login-token replay, expired initData fail-closed, XSS allowlist vectors, documented session-over-initData behaviour
- Review verdict: **CONDITIONAL GO** (`_cursor_output/11_HARDENING_REVIEW.md`) — P0/P1 owner gates still open
- No yield / principal / referral-% / production changes
- pytest: **74 passed / 0 failed**

## 2026-09-05 — I-10 broadcast / notifications polish

- Composer preview renders the message the way Telegram will, using a JS mirror of `sanitize_telegram_html` (allowlist, safe-scheme links, literal quotes)
- Length counter after sanitizing + warning that a >1024 char caption arrives as two messages
- Audience recipient count (`GET /api/admin/broadcasts/audience`) and confirm dialog before any send
- Test send (`POST /api/admin/broadcasts/test`) queues a `system` notification to the acting admin only — no `broadcasts` row, so it can never reach an audience
- Retry undelivered (`POST /api/admin/broadcasts/{id}/retry`) requeues only `failed` deliveries; delivered recipients are never resent
- Broadcast list: localized audience, progress bar, delivered / failed / pending / total, last error
- `create_broadcast` and `broadcast_audience_counts` now share `BROADCAST_AUDIENCE_FILTERS`
- Sanitizing, worker and DB schema unchanged; no mass send performed
- New tests: `tests/test_broadcast_api.py`; pytest **40 passed / 0 failed**

## 2026-09-05 — I-09 wallet vs payout clarity

- User wallet: impact notice (profile vs frozen deposit/payout addresses) + open pipeline summary
- Confirm before changing an existing payout address (user + admin)
- History / assets / admin user card show the address that actually applies
- Admin Access tab: queued / signed / broadcast counts before wallet save/clear
- Backend payout/wallet semantics **unchanged** (owner cutover question still open)
- pytest: **30 passed / 0 failed**

## 2026-09-05 — I-08 harden V10.6 admin controls

- New API tests: `tests/test_admin_controls_api.py` (referral balance/level audit, investment idempotency + bad input, non-admin / invalid level / no-wallet)
- Additive validation only: `reason` strip+min length on balance / referral-balance / referral-level / open-investment; `operation_id` strip+min length on investments
- **Not done (owner gate):** clamp admin investment to deposit min/max; Idempotency-Key for balance/level mutations
- No yield / principal / referral-% / debit accounting changes
- pytest: **30 passed / 0 failed**

## 2026-09-05 — I-07 admin user card IA

- Admin user modal split into tabs: Overview / Investments / Payouts / Referral / Access / Audit
- Existing V10.6 controls kept (balance, referral balance/level, manual investment, wallet, inviter, block)
- Added confirm dialogs for balance / referral balance / level / clear wallet / block
- Tab preserved across in-modal saves; resets to Overview when opening from user list
- Frontend only; no API / financial semantics changes

## 2026-09-05 — I-06 deposit invoice UX

- Wallet deposit form: network chip (BEP-20 only), amount range hint, wallet gate before create
- Invoice card: status + TTL countdown, exact amount hero + tail hint, token/chain id, monospace address, RU copy toasts
- Error maps for wallet-required / too-many-pending invoices
- Fractional matching tail **preserved** (UI explains, does not remove)
- Frontend only; no API / formula / production changes

## 2026-09-05 — I-05 home / assets financial hierarchy

- Home hero: active principal + **next payout** (time + amount; notes principal return on final day)
- Position strip: **received** (confirmed) / **scheduled remaining** (projection, not withdrawable) / **partner available**
- Stats: deposited + internal balance (relabeled) + team — removed ambiguous “partner income” as top KPI
- Assets cards: paid / remaining / next payment rows; summary includes expected remaining
- Frontend-only; bootstrap fields reused; payout math mirrors `calculate_bps` (floor)
- No API / formula / production changes

## 2026-09-05 — I-03 design tokens + primitives

- Added `frontend/assets/design-tokens.css` (color/type/space/radius/elevation/touch + semantic aliases)
- Refactored `novera-brand.css` to consume tokens; primitives `.stack` / `.cluster` / `.surface` / `.eyebrow` / `.money` / `.touch-target`
- Viewport gutters/tuning for 430 / 390 / 360; home amounts marked `.money`
- Spec: `_cursor_output/03_DESIGN_TOKENS.md`
- No API / financial / production changes

## 2026-09-05 — I-04 session / account-switch hardening

- **Root cause of “Сессия устарела” after NOVERA rebrand:** Mini App sent `X-NOVERA-Session` / `X-NOVERA-Telegram-Context`, API only read `X-GFORT-*` → SecureStorage token never authenticated; native context flag was ignored → shared cookie / expired initData paths resurfaced
- `delta_backend/api.py`: accept both `X-NOVERA-*` and legacy `X-GFORT-*` session/context headers
- `frontend/assets/app.js`: send both header names; migrate/read/clear `novera_auth_session_v10` **and** legacy `gfort_auth_session_v10`; drop stored token when it conflicts with live initData; RU `accountMismatch` / clear session on 401/409; reload on live Telegram id change
- Test: `test_novera_session_header_authenticates_without_init_data` — **27 passed**
- No financial formula changes; production not contacted

## 2026-09-05 — I-01b baseline tests green (26/26)

- `delta_backend/telegram_auth.py`: `max_age_seconds=0` now disables the age check like `None` (production TTL still validated 60..86400 s)
- `delta_backend/api.py`: `_header_text()` / `_is_native_context()` helpers; `current_user` and `exchange_bot_login` no longer crash when header params are absent in direct calls (restores 409 on cross-account login token)
- `tests/test_api.py`: cookie-override test asserts the server `Set-Cookie … Max-Age=0` directive (httpx jar cannot match host-scoped deletion)
- `tests/test_repository.py`: referral idempotency test asserts `referral_accruals` (V8 on-demand model) instead of immediate referral `payouts`
- No financial formula / state machine changes; production not contacted

## 2026-09-05 — Official NOVERA logo wired

- Installed owner logo as `frontend/assets/brand/novera-logo.jpg` (+ archive in `_owner_inputs/BRAND_ASSETS`)
- Topbar mark and favicon now use the official circular logo
- Cache-bust `?v=novera-brand-2` / `novera-logo-1`

## 2026-09-05 — NOVERA brand reskin

- Applied NOVERA visual system: cyan/violet palette, Orbitron + Manrope, glowing panels
- Added `frontend/assets/novera-brand.css`, `frontend/assets/brand/novera-mark.{png,svg}`
- Renamed user-facing GFORT → NOVERA in Mini App + Telegram launcher copy
- Default example `bot_username` → `NoveraBot` (runtime secrets still authoritative)
- Financial formulas / payout engine / deploy paths unchanged
- Docs: `_owner_inputs/BRAND_ASSETS/NOVERA_BRAND.md`

## 2026-09-05 — I-01 local verify path

- Added `scripts/verify_workspace.ps1` (Windows compileall + pytest)
- Added `scripts/verify_in_docker.ps1` / `scripts/verify_in_docker.sh` (isolated verify without host Python)
- Documented commands in `_cursor_output/DEV_VERIFY.md`
- Updated `scripts/verify_workspace.sh` with Windows/Docker pointers
- Ran verify on Python 3.12.10: compileall PASS; pytest **22 passed / 4 failed** (see TEST_REPORT)
- No `delta_backend` / `frontend` logic changes; production not contacted
