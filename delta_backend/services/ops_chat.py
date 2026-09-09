"""Fire-and-forget deposit/payout alerts to an ops Telegram chat/topic."""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any, Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from ..amounts import minor_to_text
from ..config import Settings

logger = logging.getLogger(__name__)


class OpsChatSettingsStore(Protocol):
    async def get_ops_chat_settings(
        self, *, env_chat_id: int | None = None, env_topic_id: int | None = None
    ) -> dict[str, object]: ...


def format_user_line(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> str:
    clean_username = str(username or "").strip().lstrip("@")
    if clean_username:
        return f"@{html.escape(clean_username)}"
    clean_name = str(first_name or "").strip()
    if clean_name:
        return html.escape(clean_name)
    return f"ID {int(telegram_id)}"


def explorer_tx_url(template: str, tx_hash: str) -> str:
    return str(template).replace("{tx_hash}", str(tx_hash))


def payout_kind_label(kind: str, subtype: str | None = None) -> str:
    kind_key = str(kind or "").strip().lower()
    subtype_key = str(subtype or "").strip().lower()
    if kind_key == "referral":
        return "партнёрский вывод"
    if subtype_key == "principal":
        return "возврат тела"
    if kind_key == "daily":
        return "дневная"
    return kind_key or "выплата"


def format_deposit_ops_html(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    amount_minor: int,
    deposit_id: int,
    tx_hash: str | None = None,
    explorer_template: str = "https://bscscan.com/tx/{tx_hash}",
) -> str:
    user_line = format_user_line(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )
    amount = html.escape(minor_to_text(int(amount_minor)))
    lines = [
        "💎 <b>Новый депозит</b>",
        f"👤 {user_line} · <code>{int(telegram_id)}</code>",
        f"💰 Сумма: <b>{amount} USDT</b>",
        f"📦 Депозит #{int(deposit_id)}",
    ]
    clean_tx = str(tx_hash or "").strip()
    if clean_tx:
        url = html.escape(explorer_tx_url(explorer_template, clean_tx))
        lines.append(f'🔗 <a href="{url}">Транзакция</a>')
    return "\n".join(lines)


def format_payout_ops_html(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    amount_minor: int,
    tx_hash: str,
    kind: str,
    subtype: str | None = None,
    explorer_template: str = "https://bscscan.com/tx/{tx_hash}",
) -> str:
    user_line = format_user_line(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )
    amount = html.escape(minor_to_text(int(amount_minor)))
    label = html.escape(payout_kind_label(kind, subtype))
    clean_tx = str(tx_hash).strip()
    url = html.escape(explorer_tx_url(explorer_template, clean_tx))
    short = html.escape(clean_tx if len(clean_tx) <= 18 else f"{clean_tx[:10]}…{clean_tx[-6:]}")
    return "\n".join(
        [
            f"💸 <b>Выплата</b> · {label}",
            f"👤 {user_line} · <code>{int(telegram_id)}</code>",
            f"💰 Сумма: <b>{amount} USDT</b>",
            f'🔗 <a href="{url}">{short}</a>',
        ]
    )


def _truncate_error(error: str, limit: int = 200) -> str:
    clean = str(error or "").strip().replace("\n", " ")
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)] + "…"


def format_failed_payout_ops_html(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    amount_minor: int,
    payout_id: int,
    kind: str,
    subtype: str | None = None,
    error: str,
) -> str:
    user_line = format_user_line(
        telegram_id=telegram_id, username=username, first_name=first_name
    )
    amount = html.escape(minor_to_text(int(amount_minor)))
    label = html.escape(payout_kind_label(kind, subtype))
    err = html.escape(_truncate_error(error))
    return "\n".join(
        [
            f"⚠️ <b>Выплата не прошла</b> · {label}",
            f"👤 {user_line} · <code>{int(telegram_id)}</code>",
            f"💰 Сумма: <b>{amount} USDT</b>",
            f"📦 Выплата #{int(payout_id)}",
            f"❗️ {err}",
        ]
    )


def format_unmatched_ops_html(
    *,
    amount_minor: int,
    chain_deposit_id: int,
    tx_hash: str,
    explorer_template: str = "https://bscscan.com/tx/{tx_hash}",
) -> str:
    amount = html.escape(minor_to_text(int(amount_minor)))
    clean_tx = str(tx_hash).strip()
    url = html.escape(explorer_tx_url(explorer_template, clean_tx))
    return "\n".join(
        [
            "❓ <b>Несопоставленный депозит</b>",
            f"💰 Сумма: <b>{amount} USDT</b>",
            f"📦 Chain deposit #{int(chain_deposit_id)}",
            f'🔗 <a href="{url}">Транзакция</a>',
        ]
    )


def format_ops_test_html(
    *, source: str, chat_id: int, topic_id: int | None
) -> str:
    topic = "—" if topic_id is None else str(int(topic_id))
    return "\n".join(
        [
            "🧪 <b>Ops-чат: тест</b>",
            f"Источник: {html.escape(str(source))}",
            f"Chat: <code>{int(chat_id)}</code>",
            f"Topic: <code>{html.escape(topic)}</code>",
        ]
    )


