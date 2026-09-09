# Уведомления о депозитах и выплатах в супергруппу — Дизайн

**Дата:** 2026-09-10  
**Статус:** Утверждён владельцем 2026-09-10  
**Продукт:** NOVERA Mini App / Telegram-бот  

## Проблема

Депозиты и выплаты сейчас уведомляют только пользователя в ЛС. Оператору нет живой ленты в супергруппе/ветке с username и ссылкой на tx выплаты.

## Зафиксированные решения

| Тема | Выбор |
|------|--------|
| Куда слать | **A:** `OPS_CHAT_ID` + опциональный `OPS_TOPIC_ID` (ветка форума) |
| Выплаты | **A:** все подтверждённые (дневные %, возврат тела, партнёрский вывод); без `admin_test` |
| Депозиты | **C:** on-chain + recovery match + ручное открытие админом |
| Вид депозита | Без пометки «админ» / recovery — единый шаблон «Новый депозит» |
| Архитектура | Отдельный `OpsChatNotifier` (не SafetyMonitor, не user_notifications) |

## Цели

1. В привязанный чат/ветку приходит красивое HTML-сообщение о каждом новом депозите и каждой подтверждённой выплате.
2. В тексте есть username (или fallback) пользователя.
3. В сообщениях о выплатах — кликабельная ссылка `block_explorer_tx_url` с хешем (формат как bscscan `/tx/0x…`).
4. Сбой Telegram не откатывает финансовую транзакцию.

## Вне скоупа (v1)

- Unmatched transfers без открытого депозита.
- Failed payouts в этот чат.
- Изменение пользовательских ЛС-уведомлений.
- Админ-UI редактирования шаблонов.
- Дублирование в ЛС `ADMIN_IDS` (опциональный follow-up).

## Конфиг

В `Settings` (`delta_backend/config.py`) и `.env.example`:

| Переменная | Смысл |
|------------|--------|
| `OPS_CHAT_ID` | ID супергруппы/канала; пусто = notifier выключен (no-op) |
| `OPS_TOPIC_ID` | Опциональный `message_thread_id` ветки; пусто = корень чата |

Fallback: если `OPS_CHAT_ID` пуст, но задан существующий `LOG_CHANNEL_ID` — использовать его как chat id (обратная совместимость мёртвого поля).

Бот должен быть админом чата с правом писать в выбранную ветку.

## Архитектура

```
успех депозита/выплаты (после commit денег)
        → schedule OpsChatNotifier.notify_* (fire-and-forget)
        → bot.send_message(OPS_CHAT_ID, html, message_thread_id=OPS_TOPIC_ID?)
```

- Новый модуль: `delta_backend/services/ops_chat.py` — форматирование + send.
- Инстанс на `app.state` при lifespan (рядом с bot token / aiogram bot или httpx Bot API — как у `SafetyMonitor` / notifications).
- Репозиторий **не** ждёт сеть внутри SQL-транзакции: вызов после успешного commit (или `asyncio.create_task` / callback, зарегистрированный снаружи), ошибки → `logger.exception`, без raise наружу.

Пользовательская очередь `user_notifications` **не** используется для ops.

## Хуки

| Событие | Место | Примечание |
|---------|--------|------------|
| On-chain депозит | `apply_transfer` после успешного match | есть `tx_hash` |
| Recovery match | `admin_match_chain_deposit` | есть `tx_hash`; шаблон как обычный депозит |
| Ручное открытие | `admin_open_investment` | без tx; шаблон без строки 🔗 |
| Выплата confirmed | `mark_payout_confirmed` | skip `admin_test`; всегда ссылка на tx |

## Шаблоны (HTML)

**Юзер-строка:** `@username` если есть; иначе `first_name`; иначе `ID {telegram_id}`. Все пользовательские поля через `html.escape`.

**Депозит:**
```
💎 <b>Новый депозит</b>
👤 {user_line} · <code>{telegram_id}</code>
💰 Сумма: <b>{amount} USDT</b>
📦 Депозит #{deposit_id}
```
Если есть `tx_hash`:
```
🔗 <a href="{explorer_url}">Транзакция</a>
```

**Выплата:**
```
💸 <b>Выплата</b> · {kind_label}
👤 {user_line} · <code>{telegram_id}</code>
💰 Сумма: <b>{amount} USDT</b>
🔗 <a href="{explorer_url}">{tx_short}</a>
```

`kind_label` (RU): дневная / возврат тела / партнёрский вывод (маппинг из kind payout).  
`explorer_url` = `settings.block_explorer_tx_url.replace("{tx_hash}", tx_hash)` (дефолт bscscan).

## Критерии успеха

- При заданном `OPS_CHAT_ID` (+ topic) сообщения появляются в нужной ветке.
- Депозит от монитора / recovery / admin open — один стиль, без слова «админ».
- Выплата содержит кликабельный bscscan-link с полным hash.
- Без `OPS_CHAT_ID` — тишина, финансы работают.
- Пользовательские ЛС без регрессии.

## Риски

| Риск | Смягчение |
|------|-----------|
| Бот не админ / нет прав на topic | Лог ошибки; документ в README/.env.example |
| Flood Telegram | Одно сообщение на событие; без ретраев-шторма в v1 |
| Утечка «админ открыл» | Единый шаблон депозита |

## Тесты

- Форматирование deposit с/без tx; payout с explorer URL.
- Notifier no-op при пустом chat id.
- Маппинг kind → label.
- (Опционально) mock send_message получил `message_thread_id`.

---

**Self-review:** Скоуп = ops chat notifier + hooks; без user DM изменений; админ-депозит маскируется; плейсхолдеров нет.
