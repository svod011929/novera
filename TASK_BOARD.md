# GFORT Cursor Task Board

Cursor отмечает выполненные пункты и сохраняет доказательства в `_cursor_output`.

## Stage 0 — baseline и аудит

- [ ] Выполнить `bash scripts/verify_workspace.sh`.
- [ ] Зафиксировать SHA-256 baseline через `bash scripts/snapshot_baseline.sh`.
- [ ] Описать архитектуру, маршруты, endpoints, background workers и таблицы.
- [ ] Зафиксировать финансовые инварианты и текущую state machine.
- [ ] Сравнить V10.6 с `_reference/V10_5_SOURCE`.
- [ ] Выявить regression risks и разделить их на P0/P1/P2/P3.
- [ ] Создать `00_BASELINE_AUDIT.md` и `01_IMPLEMENTATION_PLAN.md`.

## Stage 1 — UX-аудит и дизайн-система

- [ ] Инвентаризировать пользовательские и административные экраны.
- [ ] Проверить наложение текста, адаптивность, состояния и русскую локализацию.
- [ ] Определить tokens: цвета, типографику, spacing, radii, shadows, icons и motion.
- [ ] Создать reusable components вместо точечных CSS-патчей.
- [ ] Подготовить визуальные проверки 360/390/430 px.

## Stage 2 — пользовательский Mini App

- [ ] Главная: баланс, активные инвестиции, ближайшая выплата и быстрые действия.
- [ ] Пополнение: BEP-20, адрес, точная сумма, уникальный хвост, срок и статус.
- [ ] Инвестиции: прогресс, выплачено, ожидается, следующий платёж и детали.
- [ ] Выплаты/история: фильтры, статус, адрес, tx link и понятные причины ошибок.
- [ ] Партнёрка: уровень, оборот, команда, рефбаланс и источник доступа auto/manual.
- [ ] Кошелёк: безопасная смена адреса с объяснением влияния на существующие выплаты.
- [ ] Уведомления: пополнение, вывод, инвестиции и партнёрская статистика.
- [ ] Профиль: пригласитель, поддержка, язык и корректная Telegram-сессия.
- [ ] Исправить сценарии «Сессия устарела» и переключение Telegram-аккаунта без смешения авторизации.

## Stage 3 — административная панель

- [ ] Dashboard: treasury, safety, очереди, stuck operations и admin events.
- [ ] Пользователи: поиск, фильтры, пагинация и единая карточка.
- [ ] Добавление администраторов с полными правами и защита последнего owner.
- [ ] Изменение реферального баланса с причиной, before/after и audit.
- [ ] Ручное открытие инвестиции с preview графика и защитой от дубля.
- [ ] Управление доступом к уровням партнёрской программы без изменения оборота.
- [ ] Безопасная смена кошелька пользователя с учётом queued/signed/broadcast payout.
- [ ] Настройка ссылок поддержки/сообщества, текстов и кнопок интерфейса.
- [ ] Рассылки с форматированием, premium emoji, media, buttons, preview и test send.
- [ ] Payout/deposit/safety screens с понятными статусами и действиями.

## Stage 4 — надёжность и безопасность

- [ ] Unit/integration tests всех новых admin mutations.
- [ ] Idempotency, concurrent requests, double click и retry tests.
- [ ] Financial regression tests существующих расчётов и очередей.
- [ ] Проверить WSS/HTTP fallback, freshness и отсутствие блокировки всего приложения.
- [ ] Проверить отсутствие secrets во frontend, logs, screenshots и error payloads.
- [ ] Accessibility, performance и slow/offline network states.

## Stage 5 — независимое ревью

- [ ] Открыть новую чистую сессию Cursor.
- [ ] Проверить exact diff, миграции, API, безопасность и финансовые инварианты.
- [ ] Закрыть P0/P1; P2 исправить или письменно принять.
- [ ] Подготовить GO / CONDITIONAL GO / NO-GO.

## Stage 6 — release candidate

- [ ] Собрать self-contained installer, не включая реальные secrets.
- [ ] Сравнить extracted payload с рабочим деревом.
- [ ] Прогнать shell/build/self-tests и migration tests.
- [ ] Проверить verified backup, preflight, safe cutover и rollback rehearsal.
- [ ] Подготовить release notes, SHA-256, команду установки и post-deploy checklist.
- [ ] Остановиться перед production и запросить отдельное разрешение владельца.

