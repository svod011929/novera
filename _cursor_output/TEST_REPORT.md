# TEST_REPORT

## Payout gas price floor — 2026-09-10

- `python -m pytest -q` (Python 3.12, local) — **240 passed, 0 failed**
  (236 after PR #2 merge + 4 new gas-floor cases).
- Settings validation checked by hand: `PAYOUT_GAS_PRICE_FLOOR_WEI=-1` →
  `ValidationError "PAYOUT_GAS_PRICE_FLOOR_WEI не может быть отрицательным"`;
  `250000000` → accepted.
- PR #2 branch re-verified locally before merge: 236 passed (independent of the
  cloud run).
- Live validation of the incident path (manual, before this deploy): same-nonce
  replacements at 1 gwei for #39 (nonce 49), #41 (nonce 51) and a fresh
  nonce-52 transaction for #42 all mined within ~6 s; 0.05 gwei transactions
  had been pending 10+ minutes.

## Payout worker: delegated treasury + dropped-tx recovery — 2026-09-10

- `bash scripts/verify_workspace.sh` (compileall + `bash -n` + pytest) — PASS
- `python -m pytest -q` — **236 passed, 0 failed** (baseline on `main`
  a9a44a5: 211 passed; +25 new in `tests/test_payout_recovery.py`)
- Mutation check of the new tests (each mutation applied alone, then reverted):
  removing the delegated cap → 2 failures; removing the 3-pass streak → 2
  failures; classifying the delegated txpool messages as deterministic → 2
  failures; disabling the pending-nonce guard → 1 failure; failing while
  latest nonce == payout nonce → 5 failures. All caught.
- `ruff check` on touched files: no new rule categories versus `main`
  (pre-existing `BLE001`/`I001`/`ISC004` patterns only; new test file clean).
- Not performed: live RPC / VPS validation (no access by design); the delegated
  txpool behaviour is asserted through the recorded `-32000` messages.

## Branded bootstrap profiles + wizard — 2026-09-07/08

- `python -m pytest -q` — **99 passed, 1 failed**. The 1 failure
  (`test_repository.py::test_connect_rebrands_durable_notifications`, missing
  `telegram_html` key) pre-dates this change set (reproduced identically on the
  prior commit via `git stash`); unrelated to branding/installer work, left
  open as a separate known issue, not fixed here.
- Extended `tests/test_bootstrap_release.py` (stub `$APP_NAME`, BrandProfile
  wiring, profile fixtures) — all new assertions PASS.
- `scripts/build_bootstrap_installer.ps1 -BrandProfile novera` — PASS
  (round-trip, no secrets, hashes match manifest)
  → `NOVERA_BOOTSTRAP_INSTALLER_20260907-194204.sh` (pinned in README).
- Smoke brand `AURORA` (`smoke-demo`) — PASS: `APP_NAME`/defaults baked; index
  title/wordmark/tagline; design-token colors; `NOVERA_BOT_TOKEN_FILE` + payload
  marker unchanged. Smoke artifacts removed after check.
- Beginner wizard `scripts\make_branded_installer.ps1` — non-interactive smoke
  PASS (`SMOKEBOT` profile); advanced `-BrandProfile novera` path unaffected.
  Test-only profile/installer artifacts removed before commit.

## Decision pack + System wizard + admin idempotency — 2026-09-06

- `python -m pytest -q` — **91 passed, 0 failed**
- Tree-sitter parse: `frontend/assets/app.js` — PASS
- New coverage: referral-balance/level replay + conflict in `test_admin_controls_api.py`
- Full safe-update promote — PASS (`-Mode full`);
  release `/opt/gfort/releases/novera-update-20260906-104843`;
  `/ready` stayed `bootstrap` / `financial_ready=false`

## Master-plan follow-up (Stage 3/4 + responsive) — 2026-09-06

- `python -m pytest -q` — **91 passed, 0 failed**
- Tree-sitter parse: `frontend/assets/app.js` — PASS
- Live CDP responsive check on `bnbb.tech` at 360/390/430 (home / wallet / assets)
- Live frontend promote (`scripts/safe_update_remote.ps1 -Mode frontend`) — PASS;
  release `/opt/gfort/releases/novera-update-20260906-103153`; Caddy remount only;
  `/ready` stayed `bootstrap` / `financial_ready=false`

