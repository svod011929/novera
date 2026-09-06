# Bootstrap WSS/HTTP freshness under fail-closed setup

Date: 2026-09-06
Host: bnbb.tech / 170.168.91.129
Setup: `bootstrap`, `financial_ready=false`

## Expected behaviour while chain is off

- Mini App `/api/bootstrap`, notifications, admin reads and bot polling stay available.
- Deposit invoice creation and payout/referral withdrawals remain blocked by financial gates.
- Safety snapshot reports `status=ok` with no active alerts when chain workers are idle.
- `/ready` stays `ready` with `setup.status=bootstrap` even if no WSS session exists.
- Admin → System shows RPC/WSS as not configured until owner validate/activate.

## Verification commands

```bash
curl -fsS https://bnbb.tech/health
curl -fsS https://bnbb.tech/ready | jq .
cd /opt/gfort/current && docker compose -f compose.vps.yml logs --tail=40 delta | grep -Ei 'wss|rpc|safety|error' || true
```

## Code hardening deferred

No blockchain fallback code change is required while `CHAIN_ENABLED=false`.
After owner activation, re-check:

1. WSS disconnect does not freeze the Mini App HTTP API.
2. HTTP scan freshness alerts surface in `/api/admin/safety` without opening the safety circuit for unrelated routes.
3. Users can still open home/history/notifications during a temporary RPC blip.
