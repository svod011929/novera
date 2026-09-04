# GFORT Mini App — production BSC Mainnet package

Self-contained VPS release for `https://bnbb.tech/`. The production installer stores the Telegram token, RPC/WSS credentials and signing mnemonic in Docker secret files under `/opt/delta/secrets` and never writes them to `.env`.

Mainnet settings used by this build:
- BNB Smart Chain chain id `56`;
- USDT/BSC contract `0x55d398326f99059fF775485246999027B3197955`;
- HTTPS/WSS RPC supplied at install time;
- treasury address validated against the supplied mnemonic before startup;
- scan start block captured from the live RPC at installation;
- Caddy terminates HTTPS and serves the Mini App on the same origin.

The installer performs configuration, RPC/contract/wallet startup checks, Docker health checks and public `/health` + `/ready` checks.

Docker networking: the backend is not published on the host. It joins an internal backend network for Caddy traffic and a separate unexposed egress network for BSC RPC/WSS and Telegram API access.