## Staged UX + safe-update — 2026-09-06

- `python -m pytest -q` — **91 passed, 0 failed**
- Tree-sitter parse: `app.js`, `safe-update.sh`, `post-update-check.sh`,
  `backup-rehearsal.sh` — PASS
- Live frontend promote (`scripts/safe_update_remote.ps1 -Mode frontend`) —
  PASS; release `/opt/gfort/releases/novera-update-20260906-100344`;
  delta image unchanged (no API blink); `/ready` stayed
  `bootstrap` / `financial_ready=false`
- Backup rehearsal — PASS (`integrity_check=ok`, sidecar absent as expected)
- SSH harden — PASS (`PermitRootLogin prohibit-password`,
  `PasswordAuthentication no`; cloud-init drop-in patched)
- Frontend Stage A/B changes are markup+i18n only (no financial formula edits)

## Ubuntu 26.04 installer fix + production bootstrap — 2026-09-06

- Reproduced on VPS: `install -d -o 10001 -g 10001` → `install: invalid user:
  '10001'` (uutils coreutils 0.8.0); `chown root:10001`, `mv -Tf`,
  `sha256sum -c`, `base64 -d`, `readlink -f` verified working
- Tree-sitter shell parse of stub/preflight/backup/restore — PASS
- `python -m pytest tests/test_bootstrap_release.py -q` — 4 passed
- `python -m pytest -q` — **90 passed, 0 failed**
- `scripts/build_bootstrap_installer.ps1` — PASS (round-trip verified)
- Installer end-to-end on `170.168.91.129`: base / clock (0 s) / DNS+ports /
  payload hashes / state / image build + compileall / HTTPS + `/ready`
  fail-closed check — all `[OK]`, exit 0
- Post-install: `/health` ok, `/ready` ready + `financial_ready=false`,
  Let's Encrypt cert issued, HTTP 308 → HTTPS, secrets 640 root:10001,
  0 world-writable entries in release tree, token temp file shredded,
  `System clock synchronized: yes`

## NOVERA secure bootstrap installer — 2026-09-05

Commands/checks:

- `python -m compileall -q delta_backend tests main.py` — PASS
- `python -m pytest -q --tb=short` — **90 passed, 0 failed**
- Tree-sitter JavaScript parse of `frontend/assets/app.js` — PASS
- Tree-sitter shell parse of installer/preflight/backup/restore — PASS
- `scripts/build_bootstrap_installer.ps1` — PASS
- Independent in-memory installer decode, payload SHA-256, critical per-file
  hashes, forbidden filename scan and token-shaped literal scan — PASS
  (**74 payload files**)
- IDE diagnostics on changed backend/frontend/tests — no errors

Coverage added:

- production bootstrap financial gates;
- immutable owner authorization and dynamic-admin denial;
- secret non-echo in validation/error/audit surfaces;
- public-only provider/metadata SSRF rejection;
- encrypted generation round-trip, tamper detection and rollback;
- startup degradation/quarantine and previous-generation recovery;
- scheduled/manual backup inclusion of encrypted active generation;
- fresh-install overwrite refusal and release builder safeguards.

Final artifact:

- `NOVERA_BOOTSTRAP_INSTALLER_20260905-220159.sh`
- installer SHA-256:
  `9bfe81db3eb67d37992b82ca6d6fc2ed4f033f4b35af3e2c87d44feb7c16d378`
- payload SHA-256:
  `5e30d59ee6499fff097e04a30a5c32a7031721ef351ede88ea5dbe86dfccb1aa`
- runtime secrets included: **no**
- production/VPS execution: **not performed**

The only test warning is the pre-existing third-party
`websockets.legacy` deprecation warning.

---

## I-12 — Release candidate — 2026-09-05

### Commands used

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release_candidate.ps1
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

### Results

| Check | Result |
|-------|--------|
| RC installer build | PASS |
| Payload extract (compose / Dockerfile / env example) | PASS |
| Secrets absent from payload | PASS |
| Critical hash round-trip (`api.py`) | PASS |
| `pytest -q` | **74 passed, 0 failed** |
| VPS preflight / live cutover / production install | **NOT PERFORMED** (hard stop) |

