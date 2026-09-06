# Responsive proof 360 / 390 / 430 — Stage A4 + master follow-up

Date: 2026-09-06
Method: live browser CDP on `https://bnbb.tech` (desktop Chrome Emulation) + CSS audit

## Live captures (pre-auth browser, session banner visible)

| Width | Views checked | Result |
|------:|---------------|--------|
| 360 | home | Brand wordmark readable; session recover CTA full-width stack; hero balance + next payout visible; no horizontal scroll |
| 390 | wallet/deposit | Payout address + Save touch row; BEP-20 deposit form; session CTA ≥44px |
| 430 | assets | Portfolio heading + empty assets path; session CTA; bottom nav active state |

## CSS guarantees in `novera-brand.css`

| Width | Rules |
|------:|-------|
| ≤520 | full `NOVERA` wordmark (override of styles.css 76px ellipsis) |
| ≤430 | primary/secondary/compact/nav/admin controls `min-height:44px` |
| ≤390 | action tiles / invoice actions / history status stack |
| ≤360 | hero subtitle / profile / session CTA single column |

## Markup / behaviour added in master follow-up

- Offline banner + retry; slow-network status after ~8s; API AbortController ~20s
- `aria-current="page"` on bottom nav; `:focus-visible` outlines; `prefers-reduced-motion`
- Admin owner model card + confirm remove; links preview + audit hint

## Manual Telegram WebView (owner)

- [ ] Telegram iOS/Android WebView at ~360/390/430 with real initData
- [ ] No horizontal scroll on home/team/history after auth
- [ ] Offline airplane-mode → banner → reconnect refresh
