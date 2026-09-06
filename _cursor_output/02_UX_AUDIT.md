# GFORT Stage 1 — UX Audit Backlog

**Date:** 2026-09-05  
**Basis:** Static review of `frontend/index.html`, `assets/app.js`, `assets/styles.css` + owner known bugs  
**Note:** No live Telegram WebView screenshots in this workspace yet (`_owner_inputs/DESIGN_REFERENCES` empty). Visual claims below are code-derived; confirm on device before treating as closed.

## Design system snapshot (current)

| Token area | Current state | Gap |
|------------|---------------|-----|
| Colors | Dark palette via `:root` CSS vars (accent orange) | Semantic names incomplete (`--success` vs `--green`); hard-coded rgba scattered |
| Typography | Inter / system stack | MASTER_PLAN wants purposeful brand fonts; Inter is default-ish |
| Spacing / radii | Partial vars (`--radius`); many magic numbers | Need 4/8/12/16/24 scale |
| Components | Repeated `.panel`, `.list-card`, `.primary-btn` | No shared JS components; admin modal is one long HTML string |
| Motion | Minimal transitions on inputs/toast | Need 2–3 intentional motions later |
| A11y | Some `role="dialog"`, `aria-live` on toast | Nav labels tiny (8px); color-only tags; focus rings weak |
| Touch | Many controls ≥42–54px; some admin actions 8–10px padding | Admin chips / nav labels at risk &lt;44px |
| Breakpoints | polish `@media max-width 420/350`, `min-width 600` | Explicit 360/390/430 checklist not proven |

## User screens

### Home — P1 → **I-05 mitigated 2026-09-05**
- **Now:** Hero active principal + next payout; position strip received / projected / partner available; secondary stats deposited / internal / team.
- **Issues:** Live screenshots still pending.
- **AC:** In ≤5s user sees available/active/next payout distinctly; projected never labeled as withdrawable; RU only in RU mode; 360px no overlap.

### Assets — P1 → **I-05 mitigated 2026-09-05**
- **Now:** Summary + cards with paid / remaining / next payment labels.
- **Issues:** Device confirm pending.
- **AC:** Every amount labeled; one money format; next payment datetime visible on active cards.

### Wallet / deposit — P1 → **I-06 mitigated 2026-09-05**
- **Now:** Network chip; exact-amount hero + tail hint; status/TTL; token/chain; gated create without payout wallet; RU copy toasts.
- **Issues:** Live Telegram WebView confirm pending; deposits still require chain enabled server-side.
- **AC:** User cannot confuse network/address/exact amount; copy feedback always RU; TTL/status visible; tail preserved.

### History — P2
- **Now:** Segmented filters + list with tx links.
- **Issues:** Failure/waiting reasons may surface raw/technical strings; filters limited.
- **AC:** Each row explains status + whether user action needed; RU reasons.

### Team / partner — P1
- **Now:** Link, levels, withdraw, members; shows manual vs organic levels from API.
- **Issues:** Manual access must not look like guaranteed payout (copy exists but hierarchy can bury it); withdraw vs available vs pending clarity.
- **AC:** Source auto/manual explicit; available ≠ pending ≠ failed; withdraw disabled states explained in RU.

### Profile / notifications — P2
- **Now:** Profile details + language; notification list with categories.
- **Issues:** Notification deep-links / retry UX; unread prominence.
- **AC:** Categories localized; tap opens target view; empty/error RU.

### Session / auth — P0 (owner known) → **I-04 mitigated 2026-09-05**
- **Now:** Session banner; `verifyBootstrapIdentity`; reload on account switch; SecureStorage session; **dual `X-NOVERA-*` + `X-GFORT-*` headers**; legacy storage key migration.
- **Issues:** Device confirmation still pending in real Telegram WebView.
- **AC:** Account A never sees account B balances; RU mode never shows English system popup for session expiry; recovery path one clear CTA.

## Admin screens

### Overview / dashboard — P1
- **Now:** Metrics + deposited/paid/net cards.
- **Gaps vs MASTER_PLAN:** Weak treasury/safety/stuck-ops/freshness clock on overview; safety lives under system/treasury tabs.
- **AC:** Read-only dashboard shows treasury/safety/queues/stuck + last refresh time.

### Users + user modal — P1 → **I-07 mitigated 2026-09-05**
- **Now:** Tabbed sheet — Overview / Investments / Payouts / Referral / Access / Audit; V10.6 controls retained; confirm+reason on money mutations.
- **Issues:** Device confirm pending; pagination/filters still basic list search.
- **AC:** Tasks in 2–4 steps; reason+confirm for money mutations; before/after via reload; history under Audit.

### Payouts / deposits / treasury / safety — P1
- **Now:** Lists + retry; treasury test payout; system safety cards.
- **Issues:** Age-of-status, RPC error clarity, reconcile guidance may be thin for operators.
- **AC:** Operator understands why stuck and what is safe to retry without double-sign.

### Broadcasts — P2
- **Now:** Audience, HTML message, media, buttons fields exist.
- **Gaps:** Preview/test-send/premium emoji polish incomplete vs owner ask.
- **AC:** Preview matches send; audience confirmation; no secrets in logs.

### Admins / terms / links — P2
- **Now:** Grant/remove; terms/links editors.
- **AC:** Last bootstrap owner protected (backend); UI explains protected source; link/text edits audited.

## Cross-cutting backlog (priority)

| ID | Sev | Item | Acceptance |
|----|-----|------|------------|
| UX-01 | P0 | Session / account switch | No cross-user data; RU session messages |
| UX-02 | P1 | Design tokens + reusable classes | **I-03 done** — `design-tokens.css` + primitives; live screenshots still open |
| UX-03 | P1 | Home financial hierarchy | **I-05 done** — active / next / received / projected / partner available |
| UX-04 | P1 | Deposit invoice clarity | **I-06 done** — network/amount/address/TTL/tail hint; matching tail unchanged |
| UX-05 | P1 | Admin user card IA | **I-07 done** — tabbed IA; confirm+reason on money ops |
| UX-06 | P1 | Admin dashboard safety/queues | Stuck + freshness visible |
| UX-07 | P2 | RU completeness pass | toast/modal/validation/empty/error/offline |
| UX-08 | P2 | 360/390/430 screenshot suite | No overlap/cut-off; ≥44px primary targets |
| UX-09 | P2 | Broadcast preview/test | Owner requirements without production sends |
| UX-10 | P3 | Brand typography/motion | After tokens; non-blocking |

## Recommended Stage 1→2 path

1. Finish device screenshots into `_owner_inputs/DESIGN_REFERENCES` (owner) or local capture after I-01.
2. Owner confirms coding start: **I-03 tokens** and/or **I-04 session** (see `01_IMPLEMENTATION_PLAN.md`).
3. Defer financial admin control behavior changes until P0 treasury policy answers.

## Stage 1 status

- [x] Inventory user + admin screens (this file)
- [x] Prioritized P0–P3 backlog with AC
- [ ] Live responsive visual proof 360/390/430 (CSS+markup done 2026-09-06; device screenshots owner-side — see `RESPONSIVE_PROOF_360_390_430.md`)
- [x] Token spec document / component list (starts with coding iteration I-03)
