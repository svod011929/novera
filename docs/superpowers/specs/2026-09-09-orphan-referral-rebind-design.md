# Orphan referral report + safe rebind — Design

**Date:** 2026-09-09  
**Status:** Approved 2026-09-09  
**Product:** NOVERA Mini App / Telegram bot  
**Related bug:** partners not attached for `https://t.me/NoveraBot?start=ref_967903658` (and same class of first-touch misses)

**Self-review (2026-09-09):** Scope is A+B ops script only; no UI; no reward backfill; first-touch deploy is explicit non-goal. Script path pinned below. No unresolved placeholders.

## Problem

`ensure_user` historically set `referrer_id` only on INSERT. Users who entered the DB without a referrer (e.g. `/stats`, Mini App without `start`) kept `referrer_id IS NULL` forever, even after later opening a `ref_*` link. Live evidence for user `967903658` shows almost no organic direct children; many recent users have `NULL` inviters.

A separate first-touch code fix stops **new** orphans. This design covers **existing** orphans: discover, prove where possible, rebind only with explicit confirmation.

## Goals

1. **Read-only report** from production DB listing users with `referrer_id IS NULL`, evidence of intended `ref_*` when available, and a focus slice for leader `967903658`.
2. **Safe batch rebind** only `NULL → referrer_id` after operator confirmation of an explicit list, using the same safety rules as `admin_set_user_referrer` (cycle/self checks, `referrer_adjustments` + admin audit). Historical referral rewards/accruals are **not** rewritten.

## Non-goals

- Auto-migrate all `NULL` referrers without evidence or confirmation.
- Overwrite a non-NULL `referrer_id`.
- Backfill or move historical partner payouts/accruals.
- New Mini App admin tab / UI (deferred unless this cleanup becomes recurring).
- Shipping the first-touch `ensure_user` + `/start` bind fix (tracked separately; should deploy soon so new orphans stop accumulating).

## Approach (A + B)

| Track | Rule |
|-------|------|
| **A — evidence-backed** | Auto-suggest (and eligible for apply) only when DB still holds a `ref_<id>` trace for that user. |
| **B — focus leader** | Same report always highlights rows whose suggested or claimed referrer is `967903658`; operator may confirm a focus list for that leader even when evidence is missing, but those rows require **manual list confirmation**, not blind apply-all. |

## Evidence sources

| Source | How used |
|--------|----------|
| `web_login_tokens.start_param` matching `ref_<digits>` for that `telegram_id` | Primary evidence (`evidence = token_ref`). Tokens may be expired but not yet purged, or still pending. |
| Consumed/deleted tokens | **No** reconstruction — treated as no evidence. |
| `referrer_adjustments` / `user_referrer_changed` audit | Context only (already-admin-changed); not used as proof of original click. |
| Partner verbal claim | Allowed only via explicit operator-supplied apply list (B), never inferred. |

If multiple tokens disagree on `ref_*` for the same user, mark `evidence = conflict` and **exclude** from suggested apply until operator picks one id.

## Report columns

One row per orphan user (`users.referrer_id IS NULL`):

| Column | Meaning |
|--------|---------|
| `user_id` | `telegram_id` |
| `username` | `@username` or empty |
| `first_name` | profile name |
| `created_at` | unix ts |
| `has_deposits` | boolean / count of deposits |
| `evidence` | `token_ref` \| `none` \| `conflict` |
| `suggested_referrer_id` | parsed from evidence, else null |
| `suggested_ok` | referrer exists, ≠ self, would not create cycle |
| `focus_967903658` | true if suggested (or operator focus filter) targets that leader |
| `apply_eligible` | `evidence ∈ {token_ref}` AND `suggested_ok` AND current referrer still NULL |

Output: CSV + JSON under `_cursor_output/` (local or copied from VPS). Script also prints summary counts: total orphans, with evidence, suggested_ok, focus slice, conflicts.

## Rebind rules

### Eligibility (hard)

1. Target user exists and `referrer_id IS NULL` at apply time (re-check in transaction).
2. New referrer exists and ≠ target.
3. No referral cycle (same walk as `admin_set_user_referrer`).
4. Prefer calling / sharing logic with `admin_set_user_referrer` so cycle checks and `referrer_adjustments` stay single-sourced.

### Apply modes

1. **`report`** — read-only; write CSV/JSON; no writes to users.
2. **`dry-run`** — given apply set, print would-be changes; no writes.
3. **`apply`** — requires explicit confirmation flag (e.g. `--confirm`) and one of:
   - `--from-suggested` — only rows with `apply_eligible` from a fresh report snapshot; or
   - `--from-file path.json` — explicit `{ "user_id": referrer_id, ... }` map (for B focus list and conflict resolutions).

### Audit

- Insert `referrer_adjustments` (`old_referrer_id` NULL, `new_referrer_id`, `changed_by` = operator admin telegram id or dedicated ops id).
- Admin event `user_referrer_changed` (same shape as UI path), with reason note `orphan_rebind` / `orphan_rebind_focus` in payload or reason field if available.
- Do **not** fire end-user “new partner” spam for bulk historical binds unless product later asks; optional single summary notification to focus leader is out of scope for v1.

### Money / structure semantics

Unchanged from existing admin inviter tool:

- Structure edge moves for future accruals only.
- Already-created `referral_rewards` / `referral_accruals` stay as historical ledger rows.

## Delivery

**Ops script** (Python, runs against the same SQLite the app uses, or via SSH one-shot on VPS):

- `scripts/orphan_referral_rebind.py` with subcommands `report` | `dry-run` | `apply`.
- No new HTTP surface in v1 (avoids accidental public batch mutation).
- Document exact VPS commands in `_cursor_output/` or script `--help`.

Optional later: admin UI “orphans” list — not in this design.

## Focus leader workflow (B)

1. Run `report` on VPS.
2. Filter `focus_967903658` and/or `apply_eligible`.
3. Operator reviews CSV; for no-evidence claims, builds explicit JSON map.
4. `dry-run` → approve → `apply --confirm`.
5. Spot-check team count for `967903658` in Mini App / admin partner stats.

## Success criteria

- Report runs without mutating DB.
- Every applied row had NULL before and non-NULL after; audit row exists.
- Zero applies for users who already had a referrer.
- Conflicts and no-evidence rows never enter `--from-suggested`.
- Tests cover: evidence parse, conflict exclusion, apply only NULL, cycle rejection, dry-run no write.

## Risks

| Risk | Mitigation |
|------|------------|
| Tokens already deleted → under-count evidence | Expected; B explicit list for known claims |
| Wrong manual JSON map | dry-run + `--confirm`; only NULL |
| Script points at wrong DB | Path from env / documented live path only |
| Concurrent first-touch bind during apply | Re-check NULL inside transaction; skip if taken |

## Open follow-ups (not this spec)

- Deploy first-touch `ensure_user` + `/start` referrer bind.
- Referral bind metrics (start with ref, bind ok/fail reasons).
- Merge long-lived feature branch naming cleanup.
