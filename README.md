<p align="center">
  <img src="frontend/assets/brand/novera-logo.jpg" width="88" height="88" alt="NOVERA" />
</p>

<h1 align="center">NOVERA</h1>
<p align="center"><em>NOVERA Digital Capital — Operations &amp; Bootstrap Platform</em></p>

<p align="center">
  Telegram Mini App · Owner-админка · USDT BEP-20 учёт<br/>
  Безопасный owner-bootstrap · Поэтапные обновления · Приватный production-репозиторий
</p>

<p align="center">
  <img alt="visibility" src="https://img.shields.io/badge/доступ-приватный-111827?style=flat-square" />
  <img alt="stack" src="https://img.shields.io/badge/стек-FastAPI%20·%20Telegram%20·%20Caddy-0ea5e9?style=flat-square" />
  <img alt="tests" src="https://img.shields.io/badge/pytest-91%20passed-22c55e?style=flat-square" />
  <img alt="state" src="https://img.shields.io/badge/bootstrap-financial__ready%3Dfalse-f59e0b?style=flat-square" />
</p>

---

## Что внутри

| Слой | Назначение |
|------:|------------|
| **Mini App** | Кабинет: пополнение, активы, команда, история, кошелёк, уведомления |
| **Админка** | Обзор, пользователи, выплаты/депозиты, рассылки, условия, System-активация |
| **Installer** | Один файл на чистый VPS (Docker, Caddy, TLS, бот, финансы выключены) |
| **Брендинг** | Мастер `СОБРАТЬ_БОТА.bat` — новый инстанс с другим именем/лого/цветом |
| **Safe update** | Обновления в `/opt/gfort/releases` с проверкой `/ready` и откатом |

Свежая установка всегда **fail-closed**: сеть, депозиты, выплаты, инвестиции и партнёрка выключены, пока Owner не активирует их в **Admin → System**.

---

## Возможности

**Mini App (пользователь)**
- Личный кабинет: баланс, активы, история операций
- Пополнение депозита с автоматическим распознаванием входящего платежа (сканер блокчейна)
- Реферальная структура: команда, уровни, история начислений
- Уведомления и рассылки от оператора, мультиязычный интерфейс (ru/en/it/es/uk/ky/uz)
- Адаптивная вёрстка (360–430px), офлайн-баннер, поддержка reduced-motion

**Админка (оператор)**
- Обзорная панель: пользователи, депозиты, выплаты, статус сети
- Ручное управление балансом/рефералкой с защитой от повторной отправки (`Idempotency-Key`)
- Управление условиями (Terms) и рекламными баннерами
- **Admin → System**: пошаговый визард активации сети (RPC/WSS/seed/контракт) с проверкой перед включением финансов
- Раннее закрытие инвестиций администратором (`admin_close_investment`)

