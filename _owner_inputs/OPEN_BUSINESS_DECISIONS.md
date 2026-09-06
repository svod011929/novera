# Решения владельца (закрыто 2026-09-06)

Владелец принял текущее поведение кода («Все норм»).
Полная таблица: `_owner_inputs/DECISION_PACK_AS_IMPLEMENTED.md`.

Кратко:

1. 200% = прибыль; principal отдельно.
2. Cutover: freeze с момента `queued` (и адреса депозита при открытии).
3. Оборот линии = активный principal первой линии.
4. Ручной уровень = перспектива, без backfill.
5. Подтверждение смены кошелька — client `confirm`.
6. Роли: User / Admin / Owner.

P0/P1: manual investment liability и referral path для admin opens — принять как есть;
admin invest без clamp min/max — принять; idempotency для balance/level — уже в коде.

Пока нет письменного CHANGE, Cursor не меняет финансовые формулы.