def env_ops_chat_id(settings: Settings) -> int | None:
    chat_id = settings.ops_chat_id
    if chat_id is None and settings.log_channel_id is not None:
        chat_id = settings.log_channel_id
    return int(chat_id) if chat_id is not None else None


def env_ops_topic_id(settings: Settings) -> int | None:
    if settings.ops_topic_id is None:
        return None
    return int(settings.ops_topic_id)


class OpsChatNotifier:
    """Send deposit/payout alerts; DB admin settings override env fallback."""

    def __init__(
        self,
        settings: Settings,
        bot_token: str,
        repository: OpsChatSettingsStore | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.bot = Bot(bot_token)

    async def resolve_target(self) -> tuple[int | None, int | None]:
        env_chat = env_ops_chat_id(self.settings)
        env_topic = env_ops_topic_id(self.settings)
        if self.repository is not None:
            cfg = await self.repository.get_ops_chat_settings(
                env_chat_id=env_chat,
                env_topic_id=env_topic,
            )
            if not cfg.get("active"):
                return None, None
            chat_id = cfg.get("chat_id")
            topic_id = cfg.get("topic_id")
            return (
                int(chat_id) if chat_id is not None else None,
                int(topic_id) if topic_id is not None else None,
            )
        if env_chat is None:
            return None, None
        return env_chat, env_topic

    async def close(self) -> None:
        await self.bot.session.close()

    async def _send_to(
        self,
        chat_id: int,
        topic_id: int | None,
        text: str,
        *,
        preview: bool,
    ) -> None:
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": not preview,
        }
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id
        try:
            await self.bot.send_message(**kwargs)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(min(float(exc.retry_after), 5.0))
            await self.bot.send_message(**kwargs)

    async def _send(self, text: str, *, preview: bool) -> None:
        chat_id, topic_id = await self.resolve_target()
        if chat_id is None:
            return
        try:
            await self._send_to(chat_id, topic_id, text, preview=preview)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            logger.warning("Ops chat rejected message: %s", type(exc).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Ops chat delivery failed: %s", type(exc).__name__)

    async def _send_raising(
        self,
        chat_id: int,
        topic_id: int | None,
        text: str,
        *,
        preview: bool,
    ) -> None:
        await self._send_to(chat_id, topic_id, text, preview=preview)

    async def notify_deposit(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        amount_minor: int,
        deposit_id: int,
        tx_hash: str | None = None,
    ) -> None:
        text = format_deposit_ops_html(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            amount_minor=amount_minor,
            deposit_id=deposit_id,
            tx_hash=tx_hash,
            explorer_template=self.settings.block_explorer_tx_url,
        )
        await self._send(text, preview=False)

    async def notify_payout(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        amount_minor: int,
        tx_hash: str,
        kind: str,
        subtype: str | None = None,
    ) -> None:
        text = format_payout_ops_html(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            amount_minor=amount_minor,
            tx_hash=tx_hash,
            kind=kind,
            subtype=subtype,
            explorer_template=self.settings.block_explorer_tx_url,
        )
        await self._send(text, preview=True)

    async def notify_failed_payout(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        amount_minor: int,
        payout_id: int,
        kind: str,
        subtype: str | None = None,
        error: str = "",
    ) -> None:
        text = format_failed_payout_ops_html(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            amount_minor=amount_minor,
            payout_id=payout_id,
            kind=kind,
            subtype=subtype,
            error=error,
        )
        await self._send(text, preview=False)

    async def notify_unmatched(
        self,
        *,
        amount_minor: int,
        chain_deposit_id: int,
        tx_hash: str,
    ) -> None:
        text = format_unmatched_ops_html(
            amount_minor=amount_minor,
            chain_deposit_id=chain_deposit_id,
            tx_hash=tx_hash,
            explorer_template=self.settings.block_explorer_tx_url,
        )
        await self._send(text, preview=False)

    async def notify_safety(self, text: str) -> None:
        await self._send(str(text), preview=False)

    async def send_test(self) -> dict[str, object]:
        env_chat = env_ops_chat_id(self.settings)
        env_topic = env_ops_topic_id(self.settings)
        if self.repository is None:
            cfg = {
                "active": env_chat is not None,
                "chat_id": env_chat,
                "topic_id": env_topic,
                "source": "env" if env_chat is not None else "none",
            }
        else:
            cfg = await self.repository.get_ops_chat_settings(
                env_chat_id=env_chat, env_topic_id=env_topic
            )
        if not cfg.get("active") or cfg.get("chat_id") is None:
            return {
                "ok": False,
                "chat_id": None,
                "topic_id": None,
                "source": cfg.get("source", "none"),
                "detail": "Ops chat is not active",
            }
        chat_id = int(cfg["chat_id"])
        topic_id = None if cfg.get("topic_id") is None else int(cfg["topic_id"])
        text = format_ops_test_html(
            source=str(cfg.get("source") or "none"),
            chat_id=chat_id,
            topic_id=topic_id,
        )
        try:
            await self._send_raising(chat_id, topic_id, text, preview=False)
        except Exception as exc:
            return {
                "ok": False,
                "chat_id": chat_id,
                "topic_id": topic_id,
                "source": cfg.get("source"),
                "detail": type(exc).__name__,
            }
        return {
            "ok": True,
            "chat_id": chat_id,
            "topic_id": topic_id,
            "source": cfg.get("source"),
        }
