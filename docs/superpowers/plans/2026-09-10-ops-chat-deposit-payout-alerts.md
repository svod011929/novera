# Ops chat deposit/payout alerts — План реализации

> **For agentic workers:** Use executing-plans or implement inline. Steps use `- [ ]`.

**Goal:** HTML-уведомления о депозитах и подтверждённых выплатах в `OPS_CHAT_ID` (+ опциональный `OPS_TOPIC_ID`).

**Architecture:** `OpsChatNotifier` (aiogram Bot) + хуки после commit в repository; fire-and-forget; единый шаблон депозита без «админ».

**Tech Stack:** Python, aiogram Bot, pytest

**Spec:** `docs/superpowers/specs/2026-09-10-ops-chat-deposit-payout-alerts-design.md`

## Global Constraints

- `OPS_CHAT_ID` пуст → no-op
- Депозит: on-chain + recovery + admin open; без пометки админ
- Выплаты: все confirmed кроме admin_test; всегда explorer link
- Не ломать user_notifications / финансовые транзакции
- RU HTML templates as in spec

## Tasks

1. Format helpers + unit tests (`ops_chat.py`)
2. Settings `ops_chat_id` / `ops_topic_id` + LOG_CHANNEL fallback; `.env.example`
3. Wire notifier on lifespan; repository `_emit_ops_*` after commits
4. Hook apply_transfer, admin_match, admin_open_investment, mark_payout_confirmed
5. Verify pytest + deploy if owner asks

---
