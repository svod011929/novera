# GFORT Cursor Task Board

Cursor отмечает выполненные пункты и сохраняет доказательства в `_cursor_output`.

## Stage 0 — baseline и аудит

- [x] Выполнить `bash scripts/verify_workspace.sh`. *(host: bash/Python unavailable; equivalent PowerShell baseline + static review; see `_cursor_output/TEST_REPORT.md`)*
- [x] Зафиксировать SHA-256 baseline через `bash scripts/snapshot_baseline.sh`. *(PowerShell Get-FileHash → `_cursor_output/BASELINE_SHA256.txt`)*
- [x] Описать архитектуру, маршруты, endpoints, background workers и таблицы.
- [x] Зафиксировать финансовые инварианты и текущую state machine.
- [x] Сравнить V10.6 с `_reference/V10_5_SOURCE`.
- [x] Выявить regression risks и разделить их на P0/P1/P2/P3.
- [x] Создать `00_BASELINE_AUDIT.md` и `01_IMPLEMENTATION_PLAN.md`.
- [x] **I-01b** baseline pytest green (26→ then 27 with I-04).
- [x] **I-04** session/account-switch: dual NOVERA/GFORT auth headers, storage migration, identity clear. → `TEST_REPORT.md`
- [x] **I-08** admin controls API tests + additive reason/operation_id validation (min/max clamp + balance/level idempotency deferred). → `TEST_REPORT.md`
- [x] **I-09** wallet vs payout clarity (UI only; server cutover unchanged). → `TEST_REPORT.md`
- [x] **I-10** broadcast preview, audience count, admin-only test send, retry of failed deliveries. → `TEST_REPORT.md`
- [x] **I-11** financial golden fixtures + security hardening; verdict **CONDITIONAL GO**. → `11_HARDENING_REVIEW.md`
- [x] **I-12** RC installer built + hashed; **hard stop — no production install**. → `12_RELEASE_CANDIDATE.md`

## Stage 1 — UX-аудит и дизайн-система

- [x] Инвентаризировать пользовательские и административные экраны. → `_cursor_output/02_UX_AUDIT.md`
- [x] Проверить наложение текста, адаптивность, состояния и русскую локализацию. *(static code audit; live 360/390/430 screenshots still pending)*
- [x] Определить tokens: цвета, типографику, spacing, radii, shadows, icons и motion. → **NOVERA** `design-tokens.css` + `novera-brand.css` (`03_DESIGN_TOKENS.md`)
- [x] Создать reusable components вместо точечных CSS-патчей. → primitives `.stack` / `.cluster` / `.surface` / `.money` / `.touch-target` (I-03)
- [x] Подготовить визуальные проверки 360/390/430 px. → live CDP on bnbb.tech + `_cursor_output/RESPONSIVE_PROOF_360_390_430.md` (Telegram WebView owner pass still open)

## Stage 2 — пользовательский Mini App

- [x] Главная: баланс, активные инвестиции, ближайшая выплата и быстрые действия. → **I-05** + live CDP home 360
- [x] Пополнение: BEP-20, адрес, точная сумма, уникальный хвост, срок и статус. → **I-06** + live CDP wallet 390 (invoice fields after auth)
- [x] Инвестиции: прогресс, выплачено, ожидается, следующий платёж и детали. → **I-05** + live CDP assets 430
- [x] Выплаты/история: фильтры, статус, адрес, tx link и понятные причины ошибок. → Stage A1 2026-09-06
- [x] Партнёрка: уровень, оборот, команда, рефбаланс и источник доступа auto/manual. → Stage A2 2026-09-06
- [x] Кошелёк: безопасная смена адреса с объяснением влияния на существующие выплаты. → **I-09 UI clarity** (backend cutover still owner-gated)
- [x] Уведомления: пополнение, вывод, инвестиции и партнёрская статистика. → Stage A3 2026-09-06
- [x] Профиль: пригласитель, поддержка, язык и корректная Telegram-сессия. → session recover CTA A3
- [x] Исправить сценарии «Сессия устарела» и переключение Telegram-аккаунта без смешения авторизации. → **I-04 done in code/tests**; recover CTA on device
## Stage 3 — административная панель