### Artifact

- `GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_20260905-210023.sh`
- SHA-256: `71c0ff4f4c23e7a611c45a3f0cd63e2b42043ba20f1f754dcfc37051e5ca9350`

### Acceptance (I-12)

- [x] Self-contained installer without embedded secrets
- [x] Hash verify + payload extract
- [x] Release notes + post-deploy checklist
- [x] Preflight/rollback documented (paper rehearsal; no live VPS)
- [x] Hard stop before production observed

---

## I-11 — Hardening suite + review — 2026-09-05

### Command used

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

### Results

| Check | Result |
|-------|--------|
| `pytest -q` | **74 passed, 0 failed** |
| Review verdict | **CONDITIONAL GO** → `_cursor_output/11_HARDENING_REVIEW.md` |
| Production / secrets / deploy | Not performed |

### New coverage

| Suite | What it locks |
|-------|----------------|
| `test_financial_regression.py` | `calculate_bps` floor; default terms; day-1 daily + L1 accrual; day-20 profit+principal; 20× daily = 200% profit; exact 100 USDT → 10 USDT/day |
| `test_security_hardening.py` | Notification IDOR; bootstrap/team isolation; non-admin 403 on 12 admin routes without side effects; session preferred over conflicting initData (documented); expired initData + foreign cookie → 401; login token replay → 401; XSS allowlist |

### Acceptance (I-11)

- [x] Financial schedule amounts pinned to V10.5 defaults
- [x] IDOR / non-admin / replay / XSS checks present
- [x] Written GO / CONDITIONAL GO / NO-GO verdict
- [x] No formula or production changes

---

## I-10 — Broadcast / notifications polish — 2026-09-05

### Command used

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m compileall -q delta_backend tests main.py
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

### Results

| Check | Result |
|-------|--------|
| `compileall` | PASS |
| `pytest -q` | **40 passed, 0 failed**, 1 deprecation warning (`websockets.legacy`, third-party) |
| Mass send to real users | **Not performed** (test send targets the acting admin only) |
| Production / secrets / deploy | Not performed |

### What changed

| Area | Change |
|------|--------|
| Composer | Telegram-style preview, length counter after sanitizing, caption-split warning, test-send button |
| Safety | Recipient count + confirm before send; send blocked when the audience is empty |
| Test send | `POST /api/admin/broadcasts/test` → `system` notification to the acting admin; no `broadcasts` row |
| Retry | `POST /api/admin/broadcasts/{id}/retry` requeues `failed` deliveries only |
| List | Localized audience, progress bar, delivered / failed / pending / total, last error |
| Repository | `broadcast_audience_counts`, `retry_broadcast`, `queue_broadcast_self_test`; shared `BROADCAST_AUDIENCE_FILTERS` |
| Unchanged | `sanitize_telegram_html`, broadcast worker, DB schema (no migration) |

### New tests (`tests/test_broadcast_api.py`)

| Test | Guarantee |
|------|-----------|
| `test_sanitize_telegram_html_contract` | Pins the allowlist contract the JS preview mirrors (unknown tag dropped, text kept; unsafe `href` dropped; quotes stay literal) |
| `test_broadcast_audience_counts_match_delivery_targets` | Reported counts equal what `create_broadcast` actually enqueues, per audience |
| `test_broadcast_test_send_reaches_only_the_acting_admin` | Test send creates no broadcast, queues one notification for the admin, none for other users; blank text → 422 |
| `test_broadcast_retry_requeues_only_failed_recipients` | Only failed deliveries requeue; the delivered recipient is never claimed again; unknown id → 404 |
| `test_broadcast_endpoints_reject_non_admin` | All three endpoints → 403 for a non-admin, with no notification side effect |

### Note on existing sanitizer behaviour (kept as-is)

`sanitize_telegram_html` drops a tag outside the allowlist but preserves its text
(`<div>Текст</div>` → `Текст`). That is pre-existing behaviour on the live broadcast
path, so I did not change it; instead the JS preview mirrors it and the contract test
pins it, so the operator sees exactly what recipients will get.

### Acceptance (I-10)

