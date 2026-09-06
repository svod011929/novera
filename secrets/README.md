# Runtime secrets

Create this file only on the VPS; never add its real contents to an archive,
Git repository, Mini App, support chat or Telegram message:

- `bot_token.txt`
- `runtime_config_key.txt` — installer-generated 32-byte key encoded as base64

The bootstrap release does not require RPC/WSS credentials or signing material
at install time. Owner setup writes a single AES-256-GCM encrypted generation
under `data/runtime_secrets`; plaintext seed/RPC/WSS values are never written
to `.env`, SQLite or a backup manifest.

On the VPS, assign the files to `root:10001` with mode `0640`. The bundled
`deploy/vps-preflight.sh` does this without printing their contents.

Back up the runtime configuration key separately from normal database backups.
Without that key an encrypted chain generation cannot be restored.
