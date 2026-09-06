from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

httpx = pytest.importorskip("httpx")

from delta_backend.api import ChainSetupRuntime, SlidingWindowRateLimiter, app
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository


TOKEN = "123456:BOOTSTRAP_TEST_TOKEN"
OWNER_ID = 42
USER_ID = 100


def _init_data(user_id: int = OWNER_ID) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "bootstrap-query",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Owner",
                "username": "owner",
                "language_code": "ru",
            },
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.mark.asyncio
async def test_production_bootstrap_locks_liability_mutations(tmp_path) -> None:
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=False,
        miniapp_url="https://example.test",
        miniapp_origin="https://example.test",
        trusted_hosts="example.test,localhost",
    )
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        owner_ids=str(OWNER_ID),
        admin_ids=str(OWNER_ID),
        environment="production",
        chain_enabled=False,
        simulate_payouts=False,
        deposits_enabled=False,
        investments_enabled=False,
        payouts_enabled=False,
        referral_enabled=False,
    )
    repository = DeltaRepository(tmp_path / "bootstrap.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(OWNER_ID, "owner", "Owner", "ru")
    await repository.ensure_user(USER_ID, "member", "Member", "ru")
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.chain_setup = ChainSetupRuntime(status="bootstrap", financial_ready=False)
    app.state.rate_limiter = SlidingWindowRateLimiter()
    headers = {"X-Telegram-Init-Data": _init_data()}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            balance = await client.post(
                f"/api/admin/users/{USER_ID}/balance",
                headers={**headers, "Idempotency-Key": "bootstrap-block-balance-1"},
                json={"balance_usdt": "10", "reason": "Bootstrap must reject"},
            )
            referral = await client.post(
                f"/api/admin/users/{USER_ID}/referral-balance",
                headers={**headers, "Idempotency-Key": "bootstrap-block-referral-1"},
                json={"balance_usdt": "10", "reason": "Bootstrap must reject"},
            )
            investment = await client.post(
                f"/api/admin/users/{USER_ID}/investments",
                headers=headers,
                json={
                    "amount_usdt": "10",
                    "reason": "Bootstrap must reject",
                    "operation_id": "bootstrap-block-0001",
                    "confirm": "OPEN_INVESTMENT",
                },
            )
        assert {balance.status_code, referral.status_code, investment.status_code} == {503}
        assert "owner activation" in balance.json()["detail"].lower()
        summary = await repository.admin_summary()
        assert summary["active_deposits"] == 0
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_bootstrap_cannot_enable_financial_switches(tmp_path) -> None:
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=False,
        miniapp_url="https://example.test",
        miniapp_origin="https://example.test",
        trusted_hosts="example.test,localhost",
    )
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        owner_ids=str(OWNER_ID),
        admin_ids=str(OWNER_ID),
        environment="production",
        chain_enabled=False,
        simulate_payouts=False,
        deposits_enabled=False,
        investments_enabled=False,
        payouts_enabled=False,
        referral_enabled=False,
    )
    repository = DeltaRepository(tmp_path / "settings.sqlite3", business)
    await repository.connect()
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.chain_setup = ChainSetupRuntime(status="bootstrap", financial_ready=False)
    app.state.rate_limiter = SlidingWindowRateLimiter()
    headers = {"X-Telegram-Init-Data": _init_data()}
    payload = {
        "daily_profit_bps": 1000,
        "payout_days": 20,
        "deposit_min_usdt": 10,
        "deposit_max_usdt": 100000,
        "invoice_ttl_minutes": 30,
        "referral_level_bps": [800, 400, 250, 150, 100],
        "referral_personal_thresholds_usdt": [50, 100, 300, 500, 1000],
        "referral_line_thresholds_usdt": [100, 300, 500, 1500, 5000],
        "deposits_enabled": True,
        "investments_enabled": True,
        "payouts_enabled": True,
        "referral_enabled": True,
        "confirmation_blocks": 12,
        "deposit_scan_interval_seconds": 60,
        "support_url": "https://t.me/support",
        "chat_url": "https://t.me/chat",
    }
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/api/admin/settings",
                headers=headers,
                json=payload,
            )
        assert response.status_code == 409
        assert chain.deposits_enabled is False
        assert chain.payouts_enabled is False
    finally:
        await repository.close()
