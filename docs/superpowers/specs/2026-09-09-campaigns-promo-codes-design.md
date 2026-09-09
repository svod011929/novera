# Campaigns + promo codes — Design

**Date:** 2026-09-09  
**Status:** Approved (verbal); pending file review  
**Scope:** Unified admin «Кампании» module — promo codes with deposit principal bonuses + scheduled notification campaigns (promo / partner / custom)

## Problem

Operators need recurring engagement: push deposit promo codes with configurable bonuses, and periodic reminders about the partner program (and similar messages). Today only one-shot admin broadcasts exist; there is no promo-code or deposit-bonus machinery.

## Goals

- Admin can create/edit promo codes with **percent or fixed USDT** bonuses that **increase deposit principal** after on-chain payment.
- Shared codes: many users, **1 redemption per user**, **global activation limit**.
- Admin can create **scheduled campaigns** (interval **or** weekday+time UTC) that send via the existing broadcast delivery pipeline.
- Campaign types: `promo` (injects code/bonus into template), `partner`, `custom`.
- Single admin surface: **Кампании** (alongside existing one-shot **Рассылка**).

## Non-goals (v1)

- Per-user unique codes / personal coupons  
- Stacking multiple promos on one deposit  
- A/B testing, analytics dashboards beyond use counts  
- Changing `/api/team` or partner economics  
- Non-Telegram channels  
- Making the repository public or yield-marketing copy outside admin templates the operator writes

## Product rules

### Promo codes

| Field | Rule |
|--------|------|
| `code` | Unique, case-insensitive normalize (store uppercase) |
| `bonus_type` | `percent` \| `fixed` |
| `bonus_value` | Percent: bps or percent points (specify in plan: store as bps integer); Fixed: USDT minor units |
| `max_redemptions` | Global activation cap (≥1) |
| `per_user` | Always 1 (hard-coded v1) |
| `min_deposit_usdt` | Optional minimum base deposit |
| `valid_from` / `valid_until` | Optional unix timestamps |
| `enabled` | Soft disable without delete |

**Apply flow**

1. User enters promo on **create deposit / invoice** (Mini App).  
2. Validate: enabled, in window, under global limit, user has not redeemed, min deposit OK.  
3. Invoice `base_minor` / `exact_minor` remain the **cash** amount (no bonus in on-chain amount).  
4. Bind `promo_code_id` (or code) to the pending invoice.  
5. On successful transfer match → open deposit with  
   `principal_minor = paid_minor + bonus_minor`  
   where `bonus_minor` is computed from cash principal (invoice base / matched amount before jitter handling — plan must pin exact base: use confirmed matched `amount_minor` / invoice `base_minor` consistently).  
6. Record redemption tied to `user_id`, `promo_code_id`, `deposit_id`, `bonus_minor`.  
7. Referral accruals use the boosted principal (same as any deposit).

**Cancel / expire:** if invoice expires unused, no redemption row; promo slot not consumed. Redemption is committed only when deposit opens.

### Campaigns

| Field | Rule |
|--------|------|
| `kind` | `promo` \| `partner` \| `custom` |
| `audience` | `all` \| `investors` \| `partners` (reuse `BROADCAST_AUDIENCE_FILTERS`) |
| `schedule_mode` | `interval` \| `weekly` |
| `interval_hours` | When `interval` |
| `weekdays` + `time_utc` | When `weekly` (bitmask or JSON list of 0–6 + `HH:MM`) |
| `message_html` | Sanitized like broadcasts; placeholders for `promo`: `{{code}}`, `{{bonus_label}}` |
| `promo_code_id` | Required when `kind=promo` |
| `enabled` | On/off |
| `last_sent_at` / `next_run_at` | Worker bookkeeping |

**Worker**

- Background tick (same process as other services): find due enabled campaigns, create a normal `broadcast` row (or enqueue deliveries via existing `create_broadcast`), advance `next_run_at`.  
- `promo` campaigns: skip if linked code disabled, expired, or no remaining redemptions; log skip reason.  
- Do not bypass blocked-user exclusion.  
- Idempotency: one send per due window (`next_run_at` CAS / transaction).

Existing one-shot **Рассылка** UI stays; campaigns are additive.

## Admin UX

New tab **Кампании**:

1. **Промокоды** — list (code, type, value, used/max, enabled, validity); create/edit form; disable.  
2. **Кампании** — list (kind, audience, schedule summary, next run, enabled); create/edit; enable/disable; optional “run now” (admin-only, creates one broadcast).

## User UX

- Deposit form: optional promo field + inline validation message.  
- After apply: show effective principal preview (“Пополнение 100 → в работе 110”) before/after invoice create.  
- History/deposit card: show bonus if present (optional v1 polish — at least admin deposit detail).

## Data model (sketch)

```
promo_codes(
  id, code UNIQUE, bonus_type, bonus_value_minor_or_bps,
  max_redemptions, redemption_count, min_deposit_minor,
  valid_from, valid_until, enabled, created_by, created_at, updated_at
)

promo_redemptions(
  id, promo_code_id, user_id, deposit_id, invoice_id,
  bonus_minor, created_at,
  UNIQUE(promo_code_id, user_id)
)

campaigns(
  id, kind, audience, schedule_mode, interval_hours,
  weekdays_json, time_utc, message_html, promo_code_id NULL,
  enabled, last_sent_at, next_run_at, created_by, created_at, updated_at
)
```

Invoice/deposit: store `promo_code_id` nullable on `deposit_invoices` and/or `deposits`; store `bonus_minor` on deposit for audit.

## Security / money safety

- Admin-only CRUD and campaign control.  
- Promo validation server-side only (never trust client bonus math).  
- Race-safe redemption: transactional check `redemption_count < max` + unique `(promo, user)` under repository lock.  
- Bonus cannot make principal exceed any existing deposit max after boost — reject or clamp; **reject** preferred with clear error.  
- Safety / circuit breakers unchanged; campaigns respect deposit/payout feature flags if present.

## Testing

- Promo percent and fixed: principal = cash + bonus after confirm.  
- Second redeem by same user → reject; global limit exhausted → reject.  
- Expired / disabled code → reject; expired invoice does not consume.  
- Campaign interval and weekly: `next_run_at` advanced; creates broadcast audience correctly.  
- Promo campaign skip when code exhausted.  
- Concurrent double-submit does not double-redeem.

## Acceptance

1. Admin creates percent and fixed promos; users apply once; principal boosted after payment.  
2. Admin creates partner + promo campaigns on interval and weekly schedules; messages arrive via existing Telegram delivery.  
3. One-shot broadcasts still work.  
4. Tests cover redemption races and schedule tick.

## Open points for implementation plan

- Exact storage of percent (bps vs percent * 100).  
- Whether `bonus_minor` is computed from `base_minor` or matched `amount_minor` (recommend **invoice `base_minor`** so jitter does not change bonus).  
- Worker module placement (`delta_backend/services/campaigns.py`).
