# NOVERA bootstrap checklist

This checklist does not authorize a production install.

## Before running the fresh-VPS installer

- [ ] Previously exposed bot token was revoked; a new token is ready
- [ ] VPS is Ubuntu/Debian and contains no `/opt/delta`, `/opt/gfort` or database
- [ ] `bnbb.tech` A record points to the expected VPS IPv4
- [ ] TCP 80/443 are free and reachable
- [ ] Host clock is NTP-synchronised (`timedatectl` → `synchronized: yes`);
  Telegram login fails when the server is > 300 s behind
- [ ] Installer SHA-256 matches its `.sha256` sidecar
- [ ] Owner Telegram ID is correct and controlled by the owner

## Installer acceptance

- [ ] Hidden prompt accepted the new bot token; token was never printed
- [ ] Embedded payload and critical SHA-256 manifest passed
- [ ] Docker/Caddy image built and import-compiled
- [ ] `/health` is `ok`
- [ ] `/ready` is `ready`, database is true, no failed tasks
- [ ] `/ready.setup.status` is `bootstrap`
- [ ] `/ready.setup.financial_ready` is false
- [ ] NOVERA UI and bot open for the immutable owner

## Owner setup in Admin → System

- [ ] Trusted device warning acknowledged before seed entry
- [ ] Production HTTPS RPC and WSS use public addresses
- [ ] BSC chain ID, contract and scan start block validate
- [ ] Derived treasury address is compared independently and re-entered exactly
- [ ] Activation uses newly opened Telegram Mini App (`initData` ≤ 5 minutes)
- [ ] Restart returns setup state `active` and `financial_ready=true`
- [ ] Only approved switches are enabled under Admin → Terms
- [ ] A 1 USDT real test payout is done only after treasury funding and owner review

## Backup and recovery

- [ ] `deploy/backup.sh` manifest verifies database and `*.runtime-config.enc`
- [ ] `runtime_config_key.txt` is backed up separately and securely
- [ ] Restore command is recorded but not run casually:
  `sudo env NOVERA_CONFIRM_RESTORE=RESTORE sh deploy/restore-backup.sh <backup.sqlite3>`
- [ ] Any `degraded` state leaves financial routes locked; investigate before reactivation