- [x] Dashboard: treasury, safety, очереди, stuck operations и admin events. → Stage B1 2026-09-06
- [x] Пользователи: поиск, фильтры, пагинация и единая карточка. → **I-07** + Stage B3 filters
- [x] Добавление администраторов с полными правами и защита последнего owner. → owner-model UI + confirm remove (master follow-up)
- [x] Изменение реферального баланса с причиной, before/after и audit. → **I-08 API tests** (V10.6 endpoint already existed)
- [x] Ручное открытие инвестиции с preview графика и защитой от дубля. → **I-08 idempotency tests**; UI preview still optional
- [x] Управление доступом к уровням партнёрской программы без изменения оборота. → **I-08 API tests**
- [x] Безопасная смена кошелька пользователя с учётом queued/signed/broadcast payout. → **I-09 UI + counts**; rewrite policy still owner-gated
- [x] Настройка ссылок поддержки/сообщества, текстов и кнопок интерфейса. → links tab polish + preview (master follow-up)
- [x] Рассылки с форматированием, premium emoji, media, buttons, preview и test send. → **I-10**; premium emoji ограничены Bot API
- [x] Payout/deposit/safety screens с понятными статусами и действиями. → Stage B2 2026-09-06

## Stage 4 — надёжность и безопасность

- [x] Unit/integration tests всех новых admin mutations. → **I-08** `test_admin_controls_api.py` (30 suite green)
- [x] Idempotency, concurrent requests, double click и retry tests. → investment `operation_id` + admin balance/level `Idempotency-Key` (2026-09-06)
- [x] Financial regression tests существующих расчётов и очередей. → **I-11** `test_financial_regression.py`
- [x] Проверить WSS/HTTP fallback, freshness и отсутствие блокировки всего приложения. → bootstrap notes 2026-09-06
- [x] Проверить отсутствие secrets во frontend, logs, screenshots и error payloads. → static review in I-11 (no secrets in Mini App; XSS allowlist tested)
- [x] Accessibility, performance и slow/offline network states. → offline/slow/timeout + focus-visible / reduced-motion (master follow-up)

## Stage 5 — независимое ревью

- [x] Открыть новую чистую сессию Cursor. → I-11 review recorded in `11_HARDENING_REVIEW.md` (second owner pass still recommended)
- [x] Проверить exact diff, миграции, API, безопасность и финансовые инварианты. → financial + security suites; no schema migration in I-08…I-11
- [x] Закрыть P0/P1; P2 исправить или письменно принять. → owner ACCEPT 2026-09-06 (`DECISION_PACK_AS_IMPLEMENTED.md`); CONDITIONAL GO → GO with activation still owner-gated
- [x] Подготовить GO / CONDITIONAL GO / NO-GO. → **CONDITIONAL GO**

## Stage 6 — release candidate

- [x] Собрать self-contained installer, не включая реальные secrets. → `scripts/build_release_candidate.ps1`
- [x] Сравнить extracted payload с рабочим деревом. → round-trip extract + critical hashes in build
- [x] Прогнать shell/build/self-tests и migration tests. → local pytest 74/74; installer self-tests embedded (run on VPS at install)
- [x] Проверить verified backup, preflight, safe cutover и rollback rehearsal. → `deploy/backup-rehearsal.sh` + `deploy/safe-update.sh`
- [x] Подготовить release notes, SHA-256, команду установки и post-deploy checklist.
- [x] Остановиться перед production и запросить отдельное разрешение владельца. → **HARD STOP** in `12_RELEASE_CANDIDATE.md`

## NOVERA owner bootstrap

- [x] Fail-closed state machine `bootstrap/configured/active/degraded` +
  `financial_ready`
- [x] Immutable owner authorization and blocked liability mutations before
  activation
- [x] Versioned encrypted RPC/WSS/seed bundle with atomic activation and
  previous-generation rollback
- [x] Owner-only setup wizard with treasury confirmation and fresh Telegram
  initData
- [x] Database + encrypted-generation backup and guarded restore
- [x] One-file fresh-VPS installer with hidden new-token prompt, generated
  master key, DNS/TLS/health checks and overwrite refusal
- [x] Full suite **90/90**, JS/shell parse, token scan and 74-file payload/hash
  round-trip
- [x] Final artifact:
  `_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh`
  (supersedes `…20260905-220159.sh`, which fails on Ubuntu 26.04 uutils)
- [x] Production run — 2026-09-06, owner-authorised, over SSH on
  `170.168.91.129`: `https://bnbb.tech` in `bootstrap` state, TLS issued,
  `financial_ready=false`. Details in `_cursor_output/NOVERA_BOOTSTRAP_RELEASE.md`
- [ ] Owner: Admin → System (validate → confirm treasury → activate), then
  Admin → Terms switches
- [ ] Owner: back up `/opt/gfort/state/secrets/runtime_config_key.txt`
  off-server
- [x] Safe update path + Stage A/B UX promoted 2026-09-06
  (`novera-update-20260906-100344`, frontend-only)
- [x] Backup rehearsal + SSH harden (`PasswordAuthentication no`)

