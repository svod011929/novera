# NOVERA one-file bootstrap release

## Final artifact

- File: `releases/NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh`
- SHA-256: `85b5b6b54147e7d683777bb529ae4d7d937ac8de71f005180b85ec6d20eab415`
- Sidecar: `releases/NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh.sha256`
- Manifest: `releases/BOOTSTRAP_MANIFEST_20260906-091454.txt`

The artifact contains no runtime bot token, RPC/WSS value, seed, encryption key,
`.env` or database.

Superseded: `NOVERA_BOOTSTRAP_INSTALLER_20260905-220159.sh` fails on
Ubuntu 26.04 (uutils `install -o/-g` rejects numeric IDs) and must not be used.

## Installation command

Copy the installer to a clean Ubuntu/Debian VPS with an NTP-synchronised clock,
then run:

```bash
sha256sum NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh
sudo bash NOVERA_BOOTSTRAP_INSTALLER_20260906-091454.sh \
  --domain bnbb.tech \
  --ip 170.168.91.129 \
  --owner-id 8054710484
```

The installer asks for the bot token with hidden input (or reads
`NOVERA_BOT_TOKEN_FILE` for unattended runs). It refuses an existing
`/opt/delta`, `/opt/gfort` or production database, and fails closed when the
host clock differs from Telegram by more than 120 s.

## Production installation — 2026-09-06

Performed over SSH on `170.168.91.129` (Ubuntu 26.04 LTS, 2 vCPU / 2 GB).

- Release: `/opt/gfort/releases/novera-bootstrap-20260906-091637`
- Persistent state: `/opt/gfort/state` (`data/`, `backups/`, `secrets/`)
- Image: `novera-app:novera-bootstrap-20260906-091637` (356 MB), `caddy:2-alpine`
- `https://bnbb.tech/health` → `status=ok`, `setup_status=bootstrap`
- `https://bnbb.tech/ready` → `ready`, `database=true`,
  `setup.financial_ready=false`, `safety.status=ok`
- TLS: Let's Encrypt, `CN=bnbb.tech`, valid 2026-09-06 → 2026-12-05;
  HTTP → HTTPS 308
- Secrets `bot_token.txt` / `runtime_config_key.txt`: `640 root:10001`;
  release tree contains no world-writable entries
- Bot polling confirmed (aiogram updates handled by bot id 8957435332)

Host fixes applied before the install:

- VPS clock was 619 s behind (kvm-clock, default Ubuntu NTP pools
  unreachable). chrony now uses `time.cloudflare.com iburst nts`
  (`/etc/chrony/sources.d/novera-reachable.sources`); clock stepped, RTC
  synced, `System clock synchronized: yes`.
- Leftover of an aborted 11:36 attempt (extracted payload only, no secrets or
  data) moved to `/root/gfort.aborted-20260906-083629`.

## Result

The installer brings up NOVERA, the Telegram bot, Caddy and TLS in `bootstrap`
state. Chain, deposits, payouts, investments and referrals remain off.

The immutable owner completes **Admin → System**:

1. validate public RPC/WSS, contract, scan block and seed;
2. compare and re-enter the derived treasury address;
3. activate with fresh Telegram initData;
4. after restart, enable approved financial switches under **Admin → Terms**.

Secrets are stored in one versioned AES-256-GCM bundle. Activation uses atomic
replacement and retains a previous generation for rollback. Startup failure
returns to a non-financial `degraded` control plane.

## Verification completed

- Python compile: PASS
- Full pytest: **90 passed, 0 failed**
- Modern JavaScript parse: PASS
- Shell grammar parse: PASS
- Embedded payload decode/hash/file round-trip: PASS (74 payload files)
- Token-shaped literal scan outside tests: PASS
- IDE diagnostics: no errors
- Rebuilt 2026-09-06 after the uutils fix: shell grammar parse PASS,
  `tests/test_bootstrap_release.py` 4/4, full pytest 90/90, installer
  end-to-end on the production VPS PASS (all steps `[OK]`, exit 0)
