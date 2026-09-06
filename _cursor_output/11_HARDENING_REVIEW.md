# I-11 — Hardening review verdict

**Date:** 2026-09-05  
**Verdict:** **CONDITIONAL GO**

This is a local candidate-tree review (not a production cutover). No secrets, deploy or live mass-send were performed.

## Summary

| Area | Result |
|------|--------|
| Financial golden amounts (V10.5 terms) | **PASS** — locked in `tests/test_financial_regression.py` |
| Admin non-admin 403 matrix (12 high-risk routes) | **PASS** — no side effects on reject |
| IDOR (notifications / bootstrap / team) | **PASS** — scoped to `current_user` |
| Login-token replay | **PASS** — second exchange → 401 |
| XSS allowlist (`sanitize_telegram_html`) | **PASS** — common vectors blocked |
| Full pytest | **74 passed / 0 failed** |
| Owner P0/P1 open business questions | **Still open** → blocks unconditional GO |
| Independent clean Cursor session | **This session** documents the verdict; a second human/owner pass is still recommended before I-12 |

## What was added

1. **Financial regression** — floor `calculate_bps`, default terms (10%/20d/L1–L5 %), day-1 + L1 accrual, day-20 profit+principal, full 20-day cycle, exact-100 USDT admin investment without invoice tail.
2. **Security hardening** — notification IDOR, bootstrap/team isolation, parameterized non-admin admin routes, session-vs-initData documented behaviour, expired initData fail-closed in native mode, one-time login replay, XSS vector matrix.

## Known accepted risks (not “fixed” in I-11)

| ID | Item | Why CONDITIONAL |
|----|------|-----------------|
| P0 | Manual investment = unpaid treasury liability | Owner policy; documented since baseline |
| P0 | Admin deposits participate in referral path | Owner policy |
| P1 | Admin investment bypasses deposit min/max | Deferred in I-08 (D-20) |
| P1 | Balance/level lack Idempotency-Key | Deferred in I-08 (D-20) |
| Auth | Valid SecureStorage session wins over conflicting initData | Intentional V10 WebView design; frontend I-04 drops token on live uid mismatch (D-26) |
| XSS | Notification title/body store raw text; Mini App uses `esc()` | Telegram HTML path is sanitized; Mini App DOM must keep escaping (D-27) |
| Open | Wallet cutover status (queued/signed/broadcast rewrite) | Still in `OPEN_BUSINESS_DECISIONS.md` |

## GO criteria for I-12

Unconditional GO requires, at minimum:

1. Written owner answers for P0 treasury/referral policy items.
2. Decision on admin investment min/max and balance/level idempotency.
3. Optional second clean-session review of the exact diff since baseline.
4. Explicit owner command before any production contact (I-12 hard stop).

Until then: **ship further candidate iterations (I-12 prep) locally only**.
