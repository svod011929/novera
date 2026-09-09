"""Unit tests for ops chat HTML formatting."""

from delta_backend.amounts import usdt_to_minor
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
