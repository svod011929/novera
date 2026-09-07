<p align="center">
  <img src="frontend/assets/brand/novera-logo.jpg" width="88" height="88" alt="NOVERA" />
</p>

<h1 align="center">NOVERA</h1>

<p align="center">
  <strong>Digital Capital</strong> · Telegram Mini App · USDT BEP-20<br/>
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
| **Safe update** | Обновления в `/opt/gfort/releases` с проверкой `/ready` и откатом |

Свежая установка всегда **fail-closed**: сеть, депозиты, выплаты, инвестиции и партнёрка выключены, пока Owner не активирует их в **Admin → System**.

---

## Установка одной командой (curl)

> Репозиторий приватный — нужен GitHub-токен. Сначала `gh auth login` на рабочей машине, затем запуск **от root** на чистом Ubuntu/Debian VPS.

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
2. проверяет **SHA-256** `759fe144e5520805576cb124030a6fc08bbd2a540e3cd2bf6e67ef25b2549b45`
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
  "/repos/svod011929/novera/contents/_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh" \
  > NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh

echo '759fe144e5520805576cb124030a6fc08bbd2a540e3cd2bf6e67ef25b2549b45  NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh' \
  | sha256sum -c -

scp NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh root@YOUR_VPS:/root/
ssh root@YOUR_VPS 'bash NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh \
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

## Карта репозитория

```
delta_backend/     FastAPI, финансы, encrypted runtime secrets
frontend/          Telegram Mini App (бренд NOVERA)
deploy/            safe-update, backup, restore, bootstrap stub
scripts/           сборка и remote-promote
tests/             pytest (финансы, security, bootstrap, admin)
_cursor_output/    решения, отчёты, манифесты + pinned installer
_owner_inputs/     decision pack владельца (принят 2026-09-06)
```

Закреплённый installer:

| Артефакт | Значение |
|----------|----------|
| Файл | `_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260907-103836.sh` |
| SHA-256 | `759fe144e5520805576cb124030a6fc08bbd2a540e3cd2bf6e67ef25b2549b45` |
| Точка входа | [`install.sh`](./install.sh) |

Устарел (не использовать на Ubuntu 26.04): `…20260905-220159.sh`.

---

## Безопасность

- В git нет bot token / seed / RPC / WSS / master key
- Снаружи только Caddy; backend в изолированных Docker-сетях
- Неизменяемые `OWNER_IDS`; динамические админы не активируют chain и не выдают Owner
- Runtime-секреты сети: AES-256-GCM bundle + отдельный master key
- Admin balance / referral-balance / referral-level требуют `Idempotency-Key`

---

## Локальная проверка

```bash
python -m pytest -q
python -m compileall -q delta_backend main.py
```

---

## Доступ

Приватный репозиторий оператора NOVERA. Не публикуйте токены, seed и `runtime_config_key.txt`.
