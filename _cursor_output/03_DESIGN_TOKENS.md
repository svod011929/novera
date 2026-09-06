# I-03 — Design tokens & primitives

**Date:** 2026-09-05  
**Brand:** NOVERA  
**Files:** `frontend/assets/design-tokens.css`, `frontend/assets/novera-brand.css`, light hooks in `frontend/index.html`

## Token groups

| Group | Examples | Notes |
|-------|----------|-------|
| Color (semantic) | `--color-bg`, `--color-accent`, `--success` / `--danger` / `--warning` / `--info` | Legacy aliases `--bg`, `--accent`, `--green` kept for `styles.css` |
| Gradients | `--brand-gradient`, `--cta-gradient`, `--progress-gradient`, `--surface-gradient` | CTA / progress / surfaces |
| Type | `--font-display` (Orbitron), `--font-body` (Manrope), `--text-xs`…`--text-display` | Labels use `--tracking-label` |
| Space | `--space-1`…`--space-7` (4px base), `--page-gutter` | Gutter tightens at 430 / 390 / 360 |
| Radius | `--radius-sm/md/lg/xl/pill`, `--radius` | Panels use `--radius` |
| Elevation | `--shadow-sm/md/lg`, `--focus-ring`, `--glow-cyan/violet` | Focus rings shared |
| Motion | `--ease-out`, `--duration-fast/med` | Brand keeps 3 motions: drift, pulse, shimmer/scan |
| Touch | `--touch-min: 44px` | Primary / secondary / nav targets |

## Primitives (classes)

| Class | Role |
|-------|------|
| `.stack` / `.stack-sm` / `.stack-lg` | Vertical rhythm |
| `.cluster` / `.cluster-spread` | Horizontal wrap groups |
| `.surface` | Bordered elevated panel |
| `.eyebrow` | Display-font label (same role as `.overline`) |
| `.money` | Tabular numerals for amounts |
| `.touch-target` | Min 44×44 hit area |
| `.field-focus:focus-visible` | Shared focus ring |

## Viewport policy

CSS breakpoints in `novera-brand.css`: **430 / 390 / 360**. Live Telegram screenshots still pending owner capture (`_cursor_output/screenshots/` empty).

## Acceptance

- [x] One token file drives brand + semantic aliases
- [x] Home amounts use `.money`; brand layer consumes tokens (no new business copy)
- [x] Primary controls honor `--touch-min`
- [ ] Device screenshots 360/390/430 (owner / later visual pass)

## Out of scope (later iterations)

- Full rewrite of legacy `styles.css` orange leftovers (overridden by brand layer)
- Home financial hierarchy copy (I-05)
- Admin modal IA (I-07)
