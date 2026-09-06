# NOVERA Mini App — secure owner bootstrap

The one-file installer prepares a clean Ubuntu/Debian VPS for
`https://bnbb.tech/`. It asks for a newly issued Telegram bot token with hidden
input, creates the runtime encryption key, installs Docker/Caddy, starts the
bot and Mini App, and verifies public HTTPS plus `/health` and `/ready`.

The initial production state is deliberately fail-closed:
- immutable owner is configured through `OWNER_IDS`;
- chain, deposits, payouts, investments and referrals are off;
- simulation and demo modes are off;
- RPC, WSS and signer material are absent from the installer and `.env`;
- financial routes stay locked until an owner activation reaches `active`.

The owner completes blockchain setup under **Admin → System**:
1. enter HTTPS RPC, WSS, token contract, scan start block and seed;
2. validate both providers and the signer;
3. compare and re-enter the derived treasury address;
4. activate with fresh Telegram `initData`;
5. enable only approved financial switches under **Admin → Terms**.

Runtime RPC/WSS/seed values are stored as one versioned AES-256-GCM bundle.
SQLite contains only setup status, generation and redacted audit metadata.
Backups include the database and encrypted active generation; the master key
must be backed up separately.

The backend is not published directly on the host. Caddy is the only public
entry point, while the backend uses isolated internal and egress networks.
