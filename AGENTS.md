# GFORT Agent Instructions

## Обязательный контекст

Перед любой правкой прочитай `START_HERE.md`, `docs/MASTER_PLAN.md`, `TASK_BOARD.md` и `.cursor/rules/gfort-safety.mdc`.

## Режим выполнения

- Ты единственный исполнитель: analyst → product designer → implementer → reviewer → release engineer.
- Сначала Stage 0 без изменения исходного кода.
- После baseline выполняй небольшие изолированные итерации по `TASK_BOARD.md`.
- Не задавай владельцу общие вопросы, если можно сделать безопасное консервативное допущение. Запиши допущение в `_cursor_output/DECISIONS.md`.
- Останавливайся только на перечисленных в `START_HERE.md` approval gates.

## Границы файлов

- Рабочий код находится в корне проекта: `delta_backend`, `frontend`, `tests`, `deploy` и конфигурационные файлы.
- `_reference/**` — только чтение. Никогда не редактируй исторические исходники и installers.
- `_owner_inputs/**` — входные материалы владельца. Не изменяй оригинальные изображения и файлы бренда.
- Отчёты, планы, скриншоты и результаты проверок складывай в `_cursor_output/**`.
- Не создавай `.env` с реальными значениями и не добавляй secrets в репозиторий.

## Правила реализации

- Не меняй финансовую семантику без отдельного письменного решения владельца.
- Не выполняй production deploy, `--fresh`, destructive SQL или реальные blockchain-транзакции.
- Для денежных значений сохраняй integer minor units и существующие инварианты.
- Любая новая admin mutation: server-side role check, validation, atomic transaction, idempotency, audit actor/reason/before/after/timestamp/correlation ID.
- Пользовательский интерфейс — Telegram-first, русский язык полный, адаптивность 360/390/430 px, touch target не менее 44 px.
- После каждой итерации обновляй `_cursor_output/CHANGELOG.md` и `_cursor_output/TEST_REPORT.md`.
- Финальное ревью проводится в новой чистой сессии Cursor по exact diff.

## Definition of Done

Смотри раздел 12 в `docs/MASTER_PLAN.md`. P0/P1 блокирует релиз. Production допускается только после отдельного разрешения владельца.