- [x] Operator sees the rendered message before sending
- [x] Recipient count and confirm dialog precede every send
- [x] Test send cannot reach anyone but the acting admin
- [x] Retry never resends to already-delivered recipients
- [x] Sanitized HTML pipeline preserved; no schema migration
- [x] No yield / principal / referral-% changes

---

## I-09 — Wallet vs payout clarity — 2026-09-05

### Command used

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

### Results

| Check | Result |
|-------|--------|
| `pytest -q` | **30 passed, 0 failed** (frontend-only change; suite smoke) |
| Production / secrets / deploy | Not performed |

### What changed

| Area | Change |
|------|--------|
| User wallet | Impact copy + open payout counts; confirm on address change |
| History / assets | Show deposit schedule address / payout address |
| Admin user card | Wallet hint + queued/signed/broadcast strip; confirm save/clear; addresses on deposit/payout rows |
| Backend | Unchanged — no rewrite of queued/signed/broadcast or deposit.payout_address |

### Current server truth (documented in UI, not altered)

- `users.payout_address` — profile; used for **new** deposits and **new** referral withdrawals
- `deposits.payout_address` — frozen at open; daily schedule copies from here
- `payouts.address` — frozen at payout creation; wallet change does not rewrite queued/signed/broadcast

### Acceptance (I-09)

- [x] User understands which address applies after a change
- [x] Admin sees open payout statuses before changing wallet
- [x] No backend cutover policy change without owner answer
- [x] No yield / principal / referral-% changes

---

## I-08 — Harden V10.6 admin controls — 2026-09-05

### Command used

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

### Results

| Check | Result |
|-------|--------|
| `pytest -q` | **30 passed, 0 failed**, 1 deprecation warning (`websockets.legacy`, third-party) |
| Production / secrets / deploy | Not performed |

### What changed

| Area | Change |
|------|--------|
| Tests | `tests/test_admin_controls_api.py` — referral balance/level audited; investment idempotent + rejects zero/blank reason/bad confirm; non-admin 403; level 9 rejected; investment without wallet rejected |
| API validation | `field_validator` strips `reason` (min 2 after strip) on balance / referral-balance / referral-level / open-investment; strips `operation_id` on investments |
| Deferred (owner) | Deposit min/max clamp for admin investment; Idempotency-Key for balance/level |

### Acceptance (I-08)

- [x] Double-submit safe for admin investments (`operation_id`)
- [x] Negative / zero / blank-reason / invalid level / non-admin rejected at API boundary
- [x] Audit fields present for referral balance + level mutations
- [x] No min/max policy or balance/level idempotency without owner confirm
- [x] No yield / principal / referral-% / debit accounting changes

---

## I-04 — Session / account-switch hardening — 2026-09-05

### Command used

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m compileall -q delta_backend tests main.py
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

### Results

| Check | Result |
|-------|--------|
| `compileall` | PASS |
| `pytest -q` | **27 passed, 0 failed** |
| Production / secrets / deploy | Not performed |

### What changed

| Area | Change |
|------|--------|
| API headers | `_client_session_token` / `_native_telegram_context` accept `X-NOVERA-*` and `X-GFORT-*` |
| Mini App headers | Sends both names on every API / session-exchange call |
| Storage keys | Reads/writes/clears `novera_auth_session_v10` + legacy `gfort_auth_session_v10` |
| Identity | Drops SecureStorage token when uid ≠ live initData; clears + RU banner on 401/409 mismatch |
| Test | New bootstrap auth via `X-NOVERA-Session` alone (native context, cookie deleted) |

### Acceptance (I-04)

- [x] Switching accounts cannot keep a conflicting stored session token
- [x] NOVERA session header authenticates (regression covered by pytest)
- [x] RU mode maps account-mismatch / session errors (no English toast for those paths)
- [x] No yield / principal / referral-% changes

---

## I-01b — Close baseline pytest failures — 2026-09-05

