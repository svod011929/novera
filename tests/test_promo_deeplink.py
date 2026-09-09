"""Promo deep-link parse + invoice status + campaign bot link."""

from __future__ import annotations

import time

import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.models import TransferEvent
from delta_backend.repository import (
    DEFAULT_PROMO_CAMPAIGN_MESSAGE,
    DeltaRepository,
    parse_promo_start_param,
    render_campaign_message,
)

WALLET_ONE = "0x0000000000000000000000000000000000000001"
WALLET_TWO = "0x0000000000000000000000000000000000000002"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("promo_WELCOME10", "WELCOME10"),
        ("promo-welcome10", "WELCOME10"),
        ("PROMO_AbC", "ABC"),
        ("Promo_x", "X"),
        ("ref_123", None),
        ("REF_123", None),
        ("", None),
        (None, None),
        ("promo_", None),
        ("promo-", None),
        ("hello", None),
        ("promo_" + ("A" * 33), None),
    ],
)
def test_parse_promo_start_param(raw, expected) -> None:
    assert parse_promo_start_param(raw) == expected


def test_default_promo_campaign_message_has_bot_deep_link() -> None:
    assert "start=promo_{{code}}" in DEFAULT_PROMO_CAMPAIGN_MESSAGE
    assert "{{bot_username}}" in DEFAULT_PROMO_CAMPAIGN_MESSAGE


def test_render_campaign_message_bot_username() -> None:
    promo = {
        "code": "SAVE10",
        "bonus_type": "percent",
        "bonus_bps": 1000,
        "bonus_fixed_minor": 0,
    }
    rendered = render_campaign_message(
        "https://t.me/{{bot_username}}?start=promo_{{code}} {{bonus_label}}",
        promo,
        bot_username="@NoveraBot",
    )
    assert "https://t.me/NoveraBot?start=promo_SAVE10" in rendered
    assert "10%" in rendered
    assert "{{" not in rendered


async def test_get_user_invoice_status_ownership_and_credit(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "inv.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "u1", "One", "ru")
        await repo.ensure_user(2, "u2", "Two", "ru")
        await repo.set_wallet(1, WALLET_TWO)
        await repo.set_wallet(2, WALLET_TWO)

        inv = await repo.create_invoice(1, usdt_to_minor(10), idempotency_key="k1")
        invoice_id = int(inv["invoice_id"])
        pending = await repo.get_user_invoice(1, invoice_id)
        assert pending is not None
        assert pending["status"] == "pending"
        assert pending["credited"] is False
        assert pending["deposit_id"] is None
        assert await repo.get_user_invoice(2, invoice_id) is None

        paid = await repo.apply_transfer(
            TransferEvent(
                chain_id=97,
                tx_hash="0x" + "a" * 64,
                log_index=1,
                block_number=101,
                from_address=WALLET_TWO,
                to_address=WALLET_ONE,
                amount_atomic=int(inv["exact_minor"]) * 10**12,
                amount_minor=int(inv["exact_minor"]),
            )
        )
        assert paid["matched"] is True
        credited = await repo.get_user_invoice(1, invoice_id)
        assert credited is not None
        assert credited["status"] == "paid"
        assert credited["credited"] is True
        assert int(credited["deposit_id"]) == int(paid["deposit_id"])
    finally:
        await repo.close()


async def test_get_user_invoice_treats_ttl_as_expired(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "exp.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "u1", "One", "ru")
        await repo.set_wallet(1, WALLET_TWO)
        inv = await repo.create_invoice(1, usdt_to_minor(10), idempotency_key="k-exp")
        invoice_id = int(inv["invoice_id"])
        past = int(time.time()) - 10
        connection = repo._connection()
        async with repo._lock:
            await connection.execute(
                "UPDATE deposit_invoices SET expires_at = ? WHERE id = ?",
                (past, invoice_id),
            )
            await connection.commit()
        row = await repo.get_user_invoice(1, invoice_id)
        assert row is not None
        assert row["status"] == "expired"
        assert row["credited"] is False
    finally:
        await repo.close()


async def test_dispatch_promo_campaign_injects_bot_deep_link(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None, bot_username="@LiveBot")
    repo = DeltaRepository(tmp_path / "camp.sqlite3", business)
    await repo.connect()
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        promo = await repo.admin_create_promo_code(
            code="LINKME",
            bonus_type="percent",
            bonus_bps=500,
            bonus_fixed_minor=0,
            max_redemptions=10,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=1,
        )
        campaign = await repo.admin_create_campaign(
            kind="promo",
            audience="all",
            schedule_mode="interval",
            interval_hours=24,
            message_html="",
            promo_code_id=int(promo["id"]),
            created_by=1,
            next_run_at=int(time.time()) - 60,
        )
        result = await repo.dispatch_campaign(int(campaign["id"]))
        assert result["status"] == "sent"
        message = str(
            next(
                row
                for row in await repo.admin_broadcasts()
                if int(row["id"]) == int(result["broadcast_id"])
            )["message"]
        )
        assert "https://t.me/LiveBot?start=promo_LINKME" in message
        assert "LINKME" in message
        assert "{{" not in message
    finally:
        await repo.close()
