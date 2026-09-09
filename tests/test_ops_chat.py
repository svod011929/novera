"""Unit tests for ops chat HTML formatting and settings resolve."""

from __future__ import annotations

import pytest

from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository
from delta_backend.services.ops_chat import (
    format_deposit_ops_html,
    format_payout_ops_html,
    format_user_line,
    payout_kind_label,
)


def test_format_user_line_prefers_username() -> None:
    assert format_user_line(telegram_id=1, username="Alice", first_name="A") == "@Alice"


def test_format_user_line_escapes_html() -> None:
    assert "<" not in format_user_line(
        telegram_id=1, username=None, first_name="<b>x</b>"
    )


def test_format_deposit_with_and_without_tx() -> None:
    with_tx = format_deposit_ops_html(
        telegram_id=42,
        username="bob",
        first_name=None,
        amount_minor=usdt_to_minor("10.5"),
        deposit_id=7,
        tx_hash="0xabc",
    )
    assert "Новый депозит" in with_tx
    assert "@bob" in with_tx
    assert "bscscan.com/tx/0xabc" in with_tx
    assert "админ" not in with_tx.lower()

    without = format_deposit_ops_html(
        telegram_id=42,
        username=None,
        first_name="Bob",
        amount_minor=usdt_to_minor("10"),
        deposit_id=8,
        tx_hash=None,
    )
    assert "Транзакция" not in without
    assert "Bob" in without


def test_format_payout_includes_explorer_link() -> None:
    tx = "0x5873880ad0392d90fe2388b0010c10d84a091b03aa346d557245cfdf1b6648dc"
    text = format_payout_ops_html(
        telegram_id=9,
        username="carol",
        first_name=None,
        amount_minor=usdt_to_minor("1.25"),
        tx_hash=tx,
        kind="daily",
        subtype=None,
    )
    assert "Выплата" in text
    assert "дневная" in text
    assert f"https://bscscan.com/tx/{tx}" in text
    assert "@carol" in text


def test_payout_kind_labels() -> None:
    assert payout_kind_label("referral", None) == "партнёрский вывод"
    assert payout_kind_label("daily", "principal") == "возврат тела"
    assert payout_kind_label("daily", "") == "дневная"


@pytest.mark.asyncio
async def test_ops_chat_settings_db_overrides_env(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None, demo_mode=False, force_https=False)
    repository = DeltaRepository(tmp_path / "ops-chat.sqlite3", business)
    await repository.connect()
    try:
        env_only = await repository.get_ops_chat_settings(
            env_chat_id=-100111, env_topic_id=7
        )
        assert env_only["source"] == "env"
        assert env_only["chat_id"] == -100111
        assert env_only["topic_id"] == 7
        assert env_only["active"] is True

        await repository.set_ops_chat_settings(
            enabled=True, chat_id=-100222, topic_id=99, changed_by=1
        )
        db = await repository.get_ops_chat_settings(
            env_chat_id=-100111, env_topic_id=7
        )
        assert db["source"] == "database"
        assert db["chat_id"] == -100222
        assert db["topic_id"] == 99

        await repository.set_ops_chat_settings(
            enabled=False, chat_id=-100222, topic_id=99, changed_by=1
        )
        off = await repository.get_ops_chat_settings(
            env_chat_id=-100111, env_topic_id=7
        )
        assert off["source"] == "disabled"
        assert off["active"] is False
        assert off["chat_id"] is None

        await repository.set_ops_chat_settings(
            enabled=True, chat_id=None, topic_id=None, changed_by=1
        )
        cleared = await repository.get_ops_chat_settings(
            env_chat_id=-100111, env_topic_id=7
        )
        assert cleared["source"] == "env"
        assert cleared["chat_id"] == -100111
    finally:
        await repository.close()
