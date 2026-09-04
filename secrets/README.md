# Runtime secrets

Create this file only on the VPS; never add its real contents to an archive,
Git repository, Mini App, support chat or Telegram message:

- `bot_token.txt`

The web-only release does not require RPC credentials, a token contract,
keystore, seed phrase or private key.

On the VPS, assign the files to `root:10001` with mode `0640`. The bundled
`deploy/vps-preflight.sh` does this without printing their contents.
