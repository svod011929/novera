# Admin partner stats & partner turnover — Design

**Date:** 2026-09-08  
**Status:** Approved  
**Scope:** Admin Mini App user card only (no user-facing Team changes)

## Problem

Admins open a user and see partner count plus a bare list (name / username / id / date). They cannot see that user’s partner-program summary or each direct partner’s personal and structure turnover.

## Goals

- In **Admin → user → «Партнёрка»**, show a read-only partner summary for the selected user.
- For each **direct** partner, show **personal turnover** and **structure turnover**.
- Keep existing referral controls (balance, level override) on the same tab.
- Admin-only; reuse existing `GET /api/admin/users/{id}`.

## Non-goals

- Changes to the user «Команда» screen or `/api/team`.
- Separate admin leaderboard / Partners tab.
- CSV/export.
- Rewriting historical referral accruals.

## Definitions

| Metric | Meaning |
|--------|---------|
| **Personal turnover** (partner) | `SUM(principal_minor)` of **all** deposits for that partner (`user_id = partner`). Any deposit status. |
| **Structure turnover** (partner) | `SUM(principal_minor)` of **all** deposits for users in that partner’s downline tree **levels 1–5** (referrer chain under the partner). **Excludes** the partner’s own deposits. |
| **User partner summary** | Same fields as user Team stats where practical: referral income, today, available, personal active investments, L1 active line (qualification `line_minor`), team count, unlocked levels. |

Tree depth matches existing `team()` recursion: max depth **5**.

## UX

**Location:** existing user modal, tab `referral` («Партнёрка»).

**Above controls:** compact summary block:

- Referral income (earned)
- Today
- Available to withdraw
- Personal (active) investments
- L1 line turnover (qualification definition: active deposits of direct referrals)
- In team / levels unlocked

**Partners list** (replaces name-only cards):

- Display name, `@username`, Telegram ID, joined date
- Personal turnover (USDT)
- Structure turnover (USDT)
- Structure member count (optional but included)
- Sort: structure turnover descending, then personal descending
- Limit: 100 (same order of magnitude as today)
- Tap partner → open that user’s admin card (`openAdminUser(partner.telegram_id)`)

i18n: add RU/EN keys used by admin modal (other locales may fall back to EN/RU patterns already used in admin strings).

## API / data

Extend `Repository.admin_user_detail(user_id)` return value:

```json
{
  "partner_stats": {
    "earned_minor": 0,
    "today_minor": 0,
    "available_minor": 0,
    "personal_minor": 0,
    "line_minor": 0,
    "team_count": 0,
    "current_level": 0,
    "levels_total": 5
  },
  "partners": [
    {
      "telegram_id": 0,
      "username": null,
      "first_name": null,
      "created_at": 0,
      "personal_turnover_minor": 0,
      "structure_turnover_minor": 0,
      "structure_member_count": 0,
      "deposit_count": 0
    }
  ]
}
```

- Prefer reusing logic from `team()` for `partner_stats` (call `team(user_id)` or extract shared helper) so numbers match what the user sees.
- Enrich `partners` with turnover queries; do not leave name-only rows.
- No new HTTP routes; `GET /api/admin/users/{id}` already returns `admin_user_detail` payload.

## Performance

- One recursive CTE (or batched equivalent) for all direct partners’ trees is preferred over N per-partner full scans when partner count is large.
- Cap partners at 100.
- Acceptable latency: same order as current user detail open (&lt; ~1–2s on typical DB).

## Security

- Unchanged: admin session / admin gate only.
- No extra PII beyond what admin already sees.

## Testing

- Repository test: build a small tree (user → L1 partners → deeper), open deposits, assert `partner_stats` and per-partner `personal_turnover_minor` / `structure_turnover_minor` / `structure_member_count`.
- API smoke (existing admin detail test): response includes `partner_stats` and enriched `partners` keys.
- Structure turnover must **not** include the partner’s own principal.

## Acceptance

1. Admin opens user with partners → «Партнёрка» shows summary + list with both turnovers.
2. Numbers for personal / structure match the definitions above.
3. Clicking a partner opens that user’s card.
4. User Team UI unchanged.
5. Existing admin referral controls still work.
