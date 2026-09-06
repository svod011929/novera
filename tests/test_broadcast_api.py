"""API tests for the I-10 broadcast safety surface.

Covers audience counts, the self-only test send and retry of failed
deliveries. No test in this file may create a delivery for a real audience
member other than the fixture users.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

httpx = pytest.importorskip("httpx")

from delta_backend.api import SlidingWindowRateLimiter, app, sanitize_telegram_html
from delta_backend.api_settings import MiniAppSettings
from delta_backend.config import Settings
from delta_backend.repository import DeltaRepository


TOKEN = "123456:TEST_TOKEN"
ADMIN_ID = 42
INVESTOR_ID = 100
PARTNER_ID = 101
CHILD_ID = 102
WALLET = "0x00000000000000000000000000000000000000Aa"


def signed_init_data(*, user_id: int = ADMIN_ID, username: str = "admin_user") -> str:
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


async def _prepare(tmp_path, *, admin_ids: str = str(ADMIN_ID)):
    business = MiniAppSettings(_env_file=None, demo_mode=False, force_https=False)
    chain = Settings(
        _env_file=None,
        bot_token=TOKEN,
        admin_ids=admin_ids,
        environment="testnet",
        chain_enabled=False,
        simulate_payouts=True,
    )
    repository = DeltaRepository(tmp_path / "broadcasts.sqlite3", business)
    await repository.connect()
    await repository.ensure_user(ADMIN_ID, "admin_user", "Admin", "ru")
    await repository.ensure_user(INVESTOR_ID, "investor", "Investor", "ru")
    await repository.ensure_user(PARTNER_ID, "partner", "Partner", "ru")
    await repository.ensure_user(CHILD_ID, "child", "Child", "ru")
    await repository.set_wallet(INVESTOR_ID, WALLET)
    await repository.admin_set_user_referrer(CHILD_ID, str(PARTNER_ID), ADMIN_ID)
    await repository.admin_open_investment(
        INVESTOR_ID,
        50_000_000,
        ADMIN_ID,
        "Fixture investor",
        "fixture_investor_open_1",
    )
    app.state.chain_settings = chain
    app.state.business = business
    app.state.repository = repository
    app.state.rate_limiter = SlidingWindowRateLimiter()
    return repository


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<b>Жирный</b>", "<b>Жирный</b>"),
        # Tags outside the allowlist are dropped, their text is kept.
        ("<div>Текст</div>", "Текст"),
        ("<b>Открыт", "<b>Открыт</b>"),
        ('<a href="https://novera.app">Ссылка</a>', '<a href="https://novera.app">Ссылка</a>'),
        ('<a href="javascript:alert(1)">Ссылка</a>', "Ссылка"),
        # Text escaping keeps quotes literal; only &, < and > are encoded.
        ("Ставка 10% & \"хвост\" <20", "Ставка 10% &amp; \"хвост\" &lt;20"),
    ],
)
def test_sanitize_telegram_html_contract(raw: str, expected: str) -> None:
    """Pins the contract the Mini App composer preview mirrors in JS."""
    assert sanitize_telegram_html(raw) == expected


@pytest.mark.asyncio
async def test_broadcast_audience_counts_match_delivery_targets(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.get("/api/admin/broadcasts/audience", headers=headers)
            assert response.status_code == 200
            counts = response.json()

        assert counts["all"] == 4
        assert counts["investors"] == 1
        assert counts["partners"] == 1

        # The counts must describe exactly what create_broadcast would enqueue.
        for audience, expected in counts.items():
            created = await repository.create_broadcast(
                ADMIN_ID,
                f"Audience check {audience}",
                audience,
            )
            assert created["total_count"] == expected
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_broadcast_test_send_reaches_only_the_acting_admin(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post(
                "/api/admin/broadcasts/test",
                headers=headers,
                json={"message": "<b>Проверка</b><div>текст</div>"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["queued"] is True
            assert body["recipient_id"] == ADMIN_ID

            # A test must never create a broadcast targeting an audience.
            listing = await client.get("/api/admin/broadcasts", headers=headers)
            assert listing.status_code == 200
            assert listing.json() == []

            blank = await client.post(
                "/api/admin/broadcasts/test",
                headers=headers,
                json={"message": "   "},
            )
            assert blank.status_code == 422

        admin_inbox = await repository.list_notifications(ADMIN_ID, limit=10)
        assert [item["event_type"] for item in admin_inbox["items"]] == ["admin_broadcast_test"]
        assert admin_inbox["items"][0]["body"] == "Проверкатекст"

        # sanitize_telegram_html drops a tag outside the allowlist but keeps its
        # text, so the composer preview must render the same way.
        queued_tests = []
        while (delivery := await repository.claim_next_notification_delivery()) is not None:
            if delivery["event_type"] == "admin_broadcast_test":
                queued_tests.append(delivery)
        assert len(queued_tests) == 1
        assert int(queued_tests[0]["user_id"]) == ADMIN_ID
        assert queued_tests[0]["telegram_html"] == "<b>Проверка</b>текст"

        for other in (INVESTOR_ID, PARTNER_ID, CHILD_ID):
            events = [
                item["event_type"]
                for item in (await repository.list_notifications(other, limit=10))["items"]
            ]
            assert "admin_broadcast_test" not in events
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_broadcast_retry_requeues_only_failed_recipients(tmp_path) -> None:
    repository = await _prepare(tmp_path)
    headers = {"X-Telegram-Init-Data": signed_init_data()}
    try:
        created = await repository.create_broadcast(ADMIN_ID, "Hello", "all")
        broadcast_id = int(created["id"])

        delivered_id: int | None = None
        failed_ids: list[int] = []
        for index in range(int(created["total_count"])):
            delivery = await repository.claim_next_broadcast_delivery()
            assert delivery is not None
            if index == 0:
                delivered_id = int(delivery["id"])
                await repository.finish_broadcast_delivery(delivered_id, delivered=True)
            else:
                failed_ids.append(int(delivery["id"]))
                await repository.finish_broadcast_delivery(
                    int(delivery["id"]),
                    delivered=False,
                    error="TelegramForbiddenError",
                )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            listing = await client.get("/api/admin/broadcasts", headers=headers)
            before = listing.json()[0]
            assert before["delivered_count"] == 1
            assert before["failed_count"] == len(failed_ids)
            assert before["pending_count"] == 0
            assert before["last_error"] == "TelegramForbiddenError"

            response = await client.post(
                f"/api/admin/broadcasts/{broadcast_id}/retry",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json() == {
                "requeued": len(failed_ids),
                "pending": len(failed_ids),
            }

            after = (await client.get("/api/admin/broadcasts", headers=headers)).json()[0]
            assert after["status"] == "queued"
            assert after["delivered_count"] == 1
            assert after["failed_count"] == 0
            assert after["pending_count"] == len(failed_ids)

            missing = await client.post("/api/admin/broadcasts/999999/retry", headers=headers)
            assert missing.status_code == 404

        # The already delivered recipient must not be queued again.
        requeued: set[int] = set()
        while (delivery := await repository.claim_next_broadcast_delivery()) is not None:
            requeued.add(int(delivery["id"]))
        assert requeued == set(failed_ids)
        assert delivered_id not in requeued
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_broadcast_endpoints_reject_non_admin(tmp_path) -> None:
    repository = await _prepare(tmp_path, admin_ids=str(ADMIN_ID))
    headers = {"X-Telegram-Init-Data": signed_init_data(user_id=INVESTOR_ID, username="investor")}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            assert (
                await client.get("/api/admin/broadcasts/audience", headers=headers)
            ).status_code == 403
            assert (
                await client.post(
                    "/api/admin/broadcasts/test",
                    headers=headers,
                    json={"message": "hi"},
                )
            ).status_code == 403
            assert (
                await client.post("/api/admin/broadcasts/1/retry", headers=headers)
            ).status_code == 403

        events = [
            item["event_type"]
            for item in (await repository.list_notifications(INVESTOR_ID, limit=10))["items"]
        ]
        assert "admin_broadcast_test" not in events
    finally:
        await repository.close()