**Инфраструктура**
- One-file bootstrap installer: Docker + Caddy (TLS Let's Encrypt) + бот + БД, всё в состоянии `bootstrap` до ручной активации
- Безопасные обновления с автооткатом при провале `/ready`
- Резервное копирование и восстановление с проверкой целостности (`PRAGMA integrity_check`)
- Мастер брендирования: новое имя/лого/цветовая тема → готовый установщик за 5 минут, без правки кода

---

## Установка одной командой (curl)

> Репозиторий приватный — нужен GitHub-токен. Сначала `gh auth login` на рабочей машине, затем запуск **от root** на чистом Ubuntu/Debian VPS.

### 0) Для не-разработчика

Дважды кликните **`СОБРАТЬ_БОТА.bat`** в корне проекта — мастер задаст простые
вопросы и сам подготовит установщик. Инструкция на 7 шагов:
[`_owner_inputs/BRAND_PROFILES/README.md`](./_owner_inputs/BRAND_PROFILES/README.md).
Дальше — шаги 1–2 ниже (загрузка на VPS и запуск).

### 1) Авторизация (один раз)

```bash
# на ноутбуке
gh auth login -h github.com -p https -w
export GH_TOKEN="$(gh auth token)"
```

### 2) Установка на чистый VPS

```bash
curl -fsSL \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/svod011929/novera/contents/install.sh?ref=main" \
| sudo env GH_TOKEN="$GH_TOKEN" bash -s -- \
  --domain YOUR_DOMAIN \
  --ip YOUR_PUBLIC_IP \
  --owner-id YOUR_TELEGRAM_ID
```

Что делает обёртка:

1. скачивает закреплённый one-file installer из этого репо  
2. проверяет **SHA-256** `fc5ae5080e3339d526e1710afd6a41e817d64144e6a2d5a6c30bba400b01c003`
3. запускает его (скрытый ввод **нового** токена BotFather)

### Пример для production (bnbb.tech)

```bash
curl -fsSL \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/svod011929/novera/contents/install.sh?ref=main" \
| sudo env GH_TOKEN="$GH_TOKEN" bash -s -- \
  --domain bnbb.tech \
  --ip 170.168.91.129 \
  --owner-id 8054710484
```

### Вариант через scp (без pipe)

```bash
# ноутбук
gh api -H "Accept: application/vnd.github.raw" \
  "/repos/svod011929/novera/contents/_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260907-224025.sh" \
  > NOVERA_BOOTSTRAP_INSTALLER_20260907-224025.sh

echo 'fc5ae5080e3339d526e1710afd6a41e817d64144e6a2d5a6c30bba400b01c003  NOVERA_BOOTSTRAP_INSTALLER_20260907-224025.sh' \
  | sha256sum -c -

scp NOVERA_BOOTSTRAP_INSTALLER_20260907-224025.sh root@YOUR_VPS:/root/
ssh root@YOUR_VPS 'bash NOVERA_BOOTSTRAP_INSTALLER_20260907-224025.sh \
  --domain YOUR_DOMAIN --ip YOUR_PUBLIC_IP --owner-id YOUR_TELEGRAM_ID'
```

---

## После установки

Проверки:

```bash
curl -fsS https://YOUR_DOMAIN/health
curl -fsS https://YOUR_DOMAIN/ready
```

Ожидаемо сразу после install:

- `setup.status=bootstrap`
- `financial_ready=false`
- TLS через Let's Encrypt / Caddy

Шаги Owner:

1. Сделать off-server копию `/opt/gfort/state/secrets/runtime_config_key.txt`
2. Открыть Mini App как Owner → **Admin → System**
3. Проверить RPC / WSS / seed / контракт / scan block
4. Подтвердить адрес казны → **Activate**
5. Включить только согласованные переключатели в **Admin → Terms**

**Не** запускайте bootstrap installer повторно на хосте, где уже есть `/opt/gfort`.

---

## Безопасные обновления (уже установленный VPS)

С Windows-машины оператора:

```powershell
# только frontend (без мигания API)
powershell -NoProfile -File scripts\safe_update_remote.ps1 -Mode frontend

# backend + frontend (короткий blink API, откат при падении /ready)
powershell -NoProfile -File scripts\safe_update_remote.ps1 -Mode full
```

На VPS создаётся `/opt/gfort/releases/novera-update-<stamp>`, переиспользуются `.env` и `/opt/gfort/state`, проверяется публичный `/ready`, при ошибке — откат.

---

## Новый брендированный installer (для новичков)

Дважды кликните **`СОБРАТЬ_БОТА.bat`** в корне проекта → ответьте на вопросы → залейте `.sh` на VPS.

Инструкция на 7 шагов: [`_owner_inputs/BRAND_PROFILES/README.md`](./_owner_inputs/BRAND_PROFILES/README.md).

**В installer нет** bot token / RPC / WSS / seed / runtime key — токен спросит сервер (BotFather).

---

## Карта репозитория

```
delta_backend/     FastAPI, финансы, encrypted runtime secrets
frontend/          Telegram Mini App (бренд NOVERA)
deploy/            safe-update, backup, restore, bootstrap stub
scripts/           сборка и remote-promote
tests/             pytest (финансы, security, bootstrap, admin)
_cursor_output/    решения, отчёты, манифесты + pinned installer
_owner_inputs/     decision pack владельца + BRAND_PROFILES
```

Закреплённый installer:

| Артефакт | Значение |
|----------|----------|
| Файл | `_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260907-224025.sh` |
| SHA-256 | `fc5ae5080e3339d526e1710afd6a41e817d64144e6a2d5a6c30bba400b01c003` |
| Точка входа | [`install.sh`](./install.sh) |
| Манифест | `_cursor_output/releases/BOOTSTRAP_MANIFEST_20260907-224025.txt` |

Более ранние `_BOOTSTRAP_INSTALLER_*.sh` в этой папке — устаревшие сборки,
не использовать. Всегда собирайте новый файл через `СОБРАТЬ_БОТА.bat` или
`scripts\build_bootstrap_installer.ps1` вместо переиспользования старого.

---

## Безопасность

- В git нет bot token / seed / RPC / WSS / master key
- Снаружи только Caddy; backend в изолированных Docker-сетях
- Неизменяемые `OWNER_IDS`; динамические админы не активируют chain и не выдают Owner
- Runtime-секреты сети: AES-256-GCM bundle + отдельный master key
- Admin balance / referral-balance / referral-level требуют `Idempotency-Key`

---

## Архитектура и стек

| Компонент | Технология |
|-----------|------------|
| Backend / API | Python, FastAPI + Uvicorn |
| Telegram-бот | aiogram 3 |
| База данных | SQLite (aiosqlite), шифрованные секреты отдельным bundle |
| Блокчейн | web3.py + eth-account (USDT BEP-20, сканер входящих транзакций) |
| Frontend | Telegram Mini App: HTML/CSS/JS, design tokens под бренд-профиль |
| Прокси / TLS | Caddy (авто-выпуск Let's Encrypt) |
| Развёртывание | Docker Compose, one-file installer, safe-update с откатом |
| Тесты | pytest (финансы, безопасность, bootstrap, админка) |

---

## FAQ оператора

**Как запустить ещё один бот с другим именем/лого/цветом?**
Дважды кликнуть `СОБРАТЬ_БОТА.bat`, ответить на вопросы, залить получившийся `.sh` на новый чистый VPS. Ядро (код) общее, меняются только бренд-данные — см. [`_owner_inputs/BRAND_PROFILES/README.md`](./_owner_inputs/BRAND_PROFILES/README.md).

**Можно ли обновить уже работающий бот без простоя?**
Да, `scripts\safe_update_remote.ps1 -Mode frontend` (без перезапуска API) или `-Mode full` (короткий блинк API, автооткат при неуспешном `/ready`).

**Что делать, если что-то пошло не так после установки?**
Установщик ничего не активирует финансово по умолчанию (`financial_ready=false`). Депозиты/выплаты/сеть включаются только вручную в **Admin → System** после проверки RPC/WSS/seed.

**Где хранятся секреты (токен, seed, ключи)?**
Только на сервере, в зашифрованном bundle (`AES-256-GCM`) и в файлах, которые в этот репозиторий никогда не попадают. Токен бота вводится только на VPS в момент установки.

---

## Локальная проверка

```bash
python -m pytest -q
python -m compileall -q delta_backend main.py
```

---

## Доступ

Приватный репозиторий оператора NOVERA. Не публикуйте токены, seed и `runtime_config_key.txt`.
