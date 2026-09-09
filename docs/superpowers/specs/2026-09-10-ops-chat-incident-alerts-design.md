# Ops-чат: инциденты + test ping — Дизайн

**Дата:** 2026-09-10  
**Статус:** Утверждён владельцем 2026-09-10  
**Продукт:** NOVERA Mini App / Telegram-бот  
**База:** `2026-09-10-ops-chat-deposit-payout-alerts-design.md` (+ admin DB settings)

## Проблема

Ops-чат уже показывает успешные депозиты и подтверждённые выплаты. Оператору всё ещё не хватает в той же ветке: проверки настройки (test ping), failed payouts, unmatched on-chain депозитов и safety-алертов (сейчас только ЛС админам).

## Зафиксированные решения

| Тема | Выбор |
|------|--------|
| Скоуп релиза | **A:** test ping + failed payout + unmatched + mirror safety |
| Safety destination | **A:** ЛС админам без изменений + дубль в ops-чат |
| Failed payout | **A:** только первый переход в `failed` (не шторм на ретраях); без `admin_test` |
| Unmatched | **A:** сразу при новой unmatched-записи (не duplicate) |
| Архитектура | **1:** расширить `OpsChatNotifier` (не отдельный notifier, не через Safety loop) |

## Цели

1. Кнопка теста в Админ → Система подтверждает chat/topic без реальных денег.
2. Первый failed payout и новый unmatched deposit появляются в ops-чате в том же стиле HTML.
3. Safety activate/recover дублируются в ops-чат тем же текстом, что в ЛС.
4. Сбой Telegram не откатывает финансы и не ломает safety-цикл.

## Вне скоупа

- Отключение или переписывание safety-текстов / circuit logic.
- Сводки unmatched раз в N минут.
- Near-miss-only фильтр для unmatched.
- Изменение пользовательских ЛС / in-app notifications.
- Алерты о «тишине» монитора депозитов (отдельный follow-up).

## Архитектура

```
mark_payout_failed (first fail, !admin_test)
apply_transfer unmatched (!duplicate)
SafetyMonitor._publish_transitions (activate/recover)
Admin POST /api/admin/ops-chat/test
        → OpsChatNotifier.notify_* / send_test (fire-and-forget или sync для test)
        → resolve target (DB → env) → bot.send_message
```

- Форматтеры + send живут в `delta_backend/services/ops_chat.py`.
- Repository хуки: `_schedule_ops_failed_payout`, `_schedule_ops_unmatched` после успешного commit (как депозит/выплата).
- `SafetyMonitor` получает ссылку на `OpsChatNotifier` при lifespan; после каждого `_send_admin` вызывает `notify_safety(html)` (ошибки только в лог).
- Admin test endpoint ждёт результат send и возвращает статус доставки (чтобы UI показал toast).

## Хуки и API

| Событие | Место | Условие |
|---------|--------|---------|
| Unmatched | `apply_transfer` | `duplicate=False` и `matched=False` |
| Failed payout | `mark_payout_failed` | `not was_failed` и `admin_test=0` |
| Safety | `_publish_transitions` | каждый activate/recover code |
| Test | `POST /api/admin/ops-chat/test` | admin; target `active` |

`GET/PUT /api/admin/ops-chat` без изменения контракта (кроме UI-кнопки теста).

Ответ теста (пример): `{ "ok": true, "chat_id": ..., "topic_id": ..., "source": "database" }` или `ok: false` + `detail` при ошибке Telegram / неактивном target.

## Шаблоны (HTML)

Юзер-строка и escape — как в базовом ops-чате.

**Test**
```
🧪 <b>Ops-чат: тест</b>
Источник: {source}
Chat: <code>{chat_id}</code>
Topic: <code>{topic_id|—}</code>
```

**Failed payout**
```
⚠️ <b>Выплата не прошла</b> · {kind_label}
👤 {user_line} · <code>{telegram_id}</code>
💰 Сумма: <b>{amount} USDT</b>
📦 Выплата #{payout_id}
❗️ {error_escaped_truncated}
```

**Unmatched deposit**
```
❓ <b>Несопоставленный депозит</b>
💰 Сумма: <b>{amount} USDT</b>
📦 Chain deposit #{chain_deposit_id}
🔗 <a href="{explorer_url}">Транзакция</a>
```

**Safety:** текст из существующего `SafetyMonitor._alert_text(code, recovered=...)` без изменений формулировок — только доставка в ops.

## Админ UI

На карточке «Ops-чат» (Система): кнопка «Отправить тест» рядом с «Сохранить».  
Требует активный target; при ошибке — toast с причиной. Cache-bust `app.js`.

## Критерии успеха

- Test ping виден в настроенной ветке при активных настройках.
- Первый failed и новый unmatched появляются в ops; повторный fail того же payout / duplicate tx — без второго алерта.
- Safety activate/recover — и в ЛС админам, и в ops.
- Без активного ops target — тишина (кроме ответа API теста с явной ошибкой).
- Финансовые commit и safety loop не зависят от доставки в Telegram.

## Риски

| Риск | Смягчение |
|------|-----------|
| Flood unmatched при спаме на treasury | Одно сообщение на chain_deposit; duplicate tx молчит |
| Дубль safety в ЛС + ops | Сознательный выбор владельца |
| Test endpoint abuse | Admin-only + mutation rate limit |
| Длинный last_error | Truncate ≤200 + html.escape |

## Тесты

- Форматтеры failed / unmatched / test (escape, truncate).
- Schedule failed только при first-fail и !admin_test.
- Schedule unmatched только для non-duplicate unmatched.
- Notifier no-op без chat_id.
- (Опционально) Safety publish вызывает ops notifier.

---

**Self-review:** скоуп = расширение OpsChatNotifier + 4 события; ЛС safety сохранены; first-fail / unmatched-on-insert явные; плейсхолдеров нет.
