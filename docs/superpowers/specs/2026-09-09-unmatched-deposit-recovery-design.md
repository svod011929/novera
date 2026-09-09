# Unmatched deposit UX + admin recovery — Дизайн

**Дата:** 2026-09-09  
**Статус:** Утверждён владельцем 2026-09-09  
**Продукт:** NOVERA Mini App / Telegram-бот  
**Подход:** поэтапный (сначала пользовательский UX, затем админ-match)

## Проблема

1. Перевод на treasury без точного `exact_minor` (или после expiry) пишется в `chain_deposits` (`matched=0`) и audit `unmatched_deposit`, но **нигде не «дотягивается»** до депозита.
2. Mini App при polling показывает «ждём перевод» / «срок истёк» и **не объясняет**, что в сети мог быть платёж с неверной суммой.
3. Админ видит только сырой лог; ручной investment **не связывает** on-chain строку.

## Зафиксированные решения

| Тема | Выбор |
|------|--------|
| Скоуп v1 | **C:** юзерский UX + админ-recovery (сначала UX) |
| Админ-match | **B:** к invoice пользователя даже при ≠ сумме; депозит на **фактическую** on-chain сумму + reason/audit |
| Детект для юзера | **D:** мягкая эвристика около активного invoice + усиленный fallback-текст; автозачисления нет |
| Статус invoice для match | **B:** `pending` **или** `expired`; никогда `paid` |
| Архитектура | Поэтапный продукт (не авто-сканер) |

## Цели

1. Пока invoice жив/недавно истёк — при near-miss показать понятный **amount mismatch** и путь в поддержку.
2. Админ может **явно** привязать unmatched `chain_deposit` к invoice пользователя и открыть депозит на on-chain сумму с полным аудитом.
3. Денежные правила обычного монитора не меняются: автомат по-прежнему матчит только `exact_minor` + pending.

## Вне скоупа (v1)

- Авто-rematch / фоновый «recovery scanner».
- Match без invoice / «открыть депозит только по tx».
- Самозачисление / claim по `from_address` пользователем.
- Смена формулы дробного хвоста или экономики депозита.
- WebSocket для событий recovery.

## Фаза 1 — Пользовательский UX (read-only)

### Расширение `GET /api/deposits/invoice/{invoice_id}`

К существующему ответу добавить:

```json
{
  "mismatch_hint": false,
  "mismatch": null
}
```

При срабатывании эвристики:

```json
{
  "mismatch_hint": true,
  "mismatch": {
    "observed_amount": "100.00",
    "expected_amount": "100.37",
    "tx_hash": "0x…",
    "created_at": 0
  }
}
```

- Только owner invoice (как сейчас); чужой/отсутствующий → 404.
- Hint **не** кредитует и **не** помечает ownership на `chain_deposits`.

### Эвристика near-miss

Искать в `chain_deposits` где `matched = 0`, в окне времени:

`[invoice.created_at − 5 минут, invoice.expires_at + 2 часа]`

и сумма:

- `amount_minor == invoice.base_minor`, **или**
- `|amount_minor − invoice.exact_minor| ≤ 100` (≤ 1.00 USDT).

Если несколько кандидатов — брать **ближайший по времени** к `invoice.created_at` (затем меньший `|Δ|` к exact).

Не раскрывать unmatched чужих пользователей: кандидаты глобальны по treasury, но показываются только в контексте **своего** invoice и только как soft-hint (ложная тревога допустима реже, чем тишина; админ всё равно чинит вручную).

### Mini App

- Новый UI phase: `amount_mismatch` при `mismatch_hint` и отсутствии `credited`.
- RU-копирайт: перевод в сети найден, сумма не совпала с точной (показать expected vs observed), нужны копейки/хвост; CTA в `support_url`.
- При `expired` без credit — усиленный fallback даже без hint.
- Polling ~6 с без изменений по интервалу; hint обновляется вместе со статусом.
- Кнопки самозачисления у пользователя **нет**.

## Фаза 2 — Admin recovery

### API

1. `GET /api/admin/chain-deposits?matched=0&limit=…`  
   Список unmatched: id, tx_hash, log_index, amount, from/to, block, created_at, explorer URL fields.

2. `POST /api/admin/chain-deposits/{id}/match`  
   Body: `{ "invoice_id": N, "reason": "…" }` (`reason` обязателен, непустой).

### Правила match

- Caller: `admin_user`.
- `chain_deposit.matched == 0` и `invoice_id` ещё NULL.
- Invoice: существует; статус `pending` или `expired`; **не** `paid`.
- User invoice не blocked; для открытия депозита нужен `payout_address` (как при обычном open).
- Principal депозита = **`chain_deposits.amount_minor`** (on-chain), не `exact_minor` / не `base_minor` invoice.
- Промо: если у invoice был `promo_code_id` — попытка redeem как в `apply_transfer`; при невозможности — skip + audit `promo_redeem_skipped`, депозит всё равно на on-chain сумму (+0 bonus).
- После успеха: `chain_deposits.matched=1`, `invoice_id` set; invoice → `paid` (если ещё не); создать `deposits` row; audit `deposit_recovery_matched` (tx, amounts, invoice_id, admin_id, reason).
- Повторный match того же chain_deposit → **409**.
- Match к уже `paid` invoice → **409**.

### Admin UI

- Блок/вкладка **Unmatched deposits** (или отдельный список рядом с Logs): tx, amount, time, explorer link.
- Действие **Match**: invoice id + reason → confirm → toast; строка уходит из unmatched.

## Денежная безопасность

- Обычный `apply_transfer` / монитор **без изменений** правил exact-match.
- Юзерский путь — только read-only hint.
- Единственный credit-path recovery — явный админ-match с reason.
- Идемпотентность и запрет double-credit обязательны в тестах.

## Критерии успеха

- При near-miss пользователь видит mismatch (или сильный expiry-текст), не «вечное ожидание» без объяснения.
- Админ может закрыть реальный кейс «отправил 100.00 вместо 100.37» через match к pending/expired invoice; депозит = 100.00 USDT on-chain; `chain_deposits` связан.
- Повторный match и match к paid — отклоняются.
- Автомат по-прежнему не зачисляет неверный хвост сам.

## Риски

| Риск | Смягчение |
|------|-----------|
| Ложный mismatch_hint (чужой перевод с похожей суммой) | Узкое окно ±1 USDT / base; только soft UX; фикс — админ |
| Админ ошибся invoice | Обязательный reason, confirm UI, audit; нет массового auto |
| Промо при другой сумме | Тот же skip-path, что при обычном confirm |

## Тесты (минимум)

- Hint: hit / miss / ownership 404.
- Admin match: amount ≠ exact → deposit на on-chain; pending + expired ok; paid → 409; double → 409; audit present.
- Promo redeem skip при невозможности, депозит всё равно открыт.

## Порядок внедрения

1. Фаза 1: эвристика + поля API + Mini App phase/copy.  
2. Фаза 2: repo match + admin API + UI.  
3. Verify + deploy.

---

**Self-review:** Скоуп = UX hint + админ-match B; без авто-scanner; pending|expired only; principal = on-chain; плейсхолдеров нет; противоречий с обычным exact-match монитором нет.
