<p align="center">
  <img src="frontend/assets/brand/novera-logo.jpg" width="88" height="88" alt="NOVERA" />
</p>

<h1 align="center">NOVERA</h1>

<p align="center">
  <strong>Digital Capital</strong> · Telegram Mini App · USDT BEP-20<br/>
  Fail-closed owner bootstrap · Safe staged updates · Private production tree
</p>

<p align="center">
  <img alt="visibility" src="https://img.shields.io/badge/visibility-private-111827?style=flat-square" />
  <img alt="stack" src="https://img.shields.io/badge/stack-FastAPI%20·%20Telegram%20·%20Caddy-0ea5e9?style=flat-square" />
  <img alt="tests" src="https://img.shields.io/badge/pytest-91%20passed-22c55e?style=flat-square" />
  <img alt="state" src="https://img.shields.io/badge/bootstrap-financial__ready%3Dfalse-f59e0b?style=flat-square" />
</p>

---

## What you get

| Layer | Role |
|------:|------|
| **Mini App** | User cabinet: deposits, assets, team, history, wallet, notifications |
| **Admin** | Overview, users, payouts/deposits, broadcasts, terms, System activate |
| **Installer** | One-file fresh VPS bring-up (Docker, Caddy, TLS, bot, fail-closed finance) |
| **Safe update** | Staged promote under `/opt/gfort/releases` with health gate + rollback |

Fresh installs start **fail-closed**: chain / deposits / payouts / investments / referrals are off until the immutable Owner activates them in **Admin → System**.

---

## One-liner bootstrap (curl)

> Private repository → GitHub token required. Prefer `gh auth login` on the operator machine, then run on a **clean** Ubuntu/Debian VPS as root.

### 1) Authenticate once

```bash
# on your laptop
gh auth login -h github.com -p https -w
export GH_TOKEN="$(gh auth token)"
```

### 2) Install on a clean VPS

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

The wrapper:

1. downloads the pinned one-file installer from this repo  
2. verifies **SHA-256** `85b5b6b54147e7d683777bb529ae4d7d937ac8de71f005180b85ec6d20eab415`  
3. executes it (asks for a **new** BotFather token with hidden input)

### Production example (bnbb.tech)

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

### Offline / scp variant

```bash
# laptop
gh api -H "Accept: application/vnd.github.raw" \
  "/repos/svod011929/novera/contents/_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh" \
  > NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh

echo '85b5b6b54147e7d683777bb529ae4d7d937ac8de71f005180b85ec6d20eab415  NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh' \
  | sha256sum -c -

scp NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh root@YOUR_VPS:/root/
ssh root@YOUR_VPS 'bash NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh \
  --domain YOUR_DOMAIN --ip YOUR_PUBLIC_IP --owner-id YOUR_TELEGRAM_ID'
```

---

## After install

Public checks:

```bash
curl -fsS https://YOUR_DOMAIN/health
curl -fsS https://YOUR_DOMAIN/ready
```

Expected initially:

- `setup.status=bootstrap`
- `financial_ready=false`
- TLS via Let's Encrypt through Caddy

Owner steps:

1. Off-server backup of `/opt/gfort/state/secrets/runtime_config_key.txt`
2. Open Mini App as Owner → **Admin → System**
3. Validate RPC / WSS / seed / contract / scan block
4. Confirm derived treasury address → **Activate**
5. Enable only approved switches under **Admin → Terms**

Do **not** re-run the bootstrap installer on a host that already has `/opt/gfort`.

---

## Safe updates (existing VPS)

From a Windows operator machine with SSH key:

```powershell
# frontend-only (no API blink)
powershell -NoProfile -File scripts\safe_update_remote.ps1 -Mode frontend

# backend + frontend (short API blink, auto-rollback on /ready fail)
powershell -NoProfile -File scripts\safe_update_remote.ps1 -Mode full
```

On the VPS the script stages `/opt/gfort/releases/novera-update-<stamp>`, reuses `.env` + `/opt/gfort/state`, gates on public `/ready`, and rolls back on failure.

---

## Repository map

```
delta_backend/     FastAPI app, financial engine, encrypted runtime secrets
frontend/          Telegram Mini App (NOVERA brand)
deploy/            safe-update, backup, restore, bootstrap stub
scripts/           build + remote promote helpers
tests/             pytest (financial, security, bootstrap, admin)
_cursor_output/    decisions, reports, release manifests + pinned installer
_owner_inputs/     owner decision pack (accepted 2026-09-06)
```

Pinned installer:

| Artifact | Value |
|----------|-------|
| File | `_cursor_output/releases/NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh` |
| SHA-256 | `85b5b6b54147e7d683777bb529ae4d7d937ac8de71f005180b85ec6d20eab415` |
| Entrypoint | [`install.sh`](./install.sh) |

Superseded (do not use on Ubuntu 26.04): `…20260905-220159.sh`.

---

## Security posture

- No bot token / seed / RPC / WSS / master key in git
- Caddy is the only public entry; backend stays on isolated Docker networks
- Immutable `OWNER_IDS`; dynamic admins cannot activate chain or grant owners
- Runtime chain material: versioned AES-256-GCM bundle + separate master key
- Admin balance / referral-balance / referral-level require `Idempotency-Key`

---

## Local verify

```bash
python -m pytest -q
python -m compileall -q delta_backend main.py
```

---

## License / access

Private repository for the NOVERA operator. Do not publish tokens, seeds, or `runtime_config_key.txt`.
