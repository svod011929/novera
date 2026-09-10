# DECISIONS — conservative assumptions

**Date:** 2026-09-05  
Recorded during Stage 0. Owner can override in writing.

| ID | Assumption | Rationale |
|----|------------|-----------|
| D-01 | Work only in local candidate tree; never production | START_HERE / safety rule |
| D-02 | Preserve all financial formulas and state machines exactly as in V10.6 code | Immutable zone until written owner decision |
| D-03 | Manual level override unlocks **qualification only** for future accruals (current code) | Matches repository `_qualification` short-circuit; OPEN_BUSINESS question remains |
| D-04 | Invoice unique fractional tail stays required | Owner known constraint |
| D-05 | First implementation iterations will be UX/session/dev-env, not new admin financial features | V10.6 controls already present; priorities put safety + UX first |
| D-06 | P0 risks on manual investment (treasury liability + referral path) are documented, not “fixed” by silently changing economics | Needs owner policy |
| D-07 | On Windows host without Python/bash, Stage 0 proofs use PowerShell SHA-256 + static code review | Environment limitation; full pytest later in Linux/Docker |
| D-08 | Russian is the primary complete locale; other locales may lag | MASTER_PLAN Telegram-first RU requirement |
| D-09 | Coding of `delta_backend` / `frontend` waits for owner confirmation of a specific iteration ID | MASTER_PLAN coding gate |
| D-10 | `_reference/**` remains read-only | AGENTS.md |
| D-11 | I-01 may install local Python via winget to enable verify; still no production / secrets | Owner confirmed iteration `01` |
| D-12 | I-01 does not silently “fix” failing financial/auth tests by changing product semantics; failures are reported for a follow-up ID | Keep verify path honest |
| D-13 | Public brand is **NOVERA**; technical package/deploy/session keys stay compatible (`delta_backend`, `/opt/gfort`, legacy `gfort_lang`) | Owner brand request; Safe Deploy layout preserved |
| D-14 | Marketing terms on brand board (10%/20d/partner %) match current code defaults; no formula change was required for rebrand | Align UI copy with existing invariants |
| D-15 | `validate_init_data(max_age_seconds=0)` means "age check disabled" (same as `None`) | Test contract; production TTL is range-validated so `0` never reaches runtime |
| D-16 | Where a red test asserted a stale product model (referral `payouts` vs V8 `referral_accruals`) or a client-jar artifact, the **test** was aligned to verified server behaviour, not the code | Keep financial semantics immutable (D-02) |
| D-17 | Auth wire headers accept **both** `X-NOVERA-*` and legacy `X-GFORT-*`; Mini App sends both | Rebrand broke SecureStorage auth when only NOVERA names were sent |
| D-18 | On live initData uid vs stored session token conflict, **drop the token** (prefer fresh Telegram identity) | Prevents ledger bleed after account switch; SecureStorage should already be per-user |
| D-19 | Design tokens live in `design-tokens.css`; `novera-brand.css` is the visual layer; legacy `styles.css` structure kept | Avoid risky full CSS rewrite; brand overrides win |
| D-20 | Admin open-investment still does **not** clamp to deposit min/max (owner policy). Balance/level **now** require `Idempotency-Key` (2026-09-06) | Min/max clamp still needs written owner policy; idempotency is safe hardening without formula change |
| D-36 | Owner decision pack documents as-implemented answers without changing economics; activation remains owner-only in Mini App System tab | Unblocks Stage 5 triage without silent financial changes |
| D-21 | I-08 may add strip/min-length validators on admin `reason` / `operation_id` only | Additive input hygiene; no financial formula or debit semantics change |
| D-22 | I-09 documents current wallet cutover in UI only: profile change does **not** rewrite `deposits.payout_address` or existing `payouts.address` (queued/signed/broadcast) | Matches code today; owner still must answer OPEN_BUSINESS cutover status before any backend policy change |
| D-23 | I-10 test send is a `system` **notification to the acting admin**, not a `broadcasts` row with a new audience value | `broadcasts.audience` has a SQL CHECK constraint; a new value would need a table rebuild. This path needs no migration and structurally cannot reach real users |
| D-24 | `sanitize_telegram_html` keeps the text of tags outside the allowlist (`<div>x</div>` → `x`); I-10 mirrors this in the preview instead of changing it | Pre-existing behaviour on the live broadcast path; admin-authored input only, so it is a copy concern, not a security one (D-02) |
| D-25 | Broadcast retry requeues only `status = 'failed'` deliveries | Already-delivered recipients must never receive a duplicate message |
| D-26 | Valid SecureStorage/session token wins over conflicting initData on the server (documented in I-11) | Matches V10 WebView design; frontend I-04 drops the token when live initData uid conflicts |
| D-27 | Notification Mini App title/body may contain raw markup; DOM rendering must keep using `esc()` | Telegram HTML delivery is sanitized separately; do not switch notification cards to unsanitized `innerHTML` |
| D-28 | I-12 RC installer is built from the V10.6 Safe Deploy stub with patched NOVERA smoke checks and updated critical hashes; production install remains blocked until a separate owner command | MASTER_PLAN Stage 5 / START_HERE hard stop; CONDITIONAL GO from I-11 still applies |
| D-29 | Fresh production may run its web/control plane without RPC/WSS/seed, but every liability-creating route remains locked until setup state is `active` and `financial_ready` | Allows owner configuration through Mini App without making bootstrap financially live |
| D-30 | `OWNER_IDS` is immutable runtime configuration; dynamic DB admins may operate existing admin tools but cannot change signer/config generation, activate chain or manage administrator grants | Prevents delegated admins from taking over production control |
| D-31 | Runtime RPC/WSS/seed use one authenticated AES-256-GCM generation; SQLite stores only setup metadata and audit reason fingerprints | Atomic activation/rollback and secret non-echo are stronger than separate plaintext files |
| D-32 | Normal backups include database plus encrypted active generation, while the master key is backed up separately | Putting ciphertext and its key in the same routine backup would defeat encryption at rest |
| D-33 | The accepted deliverable is a verified installer artifact only; it is not automatically executed against the production VPS | User requested a file and later in-app configuration; live deployment remains a separate action |
| D-34 | Production bootstrap executed 2026-09-06 over SSH after the owner explicitly requested it and supplied the key and token; the owner chose to keep the chat-exposed bot token | Owner instruction supersedes D-33 for this run; token rotation path documented (BotFather `/revoke` → replace `secrets/bot_token.txt` → restart `delta`) |
| D-35 | Installer creates the state tree with `mkdir`/`chown`/`chmod` instead of `install -o/-g`, normalises payload modes, and fails closed on clock skew > 120 s | Ubuntu 26.04 uutils rejects numeric IDs; Windows-built tar ships 0666/0777; Telegram auth rejects `auth_date` ahead of a slow server clock |
| D-37 | A `broadcast` payout is auto-failed only when the on-chain nonce moved past it **and** its hash (plus any gas-bump predecessors) is unknown to every RPC endpoint on 3 consecutive passes; an RPC error during the lookup skips the tick instead of counting | Load-balanced RPC pools lag; a wrongly failed row + admin retry would be a double payment. The failure text tells the admin to verify the nonce on BscScan first |
| D-38 | Same-nonce gas bump (D) writes the replacement to the row **before** sending it, keeps the old hash in `replaced_tx_hashes`, and is capped at 3 bumps spaced `safety_payout_stuck_seconds/2` apart | A crash between send and write would otherwise leave an unknown live transaction; the DB-first order can only leave a recorded-but-unsent replacement, which the next pass rebroadcasts |
| D-39 | New payouts keep taking the nonce from the RPC pending count (nonce flow unchanged); the worker only adds a pause when an in-flight row already holds a nonce ≥ pending, and delegated treasuries sign one payout at a time | `.cursor/rules/gfort-safety.mdc` treats the nonce flow as immutable; both additions are conservative pauses, not a new nonce controller |
