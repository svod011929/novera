import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

httpx = pytest.importorskip("httpx")

from delta_backend.api import (
    SESSION_COOKIE_NAME,
    SessionExchangeRequest,
    SlidingWindowRateLimiter,
    app,
    exchange_bot_login,
    issue_web_session,
)
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository
from delta_backend.telegram_auth import TelegramUser


TOKEN = "123456:TEST_TOKEN"


def signed_init_data(*, user_id: int = 42, username: str = "delta_user") -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "signature": "telegram-third-party-signature",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": f"User {user_id}",
                "username": username,
                "language_code": "ru",
            },
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def test_authenticated_api_and_disabled_deposit_gate(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None, demo_mode=False)
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids="42",
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
    )
    repository = DeltaRepository(tmp_path / "api.sqlite3", business)
    await repository.connect()
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            headers = {"X-Telegram-Init-Data": signed_init_data()}
            response = await client.get("/api/bootstrap", headers=headers)
            assert response.status_code == 200
            assert response.json()["auth"]["is_admin"] is True
            assert response.json()["mode"]["web_only"] is True

            wallet = "0x0000000000000000000000000000000000000001"
            response = await client.post(
                "/api/wallet",
                headers=headers,
                json={"address": wallet},
            )
            assert response.status_code == 503
            assert response.json()["detail"] == (
                "Wallet configuration is disabled in web-only mode"
            )

            response = await client.post(
                "/api/deposits/invoice",
                headers={**headers, "Idempotency-Key": "invoice-api-test-0001"},
                json={"amount": 10},
            )
            assert response.status_code == 503
            assert response.json()["detail"] == "Deposits are temporarily disabled"
    finally:
        await repository.close()


async def test_current_telegram_init_data_overrides_shared_cookie(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None, demo_mode=False, force_https=False)
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids="",
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
    )
    repository = DeltaRepository(tmp_path / "account-switch.sqlite3", business)
    await repository.connect()
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    cookie_user = TelegramUser(
        id=101,
        username="first_account",
        first_name="First",
        language_code="ru",
    )
    shared_cookie = issue_web_session(cookie_user, TOKEN, 3600)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            client.cookies.set(SESSION_COOKIE_NAME, shared_cookie)
            response = await client.get(
                "/api/bootstrap",
                headers={
                    "X-Telegram-Init-Data": signed_init_data(
                        user_id=202,
                        username="second_account",
                    )
                },
            )
            assert response.status_code == 200
            assert response.json()["auth"]["telegram_id"] == 202
            assert SESSION_COOKIE_NAME not in client.cookies

            # A malformed current-account header must fail closed. It must not
            # silently fall back to a cookie that could belong to another user.
            client.cookies.set(SESSION_COOKIE_NAME, shared_cookie)
            bad_header = signed_init_data(user_id=202, username="second_account") + "x"
            response = await client.get(
                "/api/bootstrap",
                headers={"X-Telegram-Init-Data": bad_header},
            )
            assert response.status_code == 401

            # Cookie-only authentication remains available for external-browser
            # one-time login links where Telegram initData is genuinely absent.
            client.cookies.set(SESSION_COOKIE_NAME, shared_cookie)
            response = await client.get("/api/bootstrap")
            assert response.status_code == 200
            assert response.json()["auth"]["telegram_id"] == 101
    finally:
        await repository.close()


async def test_native_login_token_cannot_switch_telegram_account(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None, demo_mode=False, force_https=False)
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids="",
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
    )
    repository = DeltaRepository(tmp_path / "login-token-account.sqlite3", business)
    await repository.connect()
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    request = type("Request", (), {"app": app})()
    try:
        token = await repository.create_web_login_token(
            TelegramUser(101, "first_account", "First", "ru", "ref_999")
        )
        with pytest.raises(Exception) as caught:
            await exchange_bot_login(
                SessionExchangeRequest(token=token),
                request,
                signed_init_data(user_id=202, username="second_account"),
            )
        assert getattr(caught.value, "status_code", None) == 409

        token = await repository.create_web_login_token(
            TelegramUser(202, "second_account", "Second", "ru", None)
        )
        response = await exchange_bot_login(
            SessionExchangeRequest(token=token),
            request,
            signed_init_data(user_id=202, username="second_account"),
        )
        assert response.status_code == 200
        assert b'"mode":"telegram"' in response.body
        assert "Max-Age=0" in response.headers.get("set-cookie", "")
    finally:
        await repository.close()
