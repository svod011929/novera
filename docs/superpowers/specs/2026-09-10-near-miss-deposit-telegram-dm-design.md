# Near-miss депозит → Telegram DM — Дизайн

**Дата:** 2026-09-10  
**Статус:** Утверждён владельцем 2026-09-10  
**Продукт:** NOVERA Mini App / Telegram-бот  
**База:** `2026-09-09-unmatched-deposit-recovery-design.md` (UI mismatch_hint), `deposit_mismatch.py`

## Проблема

При переводе на treasury с суммой около заявки (±1 USDT / `base_minor`) Mini App уже показывает `amount_mismatch` при poll. Пользователь, который не открыл приложение, не получает сигнал в Telegram и может считать, что «деньги зависли».

## Зафиксированные решения

| Тема | Выбор |
|------|--------|
| Канал | **A:** только Telegram через `user_notifications` (без обязательного in-app центра) |
| Когда | **A:** сразу при записи нового unmatched `chain_deposit` (не duplicate) |
| Invoice | **A:** только `pending` (не expired) |
| Архитектура | **1:** хук в `apply_transfer` после unmatched commit + `select_mismatch_candidate` |

## Цели

1. Владелец подходящего pending invoice получает одно ЛС: ожидаемая vs фактическая сумма + призыв к точной сумме / поддержке.
2. Автозачисления нет; монитор по-прежнему матчит только exact pending.
3. Dedupe: не более одного уведомления на пару `(invoice_id, chain_deposit_id)`.

## Вне скоупа

- In-app notification center (можно позже тем же event_type).
- DM для recently expired invoices (UI hint +2ч остаётся read-only poll).
- Poll-triggered повторный DM.
- Смена `MISMATCH_AMOUNT_TOLERANCE_MINOR` / экономики хвоста.
- Изменение ops-chat unmatched алертов.

## Архитектура

```
apply_transfer: insert chain_deposit
  → нет pending exact match → unmatched
  → (после commit / в том же post-commit блоке, что ops unmatched)
  → загрузить pending invoices в time-window
  → select_mismatch_candidate(invoice, [this deposit]) для кандидатов
  → лучший invoice → _queue_notification(...)
```

Переиспользовать:
- `MISMATCH_LOOKBACK_SECONDS`, `MISMATCH_AMOUNT_TOLERANCE_MINOR`, `select_mismatch_candidate` из `deposit_mismatch.py`.
- Для reverse lookup (tx → invoices): выбрать pending invoices, у которых time-window содержит `chain_deposit.created_at` и amount near-miss к этому deposit; среди них — лучший по тем же sort-ключам, что в `select_mismatch_candidate` (ближе по времени к invoice.created_at, ближе по сумме к exact_minor, меньший id).

Реализация может:
- либо вызвать helper `find_pending_invoice_for_unmatched_deposit(deposit)` рядом с mismatch-модулем,
- либо inline SQL pending + filter через `_amount_matches` / `_in_time_window`.

Уведомление ставить **после** успешного commit unmatched (как ops schedule), либо `_queue_notification` внутри транзакции unmatched-ветки — главное: не при duplicate early-return и не при успешном match.

## Уведомление

| Поле | Значение |
|------|----------|
| category | `deposit` |
| event_type | `deposit_amount_mismatch` |
| title | `Сумма перевода не совпала` |
| body | краткий plain: ожидали X, в сети Y |
| telegram_html | см. шаблон ниже |
| dedupe_key | `deposit-mismatch:{invoice_id}:{chain_deposit_id}` |
| data | `{ "target_view": "wallet", "invoice_id": N, "chain_deposit_id": M }` |

**telegram_html:**
```
⚠️ <b>Сумма перевода не совпала</b>

Ожидали: <b>{expected} USDT</b>
В сети: <b>{observed} USDT</b>

Нужна точная сумма с хвостом из заявки.
Если уже отправили — напишите в поддержку.
```

`expected` = `minor_to_text(invoice.exact_minor)`, `observed` = `minor_to_text(chain_deposit.amount_minor)` (без trim, как в API mismatch).

## Критерии успеха

- Near-miss unmatched → одно Telegram-уведомление владельцу pending invoice без открытия Mini App.
- Exact match / сумма вне tolerance / duplicate → без mismatch DM.
- Повтор той же пары → dedupe.
- Expired-only → без DM в v1.
- Финансовый commit не зависит от доставки Telegram.

## Риски

| Риск | Смягчение |
|------|-----------|
| Несколько pending у разных юзеров подходят | Один лучший candidate; ops unmatched всё равно алертит оператора |
| Спам при серии wrong amounts | Dedupe на pair; один deposit → один invoice max |
| Расхождение с UI hint (expired) | Сознательно: DM строже (pending only) |

## Тесты

- Unmatched + pending ±1 → notification queued once.
- Far amount / exact paid path / duplicate → no mismatch notification.
- Second apply same pair → dedupe, still one row.
- Pending expired (status expired) → no DM.

---

**Self-review:** скоуп = один хук + reuse mismatch helper; без auto-credit; pending-only явный; плейсхолдеров нет.
