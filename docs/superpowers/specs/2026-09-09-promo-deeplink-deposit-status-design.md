# Deep-link промокода + живой статус депозита — Дизайн

**Дата:** 2026-09-09  
**Статус:** Утверждён владельцем 2026-09-09  
**Продукт:** NOVERA Mini App / Telegram-бот  
**Зафиксированные решения:** Deep-link путь **C** (бот `start=promo_*` + Mini App `startapp` / `tgWebAppStartParam`); статус депозита через **HTTP-polling** (не WebSocket).

## Проблема

1. Промо-кампании сообщают код, но пользователь должен сам открыть приложение и ввести его — лишнее трение и опечатки.
2. После создания invoice UI только считает TTL. Не видно, нашла ли сеть перевод, пока пользователь не уйдёт в «Активы».

## Цели

1. Открытие NOVERA по `promo_CODE` заполняет поле промокода на депозите, открывает вкладку пополнения и даёт понятный фидбек, если код невалиден — **без** списания redemption до создания invoice (денежные правила не меняются).
2. Пока invoice в статусе `pending`, Mini App опрашивает статус и показывает цепочку: ждём перевод → ищем в сети → зачислено / истекло.
3. Дефолтный шаблон promo-кампании содержит ссылку/кнопку бота вида `start=promo_{{code}}`.

## Вне скоупа (v1)

- Автосоздание invoice из deep-link без суммы.
- WebSocket / SSE для событий депозита.
- Смена дробного хвоста или экономики депозита.
- Одновременные `ref_` и `promo_` в одном `start_param`.
- Отдельный админ-UI для текста deep-link сверх шаблона кампании.

## Deep-link (путь C)

### Форматы

| Вход | Пример | Заметки |
|------|--------|---------|
| Бот `/start` | `https://t.me/<bot>?start=promo_WELCOME10` | Основной путь для кнопок кампаний |
| Mini App startapp | `https://t.me/<bot>/<app>?startapp=promo_WELCOME10` | Запасной / прямой вход в Mini App |
| WebApp | `Telegram.WebApp.initDataUnsafe.start_param` | Тот же payload после открытия |

Также принимаем `promo-CODE` (дефис) и нормализуем тем же парсером.

### Правила разбора

- Префикс `promo_` или `promo-` (префикс без учёта регистра; **тело кода** — через существующий `_normalize_promo_code`, uppercase).
- Длина/алфавит кода — как у CRUD промо (макс. 32 после нормализации).
- Если payload `ref_<id>` — реферальный путь без изменений; промо не трогаем.
- Один токен: если строка начинается с `ref_` — рефка; иначе при `promo_` / `promo-` — промо.

### Поведение клиента

1. Берём start param по порядку: login-token / session `start_param` → `initDataUnsafe.start_param` → query URL, если есть.
2. При детекции промо: вкладка **Пополнить**; `#depositPromoCode` заполнен; мягкая валидация (предпочтительно без нового endpoint, если ошибки create-invoice уже понятны; опциональный лёгкий `GET` validate удобнее для toast до ввода суммы).
3. Toast: применён / недействителен / уже использован — через существующие i18n-ключи где возможно.
4. Не затирать поле, если пользователь уже ввёл другой код вручную, кроме свежего deep-link на этот заход в сессию.

### Сервер / launcher

- `/start promo_*`: `ensure_user` **без** трактовки как реферера; полный `start_param` кладётся в login token (уже умеем для произвольного start).
- Auth `ensure_user` по-прежнему берёт реферера только из `ref_*`.
- Дефолтный HTML promo-кампании: ссылка или кнопка  
  `https://t.me/{{bot_username}}?start=promo_{{code}}`.

**Рекомендация:** расширить `render_campaign_message` плейсхолдером `{{bot_username}}` (escaped) и подставлять runtime `bot_username` при dispatch.

## Живой статус депозита (polling)

### Состояния UI

| Состояние | Смысл |
|-----------|--------|
| `awaiting_transfer` | Invoice `pending`, не истёк |
| `detecting` | Тот же pending; подпись «ищем в сети» после первого poll / во время запроса |
| `credited` | Invoice `paid` **или** появился связанный активный депозит |
| `expired` | Invoice `expired` или TTL вышел |

Неверная сумма / несматченный перевод: остаёмся в `awaiting_transfer` / `detecting` с подсказкой про точный хвост — без ложного «платёж провален», пока нет отдельной детекции unmatched.

### API

Авторизованный:

`GET /api/deposits/invoice/{invoice_id}`

Минимум в ответе:

```json
{
  "id": 123,
  "status": "pending|paid|expired",
  "expires_at": 0,
  "exact_amount": "...",
  "bonus_usdt": "...",
  "effective_principal_usdt": "...",
  "deposit_id": null,
  "credited": false
}
```

- 404, если нет записи или invoice чужой.
- `credited: true`, если `status == paid` или задан `deposit_id`.

Источник: строка `deposit_invoices` + опциональный join на `deposits` по `invoice_id`.

### Polling на клиенте

- После `renderInvoice` — опрос каждые **6 с** (опционально лёгкий jitter); пауза при скрытой вкладке (`document.visibilityState`).
- Стоп при `credited`, `expired`, уходе с экрана / закрытии карточки invoice.
- Кнопка **Обновить** — один немедленный запрос.
- При `credited`: обновить тег, toast, CTA → **Активы**; остановить countdown или показать успех.

### Денежная безопасность

- Polling только read-only.
- Redemption промо — только при открытии депозита (как сейчас).
- Deep-link сам по себе **не** вызывает `create_invoice`.

## Критерии успеха

- `/start promo_CODE` + открытие Mini App → в поле депозита виден CODE.
- `startapp=promo_CODE` / `start_param` — то же поведение.
- Невалидный код не ломает auth; депозит без промо возможен.
- Pending invoice переходит в «зачислено» после матча монитора (в пределах ~одного интервала poll после записи в БД).
- Дефолтное promo-сообщение кампании после render содержит рабочую ссылку `t.me/...?start=promo_...`.
- Тесты: разбор promo start param; ownership статуса invoice; условия остановки poll (API / unit).

## Риски

| Риск | Смягчение |
|------|-----------|
| Нагрузка от polling | Интервал 6 с, стоп на терминальном статусе, пауза когда вкладка скрыта |
| Старый start_param при повторных открытиях | Prefill промо один раз за сессию Mini App (флаг в sessionStorage) |
| Неверный username бота в ссылке | Подставлять runtime `bot_username` при dispatch |

## Отложенные follow-up (не v1)

- Prefill суммы из кампании.
- UX для on-chain платежа без матча (recovery).
- Share sheet для партнёрской ссылки (отдельный backlog).

---

**Self-review:** Скоуп — deep-link C + polling; без WS; redemption без изменений; ref/promo взаимоисключающи в одном payload; обязательна проверка владельца на API. Плейсхолдеров/противоречий нет.