### Command used

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m compileall -q delta_backend tests main.py
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q
```

(`scripts/verify_workspace.ps1` resolves the same interpreter automatically; the bare `python` on PATH is the WindowsApps Store stub.)

### Results

| Check | Result |
|-------|--------|
| `compileall` delta_backend / tests / main.py | PASS |
| `pytest -q` | **26 passed, 0 failed**, 1 deprecation warning (`websockets.legacy`, third-party) |
| Production / secrets / deploy | Not performed |

### Fixes applied (no financial formula changes)

| Test | Root cause | Fix | Layer |
|------|-----------|-----|-------|
| `test_telegram_auth.py::test_signed_old_init_data_allowed_when_age_check_disabled` | `max_age_seconds=0` was treated as a zero-second TTL | `telegram_auth.validate_init_data`: `None` **or `0`** disables the age check. Production TTL is validated to 60..86400 s, so runtime behaviour is unchanged | code |
| `test_api.py::test_native_login_token_cannot_switch_telegram_account` | When a route is called directly, unset `Header(default=None)` params arrive as FastAPI `Header` objects → `'Header' object has no attribute 'strip'` | Added `_header_text()` / `_is_native_context()` in `api.py`; `current_user` and `exchange_bot_login` use them. Non-string header values are treated as absent. Expected 409 on cross-account token is now reached | code (defensive) |
| `test_api.py::test_current_telegram_init_data_overrides_shared_cookie` | Server **already** sends `delta_session=""; Max-Age=0` (verified with a probe). `httpx.Cookies.set()` stores the cookie with an empty domain, so the client jar cannot match the host-scoped deletion a real browser applies | Test asserts the `Set-Cookie` deletion directive instead of jar state | test |
| `test_repository.py::test_deposit_and_referral_payouts_are_idempotent` | Since V8 referral rewards accrue into `referral_accruals` and are withdrawn on demand; the fixture expected an immediate `payouts.kind='referral'` row | Test asserts one level-1 accrual for the referrer, zero direct referral payouts, and that a second `schedule_due_payouts()` adds nothing | test |

### Acceptance (I-01b)

- [x] Full green pytest on Windows host
- [x] No changes to yield / principal / referral-% / invoice semantics
- [x] No production, secrets or deploy contact

---

## I-01 — Local verify path — 2026-09-05

### Command used

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_workspace.ps1 -InstallDeps
```

Python: `C:\Users\svod0\AppData\Local\Programs\Python\Python312\python.exe` (3.12.10, installed via winget for this iteration)

### Results

| Check | Result |
|-------|--------|
| `compileall` delta_backend / tests / main.py | PASS |
| `bash -n` shell scripts | SKIPPED (no bash on host; Docker path covers this) |
| `pytest -q` | **4 failed, 22 passed**, 1 deprecation warning |
| Production / secrets / deploy | Not performed |

### Pytest failures (baseline discoveries — not fixed in I-01)

I-01 scope excludes `delta_backend` / `frontend` logic changes. Failures are recorded for a follow-up iteration.

| Test | Symptom | Likely cause |
|------|---------|--------------|
| `tests/test_telegram_auth.py::test_signed_old_init_data_allowed_when_age_check_disabled` | `TelegramAuthError: Telegram initData has expired` with `max_age_seconds=0` | Code treats `0` as zero TTL; test expects `0` to disable age check (`None` is the working disable today) |
| `tests/test_repository.py::test_deposit_and_referral_payouts_are_idempotent` | Expected 1 `payouts.kind='referral'`, got 0 | Scheduling now writes **`referral_accruals`**; referral `payouts` appear on withdraw. Fixture assertion likely stale vs accrual model |
| `tests/test_api.py::test_current_telegram_init_data_overrides_shared_cookie` | `delta_session` cookie still present | Session cookie not cleared when initData identity wins — aligns with known session-switch UX risk |
| `tests/test_api.py::test_native_login_token_cannot_switch_telegram_account` | `AttributeError: 'Header' object has no attribute 'strip'` (no 409) | Header handling bug when exchanging login token across accounts |

### Artifacts added this iteration

- `scripts/verify_workspace.ps1`
- `scripts/verify_in_docker.ps1`
- `scripts/verify_in_docker.sh`
- `_cursor_output/DEV_VERIFY.md`
- Pointers added in `scripts/verify_workspace.sh`

### Acceptance (I-01)

- [x] One documented Windows command runs compileall + pytest
- [x] Docker alternative documented (Docker not installed on this host yet)
- [x] Clear skip/failure reporting when tools missing or tests red
- [x] Full green pytest — closed by **I-01b** (see above)
