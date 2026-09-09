# Promo deep-link + статус депозита — План реализации

> **For agentic workers:** Use executing-plans or implement inline. Steps use `- [ ]`.

**Goal:** Prefill промокода из `promo_*` start-param (bot + startapp) и живой статус invoice через HTTP polling.

**Architecture:** Парсер `promo_` рядом с `ref_`; `GET /api/deposits/invoice/{id}` read-only; клиент prefill + poll 6с; шаблон кампании со ссылкой `t.me/{{bot_username}}?start=promo_{{code}}`.

**Tech Stack:** Python/FastAPI/aiosqlite, vanilla Mini App JS, pytest

**Spec:** `docs/superpowers/specs/2026-09-09-promo-deeplink-deposit-status-design.md`

## Global Constraints

- Deep-link C: bot `start=promo_*` + `startapp` / `tgWebAppStartParam`
- Polling ~6с, пауза при hidden, стоп на credited/expired
- Redemption промо только при create/open депозита
- Не автосоздавать invoice из deep-link
- `ref_` и `promo_` взаимоисключающи в одном payload
- UI тексты RU (+ EN ключи)
- Commits только по запросу владельца

## File map

| File | Role |
|------|------|
| `delta_backend/promo_start.py` (или helpers в repository) | `parse_promo_start_param` |
| `delta_backend/repository.py` | `get_user_invoice_status`, campaign render `{{bot_username}}`, default template link |
| `delta_backend/api.py` | GET invoice; exchange returns `start_param`; dispatch passes bot_username |
| `frontend/assets/app.js` | prefill + poll UI |
| `frontend/index.html` | cache bump |
| `tests/test_promo_deeplink.py` | parse + invoice status + render |

---

### Task 1: parse_promo_start_param

- Create helpers + tests for `promo_CODE`, `promo-CODE`, reject empty/ref_

### Task 2: GET invoice status

- `repository.get_user_invoice(user_id, invoice_id) -> dict | None`
- API route ownership 404
- Tests paid/pending/foreign

### Task 3: Campaign template + bot_username

- Update `DEFAULT_PROMO_CAMPAIGN_MESSAGE` with link
- `render_campaign_message(..., bot_username=None)`
- `dispatch_campaign` passes business bot username

### Task 4: Session exchange + Mini App

- Exchange JSON includes `start_param`
- Client: resolve start_param once/session → wallet view + promo field
- Invoice poll + refresh + credited CTA

### Task 5: Verify + deploy

- pytest focused suite
- `safe_update_remote.ps1 -Mode full`
