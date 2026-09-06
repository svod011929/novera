"""I-11 security hardening: IDOR, non-admin matrix, auth fail-closed, XSS sinks."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

httpx = pytest.importorskip("httpx")

from delta_backend.api import (
    SlidingWindowRateLimiter,
    app,
    issue_web_session,
    sanitize_telegram_html,
)
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository
from delta_backend.telegram_auth import TelegramUser


TOKEN = "123456:TEST_TOKEN"
ADMIN_ID = 42
USER_A = 100
USER_B = 200
WALLET_A = "0x00000000000000000000000000000000000000Aa"
WALLET_B = "0x00000000000000000000000000000000000000Bb"


def signed_init_data(
    *,
    user_id: int,
    username: str = "user",
    auth_date: int | None = None,
) -> str:
    values = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
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


async def _prepare(tmp_path, *, admin_ids: str = str(ADMIN_ID)):
    business = MiniAppSettings(
        _env_file=None,
        demo_mode=False,
        force_https=False,
        telegram_init_data_ttl_seconds=86_400,
    )
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids=admin_ids,
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
    )
    repository = DeltaRepository(tmp_path / "security.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(ADMIN_ID, "admin", "Admin", "ru")
    await repository.ensure_user(USER_A, "alpha", "Alpha", "ru")
    await repository.ensure_user(USER_B, "beta", "Beta", "ru")
    await repository.set_wallet(USER_A, WALLET_A)
    await repository.set_wallet(USER_B, WALLET_B)
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    return repository, business


@pytest.mark.asyncio
async def test_notification_read_is_not_idor(tmp_path) -> None:
    repository, _ = await _prepare(tmp_path)
    try:
        async with repository.transaction() as connection:
            await repository._queue_notification(
                connection,
                user_id=USER_A,
                category="system",
                event_type="private_note",
                title="<img src=x onerror=alert(1)>Secret A",
                body="Body <script>alert(1)</script>A",
                telegram_html="<b>Secret A</b>",
                dedupe_key="private-a-1",
            )
            await repository._queue_notification(
                connection,
                user_id=USER_B,
                category="system",
                event_type="private_note",
                title="Secret B",
                body="Body B",
                telegram_html="<b>Secret B</b>",
                dedupe_key="private-b-1",
            )

        a_list = await repository.list_notifications(USER_A, limit=10)
        b_list = await repository.list_notifications(USER_B, limit=10)
        a_id = int(a_list["items"][0]["id"])
        b_id = int(b_list["items"][0]["id"])

        # Hostile markup is stored as plain text for Mini App rendering (escaped
        # by the frontend esc()). Titles/bodies are not HTML-sanitized on write.
        assert "<script>" in a_list["items"][0]["body"]
        assert a_list["items"][0]["title"].startswith("<img")

        headers_a = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_A, username="alpha")}
        headers_b = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_B, username="beta")}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            own = await client.get("/api/notifications", headers=headers_a)
            assert own.status_code == 200
            titles = [item["title"] for item in own.json()["items"]]
            assert any("Secret A" in title for title in titles)
            assert all("Secret B" not in title for title in titles)

            foreign = await client.post(
                f"/api/notifications/{b_id}/read",
                headers=headers_a,
            )
            assert foreign.status_code == 200
            assert foreign.json() == {"read": False}

            own_read = await client.post(
                f"/api/notifications/{a_id}/read",
                headers=headers_a,
            )
            assert own_read.status_code == 200
            assert own_read.json() == {"read": True}

            # Victim's unread state is unchanged by the foreign attempt.
            victim = await client.get("/api/notifications", headers=headers_b)
            assert victim.status_code == 200
            unread = [item for item in victim.json()["items"] if not item.get("read_at")]
            assert any(item["id"] == b_id for item in unread)
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_bootstrap_and_team_do_not_leak_other_users(tmp_path) -> None:
    repository, _ = await _prepare(tmp_path)
    try:
        await repository.ensure_user(201, "child", "Child", "ru", referrer_id=USER_A)
        headers_a = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_A, username="alpha")}
        headers_b = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_B, username="beta")}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            boot_a = await client.get("/api/bootstrap", headers=headers_a)
            boot_b = await client.get("/api/bootstrap", headers=headers_b)
            assert boot_a.status_code == 200 and boot_b.status_code == 200
            assert boot_a.json()["auth"]["telegram_id"] == USER_A
            assert boot_b.json()["auth"]["telegram_id"] == USER_B
            assert boot_a.json()["user"]["payout_address"].lower() == WALLET_A.lower()
            assert boot_b.json()["user"]["payout_address"].lower() == WALLET_B.lower()

            team_a = await client.get("/api/team", headers=headers_a)
            team_b = await client.get("/api/team", headers=headers_b)
            assert team_a.status_code == 200 and team_b.status_code == 200
            member_ids = {int(m["telegram_id"]) for m in team_a.json().get("members", [])}
            assert 201 in member_ids
            assert USER_B not in member_ids
            assert team_b.json().get("members", []) == []
    finally:
        await repository.close()


ADMIN_MUTATIONS = [
    ("GET", "/api/admin/summary", None),
    ("GET", "/api/admin/users", None),
    ("GET", f"/api/admin/users/{USER_A}", None),
    ("POST", f"/api/admin/users/{USER_A}/block", {"blocked": True}),
    ("POST", f"/api/admin/users/{USER_A}/balance", {"balance_usdt": "1", "reason": "x"}),
    ("POST", f"/api/admin/users/{USER_A}/wallet", {"address": WALLET_B}),
    (
        "POST",
        f"/api/admin/users/{USER_A}/referral-level",
        {"unlocked_level": 1, "reason": "x"},
    ),
    (
        "POST",
        f"/api/admin/users/{USER_A}/investments",
        {
            "amount_usdt": "10",
            "reason": "x",
            "operation_id": "security_invest_0001",
            "confirm": "OPEN_INVESTMENT",
        },
    ),
    ("GET", "/api/admin/settings", None),
    ("GET", "/api/admin/treasury", None),
    ("GET", "/api/admin/audit", None),
    ("POST", "/api/admin/broadcasts", {"message": "hi", "audience": "all", "buttons": []}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", ADMIN_MUTATIONS)
async def test_admin_routes_reject_non_admin(
    tmp_path, method: str, path: str, payload: dict | None
) -> None:
    repository, _ = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data(user_id=USER_A, username="alpha")}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            if method == "GET":
                response = await client.get(path, headers=headers)
            else:
                response = await client.post(path, headers=headers, json=payload or {})
            assert response.status_code == 403, path

        # Side-effect free: no investment, no broadcast, no balance change.
        detail = await repository.admin_user_detail(USER_A)
        assert detail is not None
        assert detail["user"]["manual_balance_minor"] == 0
        assert detail["deposits"] == []
        assert await repository.admin_broadcasts() == []
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_session_preferred_over_conflicting_init_data(tmp_path) -> None:
    """Documented V10 behaviour: valid SecureStorage session wins over stale initData.

    Telegram WebViews may reuse old initData after an account switch; the
    per-user session token is the intended identity source. Frontend I-04
    clears the token when live initData uid conflicts — server keeps session.
    """
    repository, business = await _prepare(tmp_path)
    session = issue_web_session(
        TelegramUser(id=USER_A, username="alpha", first_name="Alpha", language_code="ru"),
        TOKEN,
        3600,
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.get(
                "/api/bootstrap",
                headers={
                    "X-NOVERA-Session": session,
                    "X-NOVERA-Telegram-Context": "1",
                    "X-Telegram-Init-Data": signed_init_data(
                        user_id=USER_B, username="beta"
                    ),
                },
            )
            assert response.status_code == 200
            assert response.json()["auth"]["telegram_id"] == USER_A
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_expired_init_data_fails_closed_without_fallback(tmp_path) -> None:
    repository, business = await _prepare(tmp_path)
    foreign_session = issue_web_session(
        TelegramUser(id=USER_B, username="beta", first_name="Beta", language_code="ru"),
        TOKEN,
        3600,
    )
    expired = signed_init_data(
        user_id=USER_A,
        username="alpha",
        auth_date=int(time.time()) - business.telegram_init_data_ttl_seconds - 10,
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            # Native context + expired initData and no usable own session → 401.
            # Cookie must not resurrect a foreign identity in native mode.
            client = httpx.AsyncClient(
                transport=transport,
                base_url="http://localhost",
                cookies={"delta_session": foreign_session},
            )
            async with client:
                response = await client.get(
                    "/api/bootstrap",
                    headers={
                        "X-Telegram-Init-Data": expired,
                        "X-NOVERA-Telegram-Context": "1",
                    },
                )
                assert response.status_code == 401
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_login_token_cannot_be_replayed(tmp_path) -> None:
    repository, _ = await _prepare(tmp_path)
    user = TelegramUser(id=USER_A, username="alpha", first_name="Alpha", language_code="ru")
    token = await repository.create_web_login_token(user, ttl_seconds=600)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            first = await client.post(
                "/api/session/exchange",
                json={"token": token},
                headers={"X-NOVERA-Telegram-Context": "1"},
            )
            assert first.status_code == 200
            assert first.json()["status"] == "ok"
            assert first.json()["mode"] == "telegram"
            assert first.json()["session_token"]

            second = await client.post(
                "/api/session/exchange",
                json={"token": token},
                headers={"X-NOVERA-Telegram-Context": "1"},
            )
            assert second.status_code == 401
    finally:
        await repository.close()


@pytest.mark.parametrize(
    ("raw", "forbidden_substring"),
    [
        ('<a href="javascript:alert(1)">x</a>', "javascript:"),
        ('<a href="JaVaScRiPt:alert(1)">x</a>', "javascript:"),
        ("<img src=x onerror=alert(1)>", "<img"),
        ("<svg/onload=alert(1)>", "<svg"),
        ('<a href="data:text/html,hi">x</a>', "data:"),
    ],
)
def test_sanitize_telegram_html_blocks_common_xss_vectors(
    raw: str, forbidden_substring: str
) -> None:
    cleaned = sanitize_telegram_html(raw).lower()
    assert forbidden_substring.lower() not in cleaned
